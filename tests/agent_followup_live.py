"""Real-model capability check; 4 model calls, no business write until explicit confirmation."""
import base64,io,json,uuid,hashlib
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import httpx
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
c=httpx.Client(base_url='http://127.0.0.1:8080/api/v1',timeout=40)
body={'username':'followup_'+uuid.uuid4().hex[:8],'password':'Followup2026'}
c.post('/register',json=body).raise_for_status()
r=c.post('/login',json=body);r.raise_for_status()
h={'Authorization':'Bearer '+r.json()['token']}
checks=[]
def ask(text,image=None):
    r=c.post('/agent/chat',headers=h,json={'message':text,'image':image});r.raise_for_status()
    data=r.json();assert data['mode']=='deepseek',data
    checks.append({'input':text,'reply':data});return data

r=ask('请给1个人找会议室。')
assert not any('多少人' in item for item in r['items']),r
img=Image.new('RGB',(900,280),'white');draw=ImageDraw.Draw(img)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',28)
draw.text((24,30),'RECEIPT\nItem: Taxi fare\nAmount: [not provided]',font=font,fill='black',spacing=18)
buf=io.BytesIO();img.save(buf,'PNG')
image='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
r=ask('开始一笔新报销，事由是客户拜访打车费，类别交通。票据金额没有填写，请向我询问金额。',image)
assert not r['proposal_id'] and 'amount' in r['missing_fields'],r
r=ask('金额是38.50元。')
assert r['proposal_id'],r
draft=c.get('/agent/proposals/'+r['proposal_id'],headers=h).json()
assert Decimal(draft['payload']['amount'])==Decimal('38.50') and len(draft['payload']['receipts'])==1,draft
assert c.get('/records',headers=h).json()==[]
c.delete('/agent/proposals/'+r['proposal_id'],headers=h)
r=ask('再开一笔新的报销，事由是买办公用品，类别办公。')
assert not r['proposal_id'] and 'receipts' in r['missing_fields'] and 'amount' in r['missing_fields'],r
report={'date':datetime.now(timezone.utc).isoformat(),'checks':checks,'image_then_text_receipt_retained':True,
        'business_records_without_confirmation':0,'new_task_does_not_reuse_receipt':True,
        'source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['main.py','agent_tasks.py','cache.py']}}
(ROOT/'tests/v131-agent-live-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print('PASS: 1 person, image -> missing amount -> text completion, attachment retained, no unconfirmed writes, new-task isolation')
