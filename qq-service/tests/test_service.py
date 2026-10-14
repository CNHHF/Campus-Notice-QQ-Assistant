import importlib.util
import http.client
import hmac
import hashlib
import sys
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

path = Path(__file__).resolve().parents[1] / 'app.py'
sys.path.insert(0,str(path.parent))
spec = importlib.util.spec_from_file_location('campus_qq', path)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.radar = self.base / 'radar.db'
        with closing(sqlite3.connect(self.radar)) as db, db:
            db.execute('CREATE TABLE items(url TEXT PRIMARY KEY,title TEXT,digest TEXT,body TEXT,source_name TEXT,pub_date TEXT,deadline TEXT,category TEXT,category_name TEXT,audience TEXT,first_seen TEXT,score REAL)')
        self.insert('old', '既有奖学金通知')
        self.service = app.Service(self.base / 'runtime', self.radar)
        self.service.model_key = lambda: ''  # Isolated tests never use the machine's real provider key.
        cfg = self.service.snapshot()
        cfg.update(bot_qq='12345678', private_users=[{'id':'23456789','enabled':True}], groups=[{'id':'34567890','enabled':True,'push':True}])
        self.service.save_config(cfg)
        self.sent = []
        self.service.probe = lambda: {'connected':True}
        self.service.stop.wait = lambda _: False
        self.service.onebot = lambda action, data: self.sent.append((action, data)) or {'message_id':1}
        self.service.push_filters = lambda: {'exclude_categories':['jobstart'], 'exclude_keywords':['招聘'], 'max_age_days':30, 'categories':[], 'min_score':0, 'quiet_hours':[]}

    def tearDown(self):
        self.temp.cleanup()

    def insert(self, url, title, date=None, category='money'):
        date = datetime.now().strftime('%Y-%m-%d') if date is None else date
        with closing(sqlite3.connect(self.radar)) as db, db:
            db.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                ('https://school.example/'+url,title,'摘要','正文','学院',date,'',category,'分类','学生',app.stamp(),1))

    def event(self, message=None, kind='group', user='23456789', group='34567890'):
        return {'post_type':'message','message_type':kind,'self_id':12345678,'user_id':int(user),'group_id':int(group),'message_id':101,
                'message':message if message is not None else [{'type':'at','data':{'qq':'12345678'}},{'type':'text','data':{'text':'查通知 奖学金'}}]}

    def statuses(self):
        with self.service.connect() as db:
            return {r['title']:r['status'] for r in db.execute('SELECT title,status FROM deliveries')}

    def test_only_real_at_enters_queue(self):
        cfg = self.service.snapshot()
        for parts in (
            [{'type':'text','data':{'text':'@12345678 查通知 奖学金'}}],
            [{'type':'reply','data':{'id':'1'}},{'type':'text','data':{'text':'查通知 奖学金'}}],
            [{'type':'at','data':{'qq':'all'}},{'type':'text','data':{'text':'查通知 奖学金'}}],
            [{'type':'at','data':{'qq':'99999999'}},{'type':'text','data':{'text':'查通知 奖学金'}}],
        ):
            self.assertIsNone(app.Service.parse_event(self.event(parts),cfg))
        self.assertIsNotNone(app.Service.parse_event(self.event(),cfg))
        self.assertFalse(self.service.accept_event(self.event([{'type':'text','data':{'text':'普通聊天'}}])))
        self.assertEqual(self.service.jobs.qsize(),0)
        self.assertEqual(self.service.context,{})

    def test_group_whitelist_and_bot_identity(self):
        cfg = self.service.snapshot()
        self.assertIsNone(app.Service.parse_event(self.event(group='99999999'),cfg))
        event = self.event();event['self_id']=99999999
        self.assertIsNone(app.Service.parse_event(event,cfg))
        event = self.event();event['message']='[CQ:at,qq=12345678]查通知'
        self.assertIsNone(app.Service.parse_event(event,cfg))

    def test_private_permissions_and_revocation(self):
        parts=[{'type':'text','data':{'text':'查通知 奖学金'}}]
        cfg = self.service.snapshot()
        self.assertIsNotNone(app.Service.parse_event(self.event(parts,'private'),cfg))
        self.assertIsNone(app.Service.parse_event(self.event(parts,'private',user='99999999'),cfg))
        parsed=app.Service.parse_event(self.event(parts,'private'),cfg)
        cfg['private_users']=[];self.service.save_config(cfg)
        self.service.send_reply(parsed,'test')
        self.assertEqual(self.sent,[])

    def test_context_is_per_user_per_group_and_expires(self):
        a={'key':'34567890:23456789','text':'查通知 奖学金'}
        self.assertIn('既有奖学金',self.service.answer(a))
        a['text']='第1条详情';self.assertIn('正文',self.service.answer(a))
        b={'key':'34567890:99999999','text':'第1条详情'}
        self.assertNotIn('正文',self.service.answer(b))
        self.service.context[a['key']]['at']-=1201
        self.assertNotIn('正文',self.service.answer(a))

    def test_event_replay_is_ignored(self):
        self.assertTrue(self.service.accept_event(self.event()))
        self.assertFalse(self.service.accept_event(self.event()))
        self.assertEqual(self.service.jobs.qsize(),1)

    def test_new_group_baseline_and_title_dedup(self):
        self.service.push_round();self.assertEqual(self.sent,[])
        self.insert('new-a','新的评优通知');self.insert('new-b','新的评优通知')
        self.service.push_round();self.service.push_round()
        self.assertEqual(len(self.sent),1)
        message=self.sent[0][1]['message'][0]['data']['text']
        self.assertIn('https://school.example/',message)
        self.assertNotIn('\n',message)

    def test_filters_hold_archives_unknown_dates_jobs(self):
        self.insert('archive','历史通知',date='2016-01-01')
        self.insert('unknown','未知日期通知',date='')
        self.insert('future','未来通知',date=(datetime.now()+timedelta(days=3)).strftime('%Y-%m-%d'))
        self.insert('job','招聘活动通知')
        self.insert('category','企业活动',category='jobstart')
        self.insert('good','正常新通知')
        self.service.push_round()
        self.assertEqual(len(self.sent),1)
        self.assertIn('正常新通知',self.sent[0][1]['message'][0]['data']['text'])

    def test_timeout_is_not_retried_and_survives_restart(self):
        self.insert('new','不确定送达通知')
        def ambiguous(*_):
            raise app.AmbiguousDelivery('timeout')
        self.service.onebot=ambiguous
        self.service.push_round();self.assertEqual(self.statuses()['不确定送达通知'],'uncertain')
        calls=[];self.service.onebot=lambda *args:calls.append(args)
        self.service.push_round();self.assertEqual(calls,[])
        restarted=app.Service(self.base/'runtime',self.radar)
        with restarted.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM deliveries WHERE title='不确定送达通知'").fetchone()[0],'uncertain')

    def test_crash_in_flight_is_uncertain(self):
        with self.service.connect() as db:
            db.execute("INSERT INTO deliveries(group_id,fingerprint,title,url,message,status,updated) VALUES('34567890','crash','中断','url','text','sending',?)",(app.stamp(),))
        app.Service(self.base/'runtime',self.radar)
        self.assertEqual(self.statuses()['中断'],'uncertain')

    def test_explicit_failure_can_retry(self):
        self.insert('new','明确失败通知')
        self.service.onebot=lambda *_: (_ for _ in ()).throw(app.ExplicitFailure('failed'))
        self.service.push_round();self.assertEqual(self.statuses()['明确失败通知'],'failed')
        self.service.onebot=lambda action,data: self.sent.append(data) or {'message_id':1}
        self.service.push_round();self.assertEqual(len(self.sent),1)
        self.assertEqual(self.statuses()['明确失败通知'],'sent')

    def test_disabled_push_and_group_revocation(self):
        self.insert('new','新通知')
        cfg=self.service.snapshot();cfg['groups'][0]['push']=False;self.service.save_config(cfg)
        self.service.push_round();self.assertEqual(self.sent,[])
        cfg['groups'][0]['enabled']=False;self.service.save_config(cfg)
        self.assertIsNone(app.Service.parse_event(self.event(),self.service.snapshot()))

    def test_search_injection_and_literal_wildcard(self):
        self.assertEqual(self.service.search(["%' OR 1=1 --"]),[])
        self.assertEqual(self.service.search(['%']),[])
        self.assertEqual(len(self.service.search(['奖学金'])),1)

    def test_secret_never_in_public_state(self):
        cfg=self.service.snapshot();cfg['deepseek_key']='secret-deepseek-value';self.service.save_config(cfg)
        output=json.dumps(self.service.public_state())
        self.assertNotIn(self.service.config['admin_token'],output)
        self.assertNotIn(self.service.config['onebot_token'],output)
        self.assertNotIn('secret-deepseek-value',output)

    def test_multiple_group_baselines(self):
        cfg=self.service.snapshot();cfg['groups'].append({'id':'45678901','enabled':True,'push':True});self.service.save_config(cfg)
        self.insert('new','多群新通知')
        self.service.push_round();self.assertEqual(len(self.sent),2)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=app.Service(Path(self.temp.name)/'runtime',Path(self.temp.name)/'missing.db')
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.make_handler(self.service))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,payload=None,headers=None):
        req=urllib.request.Request(self.url+path,data=None if payload is None else json.dumps(payload).encode(),headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status,json.load(r)
        except urllib.error.HTTPError as e:
            return e.code,json.load(e)

    def test_admin_auth_required(self):
        self.assertEqual(self.request('/api/state')[0],401)
        self.assertEqual(self.request('/api/onebot-config')[0],401)
        self.assertEqual(self.request('/api/weixin/qr')[0],401)
        self.assertEqual(self.request('/api/weixin/start',{}, {'Content-Type':'application/json'})[0],401)
        h={'Authorization':'Bearer '+self.service.snapshot()['admin_token']}
        status,result=self.request('/api/state',headers=h)
        self.assertEqual(status,200);self.assertFalse(result['radar']['ready'])

    def test_webhook_auth_and_cross_site_modification(self):
        self.assertEqual(self.request('/onebot/events',{'post_type':'message'})[0],401)
        cfg=self.service.snapshot()
        h={'Authorization':'Bearer '+cfg['onebot_token']}
        self.assertEqual(self.request('/onebot/events',{'post_type':'meta_event'},h)[0],200)
        h={'Authorization':'Bearer '+cfg['admin_token'],'Content-Type':'application/json','Origin':'https://foreign.example'}
        self.assertEqual(self.request('/api/config',cfg,h)[0],403)

    def test_napcat_signed_chunked_message_enters_query_queue(self):
        cfg=self.service.snapshot()
        cfg.update(bot_qq='12345678',private_users=[{'id':'23456789','enabled':True}])
        self.service.save_config(cfg)
        event={'post_type':'message','message_type':'private','self_id':12345678,'user_id':23456789,'message_id':991,'message':[{'type':'text','data':{'text':'查通知 奖学金'}}]}
        raw=json.dumps(event,ensure_ascii=False,separators=(',',':')).encode()
        signature='sha1='+hmac.new(cfg['onebot_token'].encode(),raw,hashlib.sha1).hexdigest()
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        try:
            connection.request('POST','/onebot/events',body=iter([raw[:17],raw[17:61],raw[61:]]),headers={'Content-Type':'application/json','X-Signature':signature},encode_chunked=True)
            response=connection.getresponse()
            self.assertEqual(response.status,200)
            self.assertTrue(json.loads(response.read())['accepted'])
            self.assertEqual(self.service.jobs.qsize(),1)
        finally:
            connection.close()

    def test_config_validation_and_dns_rebinding(self):
        cfg=self.service.snapshot();cfg['onebot_url']='http://external.example'
        h={'Authorization':'Bearer '+cfg['admin_token'],'Content-Type':'application/json'}
        self.assertEqual(self.request('/api/config',cfg,h)[0],400)
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)


if __name__=='__main__':
    unittest.main()
