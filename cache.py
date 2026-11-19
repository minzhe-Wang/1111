import json
import os
import time
from threading import RLock

import redis
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True, socket_timeout=1, protocol=2)
local = {}
dirty = set()
guard = RLock()
metrics = {"local_hit": 0, "redis_hit": 0, "database_read": 0, "redis_failure": 0}


def cached(key, loader):
    key = os.getenv("OFFICE_CACHE_NAMESPACE", "") + key
    # Serialize fills and invalidations within this data-service process.
    with guard:
        return load_cached(key, loader)


def invalidate(key):
    key = os.getenv("OFFICE_CACHE_NAMESPACE", "") + key
    with guard:
        local.pop(key, None)
        try:
            client.delete(key)
            dirty.discard(key)
            return True
        except redis.RedisError:
            metrics["redis_failure"] += 1
            dirty.add(key)
            return False


def load_cached(key, loader):
    now = time.monotonic()
    if key in dirty:
        try:
            client.delete(key)
            dirty.discard(key)
        except redis.RedisError:
            metrics['redis_failure'] += 1
            metrics['database_read'] += 1
            return loader()
    with guard:
        item = local.get(key)
        if item and item[0] > now:
            metrics["local_hit"] += 1
            return item[1]
    value = None
    try:
        raw = client.get(key)
        if raw is not None:
            metrics["redis_hit"] += 1
            value = json.loads(raw)
    except redis.RedisError:
        metrics["redis_failure"] += 1
    if value is None:
        metrics["database_read"] += 1
        value = loader()
        try:
            client.setex(key, 60, json.dumps(value, ensure_ascii=False))
        except redis.RedisError:
            metrics["redis_failure"] += 1
    with guard:
        local[key] = (now + 3, value)
    return value


def history(name):
    try:
        return [json.loads(item) for item in client.lrange(context_key(name), -12, -1)]
    except redis.RedisError:
        return []


def remember(name, role, content):
    try:
        key = context_key(name)
        with client.pipeline() as pipeline:
            pipeline.rpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
            pipeline.ltrim(key, -12, -1)
            pipeline.expire(key, 1800)
            pipeline.execute()
    except redis.RedisError:
        pass


def context_available():
    try:
        return bool(client.ping())
    except redis.RedisError:
        return False


def context_key(name):
    return os.getenv('OFFICE_CACHE_NAMESPACE', '') + 'chat:' + name
