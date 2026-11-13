import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import httpx
import jwt
from cache import cached, history, remember, metrics
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine, insert, select, update
from sqlalchemy.exc import IntegrityError

load_dotenv()
root = Path(__file__).parent
engine = create_engine(os.getenv("DATABASE_URL", f"sqlite:///{root / 'office.db'}"))
secret = os.getenv("JWT_SECRET") or secrets.token_hex(32)
metadata = MetaData()
records = Table("office_records", metadata, Column("id", Integer, primary_key=True),
                Column("owner", String(50), nullable=False), Column("kind", String(20), nullable=False),
                Column("status", String(20), nullable=False), Column("data", JSON, nullable=False))
metadata.create_all(engine)
users = Table("office_users", metadata, Column("username", String(50), primary_key=True),
              Column("password_hash", String(255), nullable=False), Column("role", String(20), nullable=False))
resources = Table("office_resources", metadata, Column("name", String(100), primary_key=True))
metadata.create_all(engine)
rooms = {"海棠厅": 12, "梧桐厅": 24, "松柏厅": 40}
accounts = {"employee": ("employee", os.getenv("OFFICE_EMPLOYEE_PASSWORD", "OfficeDemo1")),
            "admin": ("admin", os.getenv("OFFICE_ADMIN_PASSWORD", "OfficeDemo2"))}


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200000).hex()
    return salt + ":" + digest


with engine.begin() as conn:
    for name, (role, password) in accounts.items():
        if conn.execute(select(users).where(users.c.username == name)).first() is None:
            conn.execute(insert(users).values(username=name, role=role, password_hash=password_hash(password)))
    for room in rooms:
        if conn.execute(select(resources).where(resources.c.name == room)).first() is None:
            conn.execute(insert(resources).values(name=room))
app = FastAPI(title="AI 智能行政办公平台")
bearer = HTTPBearer()


def user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        return jwt.decode(credentials.credentials, secret, algorithms=["HS256"])["sub"]
    except (jwt.InvalidTokenError, KeyError) as exc:
        raise HTTPException(401, "登录已失效") from exc


def admin(name: str = Depends(user)):
    with engine.connect() as conn:
        role = conn.execute(select(users.c.role).where(users.c.username == name)).scalar()
    if role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return name


class Login(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_]{3,50}$")
    password: str = Field(min_length=8, max_length=128)


class Entry(BaseModel):
    kind: Literal["schedule", "room", "travel"]
    title: str = Field(min_length=1, max_length=100)
    start: datetime
    end: datetime
    detail: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def validate_entry(self):
        if self.start.tzinfo or self.end.tzinfo or self.start >= self.end:
            raise ValueError("请使用本地时间，且结束时间必须晚于开始时间")
        if self.kind == "room" and self.detail not in rooms:
            raise ValueError("请选择有效会议室")
        if self.kind == "travel" and not self.detail.strip():
            raise ValueError("请填写出差目的地")
        return self


class Decision(BaseModel):
    status: Literal["approved", "rejected"]
    remark: str = Field(max_length=255)


class Chat(BaseModel):
    message: str = Field(min_length=1, max_length=300)


class Intent(BaseModel):
    skill: Literal["schedule_list", "room_match", "travel_draft", "unknown"]
    capacity: int = Field(default=1, ge=1, le=1000)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(root / "index.html")


@app.get("/api/v1/rooms")
def room_list(name: str = Depends(user)):
    return cached("office:room-catalog:v1", lambda: rooms)


@app.post("/api/v1/login")
def login(body: Login):
    with engine.connect() as conn:
        account = conn.execute(select(users).where(users.c.username == body.username)).mappings().first()
    if account is None or not secrets.compare_digest(
        password_hash(body.password, account["password_hash"].split(":")[0]), account["password_hash"]
    ):
        raise HTTPException(401, "账号或密码错误")
    return {"token": jwt.encode({"sub": body.username, "exp": datetime.now(timezone.utc) + timedelta(hours=4)},
                                secret, algorithm="HS256"), "role": account["role"]}


@app.post("/api/v1/register", status_code=201)
def register(body: Login):
    try:
        with engine.begin() as conn:
            conn.execute(insert(users).values(username=body.username, role="employee",
                                             password_hash=password_hash(body.password)))
    except IntegrityError as exc:
        raise HTTPException(409, "账号已存在") from exc
    return {"username": body.username}


def list_for(name, kind=None):
    query = select(records).where(records.c.kind != "chat")
    if name != "admin":
        query = query.where(records.c.owner == name)
    if kind:
        query = query.where(records.c.kind == kind)
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(query.order_by(records.c.id.desc())).mappings()]


@app.get("/api/v1/records")
def list_entries(name: str = Depends(user)):
    return list_for(name)


@app.post("/api/v1/records", status_code=201)
def create(body: Entry, name: str = Depends(user)):
    data = body.model_dump(mode="json")
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        if engine.dialect.name == "mysql":
            lock_query = select(users.c.username).where(users.c.username == name)
            if body.kind == "room":
                lock_query = select(resources.c.name).where(resources.c.name == body.detail)
            conn.execute(lock_query.with_for_update()).first()
        if body.kind in ("schedule", "room"):
            query = select(records).where(records.c.kind == body.kind, records.c.status.in_(["active", "pending", "approved"]))
            if body.kind == "schedule":
                query = query.where(records.c.owner == name)
            for row in conn.execute(query).mappings():
                old = row["data"]
                same_resource = body.kind == "schedule" or old["detail"] == body.detail
                if same_resource and old["start"] < data["end"] and data["start"] < old["end"]:
                    raise HTTPException(409, "该时间段已被占用")
        status = "active" if body.kind == "schedule" else "pending"
        result = conn.execute(insert(records).values(owner=name, kind=body.kind, status=status, data=data))
        return {"id": result.inserted_primary_key[0], "status": status}


@app.patch("/api/v1/records/{entry_id}")
def decide(entry_id: int, body: Decision, name: str = Depends(admin)):
    with engine.begin() as conn:
        row = conn.execute(select(records).where(records.c.id == entry_id)).mappings().first()
        if row is None:
            raise HTTPException(404, "记录不存在")
        result = conn.execute(update(records).where(records.c.id == entry_id, records.c.status == "pending")
                              .values(status=body.status, data={**row["data"], "remark": body.remark}))
        if result.rowcount != 1:
            raise HTTPException(409, "仅可审核待处理申请")
    return {"status": body.status}


@app.post("/api/v1/records/{entry_id}/archive")
def archive(entry_id: int, name: str = Depends(admin)):
    with engine.begin() as conn:
        result = conn.execute(update(records).where(records.c.id == entry_id, records.c.kind == "travel",
                              records.c.status.in_(["approved", "rejected"])).values(status="archived"))
        if result.rowcount != 1:
            raise HTTPException(409, "仅可归档已审核的出差申请")
    return {"status": "archived"}


def match_room(name, intent, message):
    return [f"{room}（{capacity} 人）" for room, capacity in rooms.items() if capacity >= intent.capacity]


def schedule_list(name, intent, message):
    return [row["data"]["title"] + " " + row["data"]["start"] for row in list_for(name, "schedule")
            if row["owner"] == name]


def travel_draft(name, intent, message):
    return ["请在出差表单确认目的地、起止时间和事由。", f"申请草稿：{message}"]


skills = {"room_match": match_room, "schedule_list": schedule_list, "travel_draft": travel_draft}


def offline_intent(message):
    import re
    if "会议室" in message:
        count = re.search(r"(\d+)\s*人", message)
        return Intent(skill="room_match", capacity=min(1000, max(1, int(count[1]))) if count else 1)
    if "日程" in message:
        return Intent(skill="schedule_list")
    if "出差" in message:
        return Intent(skill="travel_draft")
    return Intent(skill="unknown")


@app.post("/api/v1/agent/chat")
def chat(body: Chat, name: str = Depends(user)):
    previous = history(name)
    message = body.message
    if previous and message.strip().rstrip("人").isdigit():
        message = "找一间能容纳 " + message.strip().rstrip("人") + " 人的会议室"
    key = os.getenv("DEEPSEEK_API_KEY")
    mode = "offline"
    intent = offline_intent(message)
    if key:
        try:
            response = httpx.post("https://api.deepseek.com/chat/completions", timeout=25,
                headers={"Authorization": f"Bearer {key}"}, json={
                    "model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
                    "thinking": {"type": "disabled"},
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "你是办公意图分类器。仅输出 JSON，字段 skill 和 capacity。skill 限 schedule_list（查日程）、room_match（按人数找会议室）、travel_draft（出差草稿）、unknown。capacity 为 1 至 1000 的整数，缺省为 1。禁止写操作。"},
                        *previous, {"role": "user", "content": message}]})
            response.raise_for_status()
            intent = Intent.model_validate_json(response.json()["choices"][0]["message"]["content"])
            mode = "deepseek"
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            mode = "fallback"
    handler = skills.get(intent.skill)
    items = handler(name, intent, body.message) if handler else ["支持查询日程、按人数找会议室、生成出差表单草稿。"]
    if intent.skill == "room_match" and intent.capacity == 1:
        items = ["请问需要容纳多少人？可以回复人数，例如 20 人。"]
    remember(name, "user", body.message)
    remember(name, "assistant", "\n".join(items))
    with engine.begin() as conn:
        conn.execute(insert(records).values(owner=name, kind="chat", status=mode,
                    data={"message": body.message, "skill": intent.skill, "items": items}))
    return {"mode": mode, "skill": intent.skill, "items": items}


@app.get("/api/v1/admin/cache")
def cache_metrics(name: str = Depends(admin)):
    return metrics


@app.delete("/api/v1/records/{entry_id}")
def cancel(entry_id: int, name: str = Depends(user)):
    with engine.begin() as conn:
        row = conn.execute(select(records).where(records.c.id == entry_id)).mappings().first()
        if row is None or row["owner"] != name:
            raise HTTPException(404, "记录不存在")
        if row["status"] not in ("active", "pending"):
            raise HTTPException(409, "仅可删除日程或撤回待审核申请")
        result = conn.execute(update(records).where(records.c.id == entry_id, records.c.status == row["status"])
                              .values(status="cancelled"))
        if result.rowcount != 1:
            raise HTTPException(409, "记录状态已变化")
    return {"status": "cancelled"}


@app.put("/api/v1/records/{entry_id}")
def edit_schedule(entry_id: int, body: Entry, name: str = Depends(user)):
    if body.kind != "schedule":
        raise HTTPException(422, "此接口仅用于修改日程")
    data = body.model_dump(mode="json")
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        if engine.dialect.name == "mysql":
            conn.execute(select(users.c.username).where(users.c.username == name).with_for_update()).first()
        rows = list(conn.execute(select(records).where(records.c.owner == name, records.c.kind == "schedule").with_for_update()).mappings())
        target = next((row for row in rows if row["id"] == entry_id and row["status"] == "active"), None)
        if target is None:
            raise HTTPException(404, "日程不存在")
        for row in rows:
            old = row["data"]
            if row["id"] != entry_id and row["status"] == "active" and old["start"] < data["end"] and data["start"] < old["end"]:
                raise HTTPException(409, "日程时间冲突")
        conn.execute(update(records).where(records.c.id == entry_id).values(data=data))
    return {"id": entry_id}


@app.get("/api/v1/admin/logs")
def logs(name: str = Depends(admin)):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(records).where(records.c.kind == "chat")
                                                 .order_by(records.c.id.desc()).limit(50)).mappings()]
