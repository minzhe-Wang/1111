import sys,time,json,uuid,statistics,base64,io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import cache

import httpx
from PIL import Image,ImageDraw,ImageFont
c=httpx.Client(base_url='http://127.0.0.1:8080/api/v1',timeout=40)
passed=[]
def check(label,cond):
 assert cond,label
 passed.append(label)
def login(n,p):
 r=c.post('/login',json={'username':n,'password':p});check('login '+n,r.status_code==200)
 return {'Authorization':'Bearer '+r.json()['token']}
name='v13_'+uuid.uuid4().hex[:8]
c.post('/register',json={'username':name,'password':'Testing2026'})
h=login(name,'Testing2026');a=login('admin','OfficeDemo2')
room='V13验收厅'+uuid.uuid4().hex[:5]
check('Java create room',c.put('/admin/rooms/'+room,headers=a,json={'capacity':5}).status_code==200)
c.get('/rooms',headers=h)
r=c.put('/admin/rooms/'+room,headers=a,json={'capacity':6})
check('Java invalidates Python local cache',r.status_code==200 and c.get('/rooms',headers=h).json()[room]==6)
plate='苏V'+uuid.uuid4().hex[:5].upper()
check('plate directory',c.put('/admin/vehicles/'+plate,headers=a,json={}).status_code==200)
body={'kind':'vehicle','title':'V1.3联调用车','vehicle':plate,'start':'2041-02-01T09:00:00','end':'2041-02-01T10:00:00'}
def submit(_):return c.post('/records',headers={**h,'Idempotency-Key':uuid.uuid4().hex},json=body)
with ThreadPoolExecutor(2) as pool:rs=list(pool.map(submit,range(2)))
check('MariaDB concurrent resource lock',sorted(r.status_code for r in rs)==[201,409])
rid=next(r.json()['id'] for r in rs if r.status_code==201)
check('approve',c.patch('/records/'+str(rid),headers=a,json={'status':'approved'}).status_code==200)
check('cancel approved before start',c.request('DELETE','/records/'+str(rid),headers=h,json={'reason':'验收测试结束'}).status_code==200)
schedule={'kind':'schedule','title':'V13私密验收','start':body['start'],'end':body['end']}
key=uuid.uuid4().hex
rs=[c.post('/records',headers={**h,'Idempotency-Key':key},json=schedule) for _ in range(2)]
check('Java forwards idempotency key',rs[0].status_code==201 and rs[0].json()['id']==rs[1].json()['id'])
check('admin schedule isolation',all(x['owner']!=name or x['kind']!='schedule' for x in c.get('/records',headers=a).json()))
check('Java summary available',c.get('/admin/summary',headers=a).status_code==200)
# Small real-model verification: one complete text request and one image request.
r=c.post('/agent/chat',headers=h,json={'message':'请创建个人日程：2042年5月1日9点到10点，标题是V13模型验收，不要添加其他内容。'})
check('real text model',r.status_code==200 and r.json()['mode']=='deepseek' and r.json()['proposal_id'])
pid=r.json()['proposal_id'];d=c.get('/agent/proposals/'+pid,headers=h).json()
edited={**d['payload'],'title':'V13已核对模型日程'}
r=c.put('/agent/proposals/'+pid,headers=h,json={'version':d['version'],'entry':edited});check('live draft edit',r.status_code==200)
r=c.post('/agent/confirm/'+pid,headers=h,json={'version':r.json()['version']});check('live draft confirmation',r.status_code==200)
img=Image.new('RGB',(900,300),'white');draw=ImageDraw.Draw(img)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',30)
draw.text((25,35),'Meeting: Vision acceptance\nDate: 2042-05-02\nStart: 09:00   End: 10:00',font=font,fill='black',spacing=20)
buf=io.BytesIO();img.save(buf,'PNG')
r=c.post('/agent/chat',headers=h,json={'message':'根据图片创建个人日程，标题使用图片中的Meeting名称。','image':'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()})
check('real multimodal model',r.status_code==200 and r.json()['mode']=='deepseek' and r.json()['proposal_id'])
c.delete('/agent/proposals/'+r.json()['proposal_id'],headers=h)
def query(_):
 t=time.perf_counter();r=c.get('/records',headers=h);return r.status_code,(time.perf_counter()-t)*1000
with ThreadPoolExecutor(10) as pool: measurements=list(pool.map(query,range(100)))
times=sorted(x[1] for x in measurements)
check('100 HTTP requests successful',all(x[0]==200 for x in measurements))
check('HTTP P95 within 300ms',times[94]<=300)
before=c.get('/admin/cache',headers=a).json()['database_read']
for _ in range(100): check_result=c.get('/rooms',headers=h)
after=c.get('/admin/cache',headers=a).json()['database_read']
check('100 directory reads <=2 DB loads',after-before<=2)
report={'timestamp':time.strftime('%Y-%m-%d %H:%M:%S'),'passed':passed,'user':name,'room':room,'plate':plate,'performance':{'requests':100,'concurrency':10,'p95_ms':round(times[94],2),'median_ms':round(statistics.median(times),2)},'scope':'Java 8080 + MariaDB + Redis + real model; test data retained'}
import hashlib,platform
report['source_sha256']={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['main.py','cache.py','java-server/src/main/java/cn/zhixing/AdminController.java']}
report['environment']={'platform':platform.platform(),'processor':platform.processor(),'user_records':len(c.get('/records',headers=h).json()),'directory_db_loads':after-before}
(ROOT/'tests/v13-live-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
