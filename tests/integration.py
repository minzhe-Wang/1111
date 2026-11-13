import httpx,time,statistics,json
from concurrent.futures import ThreadPoolExecutor
c=httpx.Client(base_url='http://127.0.0.1:8080',timeout=40)
passed=[]
def ok(name,value):
 assert value,name
 passed.append(name)
def login(name,p):
 r=c.post('/api/v1/login',json={'username':name,'password':p})
 ok('login '+name,r.status_code==200)
 return {'Authorization':'Bearer '+r.json()['token']}
e=login('employee','OfficeDemo1');a=login('admin','OfficeDemo2')
for path in ['/','/admin.html','/mobile.html']:
 ok(path,c.get(path).status_code==200)
username='test_'+str(int(time.time()))
ok('register',c.post('/api/v1/register',json={'username':username,'password':'Testing2026'}).status_code==201)
other=login(username,'Testing2026')
ok('permission',c.get('/api/v1/admin/logs',headers=e).status_code==403)
data={'kind':'room','title':'并发预约测试','start':'2035-03-01T10:00','end':'2035-03-01T11:00','detail':'海棠厅'}
# Unique date hour for repeatable smoke runs.
data['start']='2035-03-01T'+time.strftime('%H:%M:%S')
data['end']='2035-03-02T00:00:00'
with ThreadPoolExecutor(max_workers=2) as pool:
 results=list(pool.map(lambda _:c.post('/api/v1/records',json=data,headers=e),range(2)))
ok('concurrent booking',sorted(r.status_code for r in results)==[201,409])
record=next(r.json()['id'] for r in results if r.status_code==201)
ok('ownership',c.delete('/api/v1/records/'+str(record),headers=other).status_code==404)
ok('withdraw',c.delete('/api/v1/records/'+str(record),headers=e).status_code==200)
for kind in ['schedule','travel']:
 data.update(kind=kind,detail='杭州' if kind=='travel' else '')
 r=c.post('/api/v1/records',json=data,headers=other);ok('create '+kind,r.status_code==201)
 url='/api/v1/records/'+str(r.json()['id'])
 if kind=='schedule':
  data['title']='已修改';ok('edit',c.put(url,json=data,headers=other).status_code==200)
  ok('delete',c.delete(url,headers=other).status_code==200)
 else:
  ok('approval',c.patch(url,json={'status':'approved','remark':'同意'},headers=a).status_code==200)
  ok('repeat approval',c.patch(url,json={'status':'approved','remark':'同意'},headers=a).status_code==409)
  ok('archive',c.post(url+'/archive',headers=a).status_code==200)
for message in ['帮我找会议室','20人']:
 r=c.post('/api/v1/agent/chat',json={'message':message},headers=other)
 ok('live agent '+message,r.status_code==200 and r.json()['mode']=='deepseek')
ok('context',len(r.json()['items'])==2)
c.get('/api/v1/rooms',headers=e);c.get('/api/v1/rooms',headers=e);time.sleep(3.1);c.get('/api/v1/rooms',headers=e)
metrics=c.get('/api/v1/admin/cache',headers=a).json()
ok('cache tiers',metrics['local_hit']>0 and metrics['redis_hit']>0)
def request(_):
 start=time.perf_counter();r=c.get('/api/v1/records',headers=e)
 return r.status_code,(time.perf_counter()-start)*1000
with ThreadPoolExecutor(max_workers=10) as pool:
 measurements=list(pool.map(request,range(100)))
ok('100 request load',all(status==200 for status,_ in measurements))
times=sorted(t for _,t in measurements)
report={'passed':passed,'cache':metrics,'load':{'requests':100,'concurrency':10,'errors':0,'median_ms':round(statistics.median(times),2),'p95_ms':round(times[94],2)}}
from pathlib import Path
Path('test-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
