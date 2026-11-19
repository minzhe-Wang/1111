"""Replay the reported mixed conversation with a real model; no business writes."""
import httpx,uuid,json
from pathlib import Path
from datetime import datetime,timezone
c=httpx.Client(base_url='http://127.0.0.1:8080/api/v1',timeout=40)
credentials={'username':'conversation_'+uuid.uuid4().hex[:8],'password':'Testing2026'}
c.post('/register',json=credentials).raise_for_status()
login=c.post('/login',json=credentials);login.raise_for_status()
c.headers['Authorization']='Bearer '+login.json()['token']
turns=[]
for message in ['请给1个人找会议室','查一下我明天的日程','找一间能容纳20人的会议室','帮我起草明天去上海的出差申请','1234','申报金额:123','明天14:00--15:00,海棠厅有人占用吗']:
    r=c.post('/agent/chat',json={'message':message});r.raise_for_status()
    turns.append({'message':message,'response':r.json()})
assert turns[0]['response']['skill']=='query'
assert '当天没有日程' in str(turns[1])
assert '松柏厅' in str(turns[2])
assert turns[3]['response']['mode']=='deepseek'
assert 'start' in turns[3]['response']['missing_fields'] and 'end' in turns[3]['response']['missing_fields']
assert turns[4]['response']['skill']=='clarify'
assert all(not t['response']['proposal_id'] for t in turns)
assert '当前空闲' in str(turns[-1]) or '已占用' in str(turns[-1])
assert c.get('/records').json()==[]
result={'date':datetime.now(timezone.utc).isoformat(),'passed':True,'turns':turns,'business_writes':0}
Path('tests/conversation-live-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print('PASS: 7 mixed turns, correct queries, missing times, no task switch or business writes')
