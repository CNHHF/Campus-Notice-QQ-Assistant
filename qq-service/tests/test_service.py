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
        policy_patch=patch.object(app,'read_policy',return_value={'qq_push_paused':False})
        policy_patch.start();self.addCleanup(policy_patch.stop)
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

    def test_gateway_cold_start_is_pending_then_expires(self):
        import time
        report=self.service.data/'startup-status.json'
        report.write_text(json.dumps({'phase':'starting','started_epoch':time.time(),'bridge_pid':0}),encoding='utf-8')
        with patch.object(app.socket,'create_connection',side_effect=OSError):
            self.assertTrue(self.service.services_status()['starting'])
            report.write_text(json.dumps({'phase':'starting','started_epoch':time.time()-400,'bridge_pid':0}),encoding='utf-8')
            self.assertFalse(self.service.services_status()['starting'])

    def test_qq_webui_ready_is_waiting_for_login_not_stopped(self):
        self.service.onebot=lambda *_: (_ for _ in ()).throw(app.ExplicitFailure('QQ 客户端尚未启动'))
        with patch.object(app.socket,'create_connection'):
            result=app.Service.probe(self.service)
        self.assertFalse(result['connected'])
        self.assertIn('等待登录',result['message'])

    def test_start_services_is_single_flight_and_reports_failure(self):
        with patch.object(app.subprocess, 'Popen') as launch, patch.object(app.os, 'name', 'nt'):
            launch.return_value.poll.return_value = None
            self.service.start_services()
            self.service.start_services()
            self.assertEqual(launch.call_count, 1)
            args = launch.call_args.args[0]
            self.assertEqual(args[:3], ['powershell.exe','-NoProfile','-File'])
            self.assertTrue(args[3].endswith('start-services.ps1'))
            launch.return_value.poll.return_value = 1
            self.assertIn('启动未完成', self.service.services_status()['error'])
            self.service.start_services()
            self.assertEqual(launch.call_count, 2)


    def test_new_config_marks_first_notice_and_retains_random_token(self):
        marker=self.service.data/'admin-token-notice.pending'
        self.assertTrue(marker.exists())
        token=self.service.snapshot()['admin_token']
        marker.unlink()
        again=app.Service(self.service.data,self.radar)
        self.assertEqual(again.snapshot()['admin_token'],token)
        self.assertFalse(marker.exists())
        other=app.Service(self.base/'other-runtime',self.radar)
        self.assertNotEqual(other.snapshot()['admin_token'],token)

    def test_search_source_date_and_pagination(self):
        self.insert('start','筛选通知','2026-10-01')
        self.insert('end','筛选通知','2026-10-15')
        self.insert('outside','筛选通知','2026-09-30')
        self.insert('unknown','筛选通知','')
        with self.service.connect() as db:
            pass
        with closing(sqlite3.connect(self.radar)) as db,db:
            db.execute("UPDATE items SET source_name='信息技术部' WHERE url LIKE '%/end'")
        found=self.service.search(['筛选'],source='学院',start='2026-10-01',end='2026-10-15')
        self.assertEqual([r['url'].split('/')[-1] for r in found],['start'])
        found=self.service.search(['筛选'],source='信息技术部',start='2026-10-15',end='2026-10-15')
        self.assertEqual(len(found),1)
        self.assertEqual(self.service.search([],source="学院' OR 1=1 --"),[])
        first=self.service.search([],limit=2)
        second=self.service.search([],limit=2,offset=2)
        self.assertFalse({r['url'] for r in first}&{r['url'] for r in second})
        for args in [{'start':'2026-11-01','end':'2026-10-01'},{'start':'2026-02-30'}]:
            with self.assertRaises(ValueError): self.service.search([],**args)

    def test_offtopic_private_and_mentioned_group_use_exact_prompt(self):
        for kind in ('private','group'):
            for text in ('你好','今天天气怎么样','帮我写代码','hello','你是谁',''):
                parts=[{'type':'text','data':{'text':text}}]
                if kind=='group':parts.insert(0,{'type':'at','data':{'qq':'12345678'}})
                parsed=self.service.parse_event(self.event(parts,kind),self.service.snapshot())
                self.assertIsNotNone(parsed)
                with patch.object(self.service,'query_plan',side_effect=AssertionError('no model for obvious chatter')):
                    self.assertEqual(self.service.answer(parsed),'请说出您要查询的通知')
                self.assertNotIn(parsed['key'],self.service.context)

    def test_model_rejected_topic_uses_exact_prompt_and_query_still_works(self):
        parsed={'key':'private:23456789','text':'谈谈人生的意义'}
        with patch.object(self.service,'query_plan',return_value={'scope':False}):
            self.assertEqual(self.service.answer(parsed),'请说出您要查询的通知')
        parsed['text']='查通知 奖学金'
        self.assertIn('既有奖学金通知',self.service.answer(parsed))
        parsed['text']='你好'
        self.assertEqual(self.service.answer(parsed),'请说出您要查询的通知')
        parsed['text']='第1条详情'
        self.assertIn('既有奖学金通知',self.service.answer(parsed))

    def test_manual_batch_supports_fifty_notices(self):
        urls=[]
        for i in range(50):
            self.insert('batch'+str(i),'批量通知'+str(i))
            urls.append('https://school.example/batch'+str(i))
        targets=[{'kind':'private','id':'23456789'}]
        result=self.service.manual_preview({'urls':urls,'targets':targets})
        self.assertEqual(len(result['items']),50)
        self.assertEqual(self.sent,[])
        with self.assertRaises(ValueError):
            self.service.manual_preview({'urls':urls+['https://school.example/old'],'targets':targets})

    def manual(self, targets=None):
        return self.service.manual_preview({'urls':['https://school.example/old'], 'targets': targets or [{'kind':'group','id':'34567890'},{'kind':'private','id':'23456789'}]})

    def test_manual_preview_does_not_send_and_rejects_arbitrary_targets(self):
        batch=self.manual()
        self.assertEqual(len(batch['items']),2)
        self.assertEqual(self.sent,[])
        with self.assertRaises(ValueError):
            self.manual([{'kind':'private','id':'99999999'}])
        with self.assertRaises(ValueError):
            self.service.manual_preview({'urls':['https://external.example/fake'],'targets':[{'kind':'group','id':'34567890'}]})
        self.assertTrue(all('https://school.example/old' in x['message'] and '\n' not in x['message'] for x in batch['items']))

    def test_manual_confirmation_idempotent_and_shared_group_dedup(self):
        batch=self.manual()['batch']
        with patch.object(app.threading,'Thread') as thread:
            self.service.manual_send(batch)
            self.service.manual_send(batch)
            self.assertEqual(thread.call_count,1)
        self.service.manual_worker(batch)
        self.assertEqual(len(self.sent),2)
        self.assertEqual({x[0] for x in self.sent},{'send_group_msg','send_private_msg'})
        self.assertTrue(all(x['status']=='sent' for x in self.service.manual_status(batch)['items']))
        self.assertTrue(all(x['status']=='wait_resend' for x in self.manual()['items']))
        self.service.push_round()
        self.assertEqual(len(self.sent),2)

    def test_resend_requires_explicit_confirmation_and_stays_idempotent(self):
        targets=[{'kind':'group','id':'34567890'}]
        first=self.manual(targets)['batch']
        with patch.object(app.threading,'Thread'):self.service.manual_send(first)
        self.service.manual_worker(first)
        second=self.manual(targets)
        self.assertEqual(second['items'][0]['status'],'wait_resend')
        with self.assertRaises(ValueError):self.service.manual_send(second['batch'])
        self.assertEqual(len(self.sent),1)
        with patch.object(app.threading,'Thread'):
            self.service.manual_send(second['batch'],True)
            self.service.manual_send(second['batch'],True)
        self.service.manual_worker(second['batch'])
        self.service.manual_worker(second['batch'])
        self.assertEqual(len(self.sent),2)

    def test_resend_does_not_override_uncertain_or_concurrent_work(self):
        targets=[{'kind':'group','id':'34567890'}]
        first=self.manual(targets)['batch']
        with patch.object(app.threading,'Thread'):self.service.manual_send(first)
        self.service.manual_worker(first)
        second=self.manual(targets)['batch']
        with patch.object(app.threading,'Thread'):self.service.manual_send(second,True)
        with self.service.connect() as db:
            db.execute("UPDATE deliveries SET status='uncertain' WHERE group_id='34567890'")
        self.service.manual_worker(second)
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.service.manual_status(second)['items'][0]['status'],'skipped')

    def test_manual_uncertain_never_automatically_retries(self):
        batch=self.manual([{'kind':'group','id':'34567890'}])['batch']
        with patch.object(app.threading,'Thread'):
            self.service.manual_send(batch)
        def fail(*args): raise app.AmbiguousDelivery('timeout')
        self.service.onebot=fail
        self.service.manual_worker(batch)
        self.assertEqual(self.service.manual_status(batch)['items'][0]['status'],'uncertain')
        self.assertEqual(self.manual([{'kind':'group','id':'34567890'}])['items'][0]['status'],'skipped')
        self.service.push_round()

    def test_manual_revalidates_permissions_and_auto_delivery_after_preview(self):
        batch=self.manual([{'kind':'private','id':'23456789'}])['batch']
        cfg=self.service.snapshot();cfg['private_users']=[];self.service.save_config(cfg)
        with self.assertRaises(ValueError): self.service.manual_send(batch)
        batch=self.manual([{'kind':'group','id':'34567890'}])['batch']
        with patch.object(app.threading,'Thread'): self.service.manual_send(batch)
        with self.service.connect() as db: db.execute("UPDATE deliveries SET status='sent' WHERE group_id='34567890'")
        self.service.manual_worker(batch)
        self.assertEqual(self.service.manual_status(batch)['items'][0]['status'],'skipped')
        self.assertEqual(self.sent,[])



class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=app.Service(Path(self.temp.name)/'runtime',Path(self.temp.name)/'missing.db')
        self.service.probe=lambda: {'connected':False}
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
        self.assertEqual(self.request('/workbench/')[0],401)
        self.assertEqual(self.request('/workbench/api/items')[0],401)
        self.assertEqual(self.request('/api/onebot-config')[0],401)
        self.assertEqual(self.request('/api/manual/preview',{}, {'Content-Type':'application/json'})[0],401)
        self.assertEqual(self.request('/api/manual/send',{}, {'Content-Type':'application/json'})[0],401)
        self.assertEqual(self.request('/api/manual/status?batch=unknown')[0],401)
        self.assertEqual(self.request('/api/weixin/qr')[0],401)
        self.assertEqual(self.request('/api/weixin/start',{}, {'Content-Type':'application/json'})[0],401)
        h={'Authorization':'Bearer '+self.service.snapshot()['admin_token']}
        status,result=self.request('/api/state',headers=h)
        self.assertEqual(status,200);self.assertFalse(result['radar']['ready'])

    def test_start_services_requires_admin_and_same_origin(self):
        with patch.object(self.service, 'start_services', return_value={'message':'started'}) as start:
            h={'Content-Type':'application/json'}
            self.assertEqual(self.request('/api/services/start',{},h)[0],401)
            h['Authorization']='Bearer '+self.service.snapshot()['admin_token']
            h['Origin']='https://foreign.example'
            self.assertEqual(self.request('/api/services/start',{},h)[0],403)
            start.assert_not_called()
            del h['Origin']
            self.assertEqual(self.request('/api/services/start',{},h),(200,{'message':'started'}))
            start.assert_called_once_with()

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
