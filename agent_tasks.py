"""Bounded per-user filling state. Model extracts fields; code owns completeness and attachments."""
import json
import redis
import re
from cache import client, context_key

FIELDS = {'kind','title','start','end','detail','destination','vehicle','passengers','leave_type','amount','category'}
KINDS = {'schedule','room','travel','vehicle','leave','expense'}
LABELS = {'title':'标题或事由','start':'开始时间','end':'结束时间','detail':'会议室',
          'destination':'出差目的地','vehicle':'车牌','passengers':'参会人数','leave_type':'假别',
          'amount':'申报金额','category':'费用类别','receipts':'票据图片'}

def task_key(name):
    return context_key(name) + ':filling'

def read_task(name):
    try:
        raw = client.get(task_key(name))
        return json.loads(raw) if raw else {}
    except (redis.RedisError, ValueError):
        return {}

def write_task(name, task):
    try:
        if task:
            client.set(task_key(name),json.dumps(task,ensure_ascii=False),ex=1800)
        else:
            client.delete(task_key(name))
        return True
    except redis.RedisError:
        return False

def merge_task(previous, patch, action='continue_task'):
    # Unknown/null model fields must not erase facts captured in an earlier turn.
    patch = {k:v for k,v in patch.items() if k in FIELDS and v is not None
             and (not isinstance(v,str) or v.strip())}
    previous_kind = previous.get('fields',{}).get('kind')
    if action == 'new_task' or (patch.get('kind') and patch['kind'] != previous_kind):
        previous = {}
    task = {**previous,'fields':{**previous.get('fields',{}),**patch}}
    return task

def is_new_request(message):
    return bool(re.search(r'另(?:一笔|一项|一个)|再(?:开|来|办)(?:一笔|一项|一个)?|开始一(?:笔|项|个)|新(?:的)?(?:任务|事项|日程|报销|申请)|新一(?:笔|项|个)',message))


def resolve_action(message, previous, proposed):
    if not previous:
        return 'new_task'
    # A short answer such as "38.50元" cannot start a new task even if the model labels it so.
    explicit = is_new_request(message)
    request = re.search(r'(?:创建|登记|提交|申请|我要|我想|帮我).*(?:日程|报销|出差|用车|请假|会议)',message)
    return 'new_task' if explicit or (proposed=='new_task' and request) else 'continue_task'

def prepare_task(task, entry_model):
    fields = task.get('fields',{})
    kind = fields.get('kind')
    if kind not in KINDS:
        return None, ['kind'], '请说明需要办理日程、会议室、出差、用车、请假还是报销。'
    required = [] if kind == 'leave' else ['title']
    required += ['amount','category'] if kind == 'expense' else ['start','end']
    required += {'room':['detail','passengers'],'travel':['destination'],
                 'vehicle':['vehicle'],'leave':['leave_type']}.get(kind,[])
    missing = [k for k in required if fields.get(k) is None or str(fields[k]).strip() == '']
    if kind == 'expense' and not task.get('image_ref'):
        missing.append('receipts')
    if missing:
        return None, missing, '请补充：' + '、'.join(LABELS.get(k,k) for k in missing) + '。已提供的信息会保留。'
    try:
        entry = entry_model.model_validate({**fields,'receipts':[]})
        return entry, [], ''
    except ValueError as exc:
        errors = exc.errors() if hasattr(exc,'errors') else []
        bad = list(dict.fromkeys(str(e['loc'][0]) for e in errors if e['loc']))
        detail = str(errors[0].get('msg','字段不合法')) if errors else '字段不合法'
        return None, bad or ['validation'], '请检查' + '、'.join(LABELS.get(k,k) for k in bad) + '：' + detail

def image_summary(task):
    # Only typed business fields, not arbitrary instructions from an image.
    return {k:v for k,v in task.get('fields',{}).items() if k in FIELDS and v is not None}
