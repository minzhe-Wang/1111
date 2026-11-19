"""Deterministic routing and date bounds for common office requests."""
import re
from datetime import datetime, timedelta

KINDS = {'出差':'travel','报销':'expense','请假':'leave','用车':'vehicle','日程':'schedule','会议室':'room'}

def requested_kind(text):
    if re.search(r'审批|归档|删除|撤回', text):
        return None
    if not re.search(r'申请|起草|创建|新增|登记|预约|预订|报销|我要请假|帮我请假', text):
        return None
    return next((v for k,v in KINDS.items() if k in text), None)

def day_bounds(text, now):
    day = None
    for word,offset in [('大后天',3),('后天',2),('明天',1),('今天',0),('昨天',-1)]:
        if word in text:
            day = now.date()+timedelta(days=offset);break
    match = re.search(r'(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?',text)
    if match:
        day = datetime(*map(int,match.groups())).date()
    if day:
        start = datetime.combine(day,datetime.min.time())
        return start,start+timedelta(days=1)
    return None

def time_bounds(text, now):
    bounds=day_bounds(text,now)
    clocks=re.findall(r'(?<!\d)(\d{1,2})(?::|：|点|时)(\d{2})?',text)
    if not bounds or len(clocks)!=2:
        return None
    times=[]
    for hour,minute in clocks:
        hour=int(hour);minute=int(minute or 0)
        if '下午' in text and hour<12:hour+=12
        times.append(bounds[0].replace(hour=hour,minute=minute))
    if times[1]<=times[0]:raise ValueError('结束时间需要晚于开始时间')
    return times

def query_kind(text):
    if requested_kind(text):return None
    if '日程' in text:return 'schedule'
    if re.search(r'占用|空闲|有空|可用|有人|空着',text):return 'availability'
    if '会议室' in text and re.search(r'找|查询|查|容纳|人',text):return 'capacity'
    return None
