"""Isolated V1.3 regression suite. No real model calls or changes to the user's database."""
import os
import sys
import tempfile
import unittest
import base64
import io
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

tmp = tempfile.TemporaryDirectory(prefix='office-v13-')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tmp.name)/'test.db')
os.environ['RECEIPT_DIR']=str(Path(tmp.name)/'receipts')
os.environ['DEEPSEEK_API_KEY']=''
os.environ['OFFICE_CACHE_NAMESPACE']='test-v13-'+__import__('uuid').uuid4().hex+':'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main as m
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import insert, select, update

class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=TestClient(m.app)
        cls.headers={}
        for who in ('alice','bobby'):
            cls.c.post('/api/v1/register',json={'username':who,'password':'Testing2026'})
        for who,pwd in [('alice','Testing2026'),('bobby','Testing2026'),('admin','OfficeDemo2')]:
            r=cls.c.post('/api/v1/login',json={'username':who,'password':pwd})
            assert r.status_code==200,r.text
            cls.headers[who]={'Authorization':'Bearer '+r.json()['token']}
    def call(self,method,path,body=None,who='alice',key=None):
        headers={**self.headers[who]}
        if method=='POST' and path=='/records': headers['Idempotency-Key']=key or __import__('uuid').uuid4().hex
        return self.c.request(method,'/api/v1'+path,json=body,headers=headers)
    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        m.engine.dispose()
        tmp.cleanup()
    def entry(self,kind='schedule',**kw):
        return dict(kind=kind,title='验收事项',start='2040-01-01T09:00:00',end='2040-01-01T10:00:00',**kw)
    def create(self,body,who='alice'):
        r=self.call('POST','/records',body,who); self.assertEqual(r.status_code,201,r.text); return r.json()['id']
    def draft(self):
        pid=__import__('uuid').uuid4().hex
        with m.engine.begin() as c:
            c.execute(insert(m.proposals).values(id=pid,owner='alice',payload=self.entry(),version=1,
                expires=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()))
        return pid
    def image(self,color):
        buf=io.BytesIO();Image.new('RGB',(12,12),color).save(buf,'PNG')
        return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
    def test_01_auth_privacy_schedule_history(self):
        self.assertEqual(self.c.get('/api/v1/records').status_code,401)
        self.assertEqual(self.call('GET','/admin/logs').status_code,403)
        a=self.create(self.entry());self.create(self.entry())
        self.assertEqual(self.call('GET',f'/records/{a}',who='admin').status_code,404)
        self.assertEqual(self.call('GET',f'/records/{a}',who='bobby').status_code,404)
        self.assertEqual(self.call('PUT',f'/records/{a}',{**self.entry(),'title':'修改后'}).status_code,200)
        self.assertEqual(self.call('DELETE',f'/records/{a}').status_code,200)
        self.assertEqual(len(self.call('GET',f'/records/{a}').json()['data']['history']),3)
        self.assertTrue(all(r['kind']!='schedule' for r in self.call('GET','/records',who='admin').json()))
    def test_02_room_concurrency_cancel_boundary(self):
        self.call('PUT','/admin/rooms/验收厅',{'capacity':4},'admin')
        body=self.entry('room',detail='验收厅',passengers=4)
        with ThreadPoolExecutor(2) as pool:
            rs=list(pool.map(lambda who:self.call('POST','/records',body,who),['alice','bobby']))
        self.assertEqual(sorted(r.status_code for r in rs),[201,409])
        i=next(i for i,r in enumerate(rs) if r.status_code==201);who=['alice','bobby'][i];rid=rs[i].json()['id']
        self.assertEqual(self.call('PATCH',f'/records/{rid}',{'status':'rejected'},'admin').status_code,422)
        self.assertEqual(self.call('PATCH',f'/records/{rid}',{'status':'approved','amount':1},'admin').status_code,422)
        for _ in range(2):self.assertEqual(self.call('PATCH',f'/records/{rid}',{'status':'approved'},'admin').status_code,200)
        self.assertEqual(self.call('DELETE',f'/records/{rid}',who=who).status_code,422)
        with patch.object(m,'now_local',return_value=datetime(2040,1,1,9)):
            self.assertEqual(self.call('DELETE',f'/records/{rid}',{'reason':'行程变更'},who).status_code,409)
        with patch.object(m,'now_local',return_value=datetime(2040,1,1,8,59,59)):
            self.assertEqual(self.call('DELETE',f'/records/{rid}',{'reason':'行程变更'},who).status_code,200)
        self.create(body)
        self.create({**body,'start':body['end'],'end':'2040-01-01T11:00:00'})
        self.assertEqual(self.call('POST','/records',{**body,'passengers':5}).status_code,409)
    def test_03_vehicle_resource_recheck(self):
        self.assertEqual(self.call('PUT','/admin/vehicles/苏A12345',{},'admin').status_code,200)
        body=self.entry('vehicle',vehicle=' 苏a12345 ')
        rid=self.create(body)
        self.call('PUT','/admin/vehicles/苏A12345',{'enabled':False},'admin')
        self.assertEqual(self.call('PATCH',f'/records/{rid}',{'status':'approved'},'admin').status_code,409)
        self.call('PUT','/admin/vehicles/苏A12345',{'enabled':True},'admin')
        self.assertEqual(self.call('PATCH',f'/records/{rid}',{'status':'approved'},'admin').status_code,200)
        self.assertEqual(self.call('POST',f'/records/{rid}/archive',who='admin').status_code,409)
        with patch.object(m,'now_local',return_value=datetime(2040,1,1,10)):
            self.assertEqual(self.call('POST',f'/records/{rid}/archive',who='admin').status_code,200)
        self.assertEqual(self.call('GET',f'/records/{rid}').json()['data']['approval_result'],'approved')
    def test_04_cross_warning_and_conflicts(self):
        body=self.entry('travel',destination='杭州');rid=self.create(body)
        self.assertEqual(self.call('POST','/records',body).status_code,409)
        leave=self.entry('leave',leave_type='事假');r=self.call('POST','/records',leave)
        self.assertEqual(r.status_code,201,r.text);self.assertTrue(r.json()['warnings'])
        self.assertEqual(self.call('POST','/records',leave).status_code,409)
        rows=self.call('GET','/records',who='admin').json()
        self.assertTrue(next(x for x in rows if x['id']==rid)['warnings'])
        self.assertEqual(self.call('POST','/records',{**leave,'end':'2040-03-01T10:00:00'}).status_code,422)
    def test_05_receipts_precision_privacy_and_lifecycle(self):
        body={'kind':'expense','title':'测试报销','category':'交通','amount':'12.34','receipts':[self.image('red')]}
        self.assertEqual(self.call('POST','/records',{**body,'amount':'1.001'}).status_code,422)
        self.assertEqual(self.call('POST','/records',{**body,'receipts':[]}).status_code,422)
        self.assertEqual(self.call('POST','/records',{**body,'receipts':body['receipts']*2}).status_code,409)
        rid=self.create(body)
        f=self.call('GET',f'/records/{rid}').json()['data']['receipts'][0]
        self.assertEqual(self.call('GET','/receipts/'+f,who='bobby').status_code,404)
        self.assertEqual(self.call('GET','/receipts/'+f,who='admin').status_code,200)
        self.assertEqual(self.call('POST','/records',{**body,'receipts':[f]},'bobby').status_code,422)
        self.assertEqual(self.call('POST','/records',body,'bobby').status_code,409)
        self.call('PATCH',f'/records/{rid}',{'status':'rejected','remark':'更正'},'admin')
        self.call('POST',f'/records/{rid}/archive',who='admin')
        rid2=self.create(body,'bobby')
        self.call('PATCH',f'/records/{rid2}',{'status':'approved'},'admin')
        self.call('POST',f'/records/{rid2}/archive',who='admin')
        self.assertEqual(self.call('POST','/records',body).status_code,409)
        concurrent={**body,'receipts':[self.image('blue')]}
        with ThreadPoolExecutor(2) as pool:
            rs=list(pool.map(lambda who:self.call('POST','/records',concurrent,who),['alice','bobby']))
        self.assertEqual(sorted(r.status_code for r in rs),[201,409])
    def test_06_idempotency_response_loss(self):
        body=self.entry()
        with ThreadPoolExecutor(2) as pool:
            rs=list(pool.map(lambda _:self.call('POST','/records',body,key='same-key-1234'),range(2)))
        self.assertEqual(rs[0].json()['id'],rs[1].json()['id'])
        self.assertEqual(self.call('POST','/records',{**body,'title':'changed'},key='same-key-1234').status_code,409)
    def test_07_drafts_version_expiry_cancel(self):
        pid=self.draft();url='/agent/proposals/'+pid
        self.assertEqual(self.call('GET',url,who='bobby').status_code,404)
        expiry=self.call('GET',url).json()['expires']
        r=self.call('PUT',url,{'version':1,'entry':self.entry()});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['expires'],expiry)
        self.assertEqual(self.call('POST','/agent/confirm/'+pid,{'version':1}).status_code,409)
        r=self.call('POST','/agent/confirm/'+pid,{'version':2});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.call('POST','/agent/confirm/'+pid,{'version':2}).json()['id'],r.json()['id'])
        pid=self.draft();self.call('DELETE','/agent/proposals/'+pid)
        self.assertEqual(self.call('POST','/agent/confirm/'+pid,{'version':1}).status_code,409)
        pid=self.draft()
        with m.engine.begin() as c:c.execute(update(m.proposals).where(m.proposals.c.id==pid).values(expires=datetime.now(timezone.utc).isoformat()))
        self.assertEqual(self.call('POST','/agent/confirm/'+pid,{'version':1}).status_code,409)
        r=self.call('POST','/agent/proposals/'+pid+'/regenerate')
        self.assertEqual(r.status_code,200,r.text);self.assertNotEqual(r.json()['id'],pid)
    def test_08_cache_and_agent_failure(self):
        import cache
        self.call('PUT','/admin/rooms/缓存厅',{'capacity':10},'admin')
        self.assertEqual(self.call('GET','/rooms').json()['缓存厅'],10)
        self.call('PUT','/admin/rooms/缓存厅',{'capacity':20},'admin')
        self.assertEqual(self.call('GET','/rooms').json()['缓存厅'],20)
        from redis import RedisError
        with patch.object(cache.client,'delete',side_effect=RedisError()),patch.object(cache.client,'get',side_effect=RedisError()):
            r=self.call('PUT','/admin/rooms/缓存厅',{'capacity':30},'admin')
            self.assertFalse(r.json()['cacheInvalidated'])
            self.assertEqual(self.call('GET','/rooms').json()['缓存厅'],30)
            self.create(self.entry())
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}),patch.object(m.httpx,'post',side_effect=m.httpx.ConnectError('offline')):
            r=self.call('POST','/agent/chat',{'message':'帮我报销12元','image':self.image('green')})
            self.assertEqual(r.json()['mode'],'fallback');self.assertIsNone(r.json()['proposal_id'])
        logs=self.call('GET','/admin/logs',who='admin').json()
        self.assertTrue(all('12元' not in json.dumps(r,ensure_ascii=False) for r in logs))

    def test_09_cleanup_and_context(self):
        import cache
        f=m.store_receipt(self.image('yellow'),'alice')
        os.utime(m.receipt_dir/f,(0,0))
        m.cleanup_receipts()
        self.assertFalse((m.receipt_dir/f).exists())
        for r in self.call('GET','/records').json():
            for f in r['data'].get('receipts',[]): self.assertTrue((m.receipt_dir/f).exists())
        if cache.context_available():
            for i in range(15): cache.remember('alice','user',str(i))
            self.assertEqual(len(cache.history('alice')),12)
            self.assertFalse(cache.history('bobby'))
            self.assertGreater(cache.client.ttl(cache.context_key('alice')),1700)
            self.call('DELETE','/agent/context')
            self.assertFalse(cache.history('alice'))

    def test_10_draft_race_and_timezone(self):
        pid=self.draft()
        with ThreadPoolExecutor(2) as pool:
            rs=list(pool.map(lambda _:self.call('POST','/agent/confirm/'+pid,{'version':1}),range(2)))
        self.assertEqual(rs[0].json()['id'],rs[1].json()['id'])
        r=self.call('POST','/records',{**self.entry(),'start':'2040-01-01T01:00:00Z','end':'2040-01-01T02:00:00Z'})
        self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.call('GET','/records/'+str(r.json()['id'])).json()['data']['start'],'2040-01-01T09:00:00')

    def test_11_one_person_and_missing_capacity(self):
        self.assertTrue(m.match_room('alice',m.Intent(skill='room_match',capacity=1),'1人'))
        self.assertIn('多少人',m.match_room('alice',m.Intent(skill='room_match'),'')[0])
        self.assertEqual(m.offline_intent('找1人的会议室').capacity,1)

    def model_reply(self, payload):
        import httpx
        return httpx.Response(200, request=httpx.Request('POST','https://example.test'),
            json={'choices':[{'message':{'content':json.dumps(payload,ensure_ascii=False)}}]})

    def test_12_image_then_amount_preserves_owned_attachment(self):
        from agent_tasks import read_task
        self.call('DELETE','/agent/context')
        before=len(self.call('GET','/records').json())
        first={'skill':'expense_draft','task_action':'new_task','entry':{'kind':'expense','title':'跨轮票据','category':'交通'}}
        second={'skill':'create_entry','task_action':'new_task','entry':{'amount':'19.80','title':None,'category':''}}
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}),patch.object(m.httpx,'post',side_effect=[self.model_reply(first),self.model_reply(second)]):
            r=self.call('POST','/agent/chat',{'message':'帮我报销这张票据','image':self.image('pink')})
            self.assertEqual(r.json()['missing_fields'],['amount'])
            pending=read_task('alice');self.assertTrue(pending['image_ref']);self.assertTrue(pending['image_summary'])
            self.assertFalse(read_task('bobby'))
            r=self.call('POST','/agent/chat',{'message':'19.80元'})
            pid=r.json()['proposal_id'];self.assertTrue(pid,r.text)
            draft=self.call('GET','/agent/proposals/'+pid).json()
            self.assertEqual(draft['payload']['receipts'],[pending['image_ref']])
            self.assertEqual(draft['payload']['title'],'跨轮票据')
            self.assertEqual(draft['payload']['amount'],'19.80')
            self.assertFalse(read_task('alice'))
        self.assertEqual(len(self.call('GET','/records').json()),before)

    def test_13_new_task_and_clear_do_not_reuse_image(self):
        from agent_tasks import merge_task,prepare_task,write_task,read_task,is_new_request
        old={'fields':{'kind':'expense','title':'旧事项','amount':'10','category':'交通'},'image_ref':'old.png'}
        fresh=merge_task(old,{'kind':'expense','title':'另一笔'},'new_task')
        self.assertNotIn('image_ref',fresh)
        _,missing,_=prepare_task(fresh,m.Entry)
        self.assertIn('amount',missing);self.assertIn('receipts',missing)
        write_task('alice',old);self.call('DELETE','/agent/context');self.assertFalse(read_task('alice'))
        self.assertFalse(is_new_request('金额还要改成38.50元'))
        intent=m.normalize_intent({'skill':'unknown'},'再开一笔新的报销')
        self.assertEqual(intent.skill,'create_entry');self.assertEqual(intent.partial['kind'],'expense')
        write_task('alice',old)
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake'}),patch.object(m.httpx,'post',return_value=self.model_reply({'skill':'unknown'})) as request:
            r=self.call('POST','/agent/chat',{'message':'再开一笔新的报销'})
            self.assertIn('amount',r.json()['missing_fields']);self.assertIn('receipts',r.json()['missing_fields'])
            sent=request.call_args.kwargs['json']['messages']
            self.assertEqual(len(sent),2)
            self.assertNotIn('old.png',sent[0]['content'])

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    import hashlib
    report={'timestamp':datetime.now(timezone.utc).isoformat(), 'groups':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'success':result.wasSuccessful(),
        'source_sha256':hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
        'scope':'isolated SQLite; concurrency, privacy, boundaries, receipts, recovery, draft versions, Redis context when available'}
    (Path(__file__).parent/'v13-unit-result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    sys.exit(0 if result.wasSuccessful() else 1)
