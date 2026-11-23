from contextlib import closing
from datetime import date, timedelta
import asyncio
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import official_bot
from campus_notice import CampusNotice


class OfficialBotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.radar = self.root / 'radar.db'
        with closing(sqlite3.connect(self.radar)) as db, db:
            db.execute('CREATE TABLE items(url TEXT PRIMARY KEY,title TEXT,digest TEXT,body TEXT,source_name TEXT,pub_date TEXT,deadline TEXT,category TEXT,category_name TEXT,audience TEXT,first_seen TEXT,score REAL)')
        self.add('旧通知', 'old')
        self.service = app.Service(self.root/'runtime', self.radar)
        self.service.model_key = lambda: 'fixture-model-secret'
        self.path = self.service.data/'official-qq.json'
        self.path.write_text(json.dumps({'app_id':'123456789','secret':'fixture-bot-secret','allow_from':['*']}),encoding='utf-8')
        self.bot = official_bot.OfficialBot(self.service)
        self.bot.notice.root = self.root
        self.notice = self.bot.notice
        (self.root/'weixin-bridge').mkdir()
        (self.root/'weixin-bridge/bridge-config.json').write_text(json.dumps({'exclude_categories':['jobstart'],'exclude_keywords':['招聘'],'max_age_days':30}),encoding='utf-8')
        self.mock = patch.object(official_bot, '_runtime', self.bot)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def tearDown(self):
        self.temp.cleanup()

    def add(self, title, url, category='teachrun', days=0):
        day = (date.today()-timedelta(days=days)).isoformat()
        with closing(sqlite3.connect(self.radar)) as db, db:
            db.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('https://school.test/'+url,title,'摘要','真实正文','学院',day,'',category,'教学','学生',day,1))

    def test_desktop_filters_preview_and_push(self):
        filters={'sources':['学院'],'categories':['teachrun'],'keywords':['竞赛','奖学金']}
        official_bot.save_subscription({'kind':'group','target':'GROUP_OPENID','label':'竞赛提醒','filters':filters})
        self.add('竞赛报名','competition')
        self.add('奖学金申请','award')
        self.add('普通会议','meeting')
        self.add('竞赛招聘','recruit')
        before=self.notice.dashboard()['stats']
        preview=official_bot.preview_subscription({'filters':filters})
        self.assertEqual(preview['total'],2)
        self.assertFalse(preview['will_send'])
        self.assertEqual(before,self.notice.dashboard()['stats'])
        send=AsyncMock(return_value={'id':'receipt'})
        with patch('asyncio.sleep',new=AsyncMock()):
            asyncio.run(self.notice.push_once(send,lambda _:True))
        self.assertEqual(send.await_count,2)

    def test_label_edit_keeps_pending_but_content_edit_baselines(self):
        self.notice.subscribe('group','GROUP_OPENID')
        self.add('待推通知','pending')
        self.notice.save_subscription('group','GROUP_OPENID',label='新备注',filters={})
        send=AsyncMock(return_value={'id':'receipt'})
        with patch('asyncio.sleep',new=AsyncMock()):
            asyncio.run(self.notice.push_once(send,lambda _:True))
        self.assertEqual(send.await_count,1)
        self.add('竞赛通知','later')
        self.notice.save_subscription('group','GROUP_OPENID',filters={'keywords':['竞赛']})
        asyncio.run(self.notice.push_once(send,lambda _:True))
        self.assertEqual(send.await_count,1)

    def test_resume_baselines_pause_period(self):
        self.notice.subscribe('group','GROUP_OPENID')
        self.notice.pause_subscription('group','GROUP_OPENID')
        self.add('暂停期间通知','paused')
        self.notice.save_subscription('group','GROUP_OPENID',enabled=True)
        send=AsyncMock()
        asyncio.run(self.notice.push_once(send,lambda _:True))
        send.assert_not_awaited()

    def test_contacts_and_invalid_subscription_inputs(self):
        self.notice.record_contact('group','GROUP_OPENID')
        self.assertEqual(self.notice.dashboard()['contacts'][0]['target'],'GROUP_OPENID')
        for value in ({'categories':['invalid']},{'keywords':'string'}):
            with self.assertRaises(ValueError):self.notice.preview(value)
        with self.assertRaises(ValueError):self.notice.save_subscription('group','123456789')
        self.assertFalse(self.notice.matches({'source_name':'其他','category':'teachrun','title':'竞赛'},self.notice.normalize_filters({'sources':['学院'],'keywords':['竞赛']})))

    def test_dashboard_never_returns_secrets(self):
        encoded=json.dumps(self.bot.dashboard())
        self.assertNotIn('fixture-model-secret',encoded)
        self.assertNotIn('fixture-bot-secret',encoded)

    def test_empty_secret_preserves_existing(self):
        official_bot.save({'app_id':'123456789','secret':'','allow_all':True})
        self.assertEqual(self.bot.config()['secret'],'fixture-bot-secret')

    def test_allowlist_can_be_managed_without_external_ui(self):
        official_bot.save({'app_id':'123456789','allow_all':False,'allow_from':['OWNER_OPENID']})
        self.assertTrue(self.bot.allowed('OWNER_OPENID'))
        self.assertFalse(self.bot.allowed('another-user'))

    def test_empty_restricted_allowlist_rejected(self):
        with self.assertRaises(ValueError):official_bot.save({'app_id':'123456789','allow_all':False,'allow_from':[]})

    def test_invalid_appid_rejected(self):
        with self.assertRaises(ValueError):official_bot.save({'app_id':'https://bad.test','allow_all':True})

    def test_model_config_stays_in_this_project(self):
        official_bot.save_model({'model':'deepseek-flash','api_key':'new-private-key'})
        stored=json.loads((self.service.data/'config.json').read_text(encoding='utf-8'))
        self.assertEqual(stored['deepseek_key'],'new-private-key')

    def test_native_mode_does_not_read_other_provider_stores(self):
        self.service.model_key=app.Service.model_key.__get__(self.service)
        self.service.config.pop('deepseek_key',None)
        with patch.dict('os.environ',{},clear=True),patch.object(Path,'read_text',side_effect=AssertionError('External credential store read')):
            self.assertEqual(self.service.model_key(),'')

    def test_greeting_and_programming_are_notice_only(self):
        for text in ('你好','写一段代码'):
            self.assertEqual(self.notice.answer('c2c','a','a',text),'请说出您要查询的通知')

    def test_search_and_numbered_followup(self):
        self.assertIn('https://school.test/old',self.notice.answer('group','g','a','最新通知'))
        self.assertIn('真实正文',self.notice.answer('group','g','a','第1条详情'))

    def test_subscribe_does_not_send_history(self):
        self.notice.subscribe('c2c','a')
        send=AsyncMock()
        asyncio.run(self.notice.push_once(send,lambda _:True))
        send.assert_not_awaited()

    def test_new_notice_dedup_single_line_with_link(self):
        self.notice.subscribe('c2c','a')
        self.add('新通知\n详情','new')
        self.add('新通知 详情','duplicate')
        send=AsyncMock(return_value={'id':'receipt'})
        with patch('asyncio.sleep',new=AsyncMock()):
            asyncio.run(self.notice.push_once(send,lambda _:True))
            asyncio.run(self.notice.push_once(send,lambda _:True))
        self.assertEqual(send.await_count,1)
        self.assertNotIn('\n',send.call_args.args[2])
        self.assertIn('https://school.test/',send.call_args.args[2])

    def test_future_old_and_recruitment_not_pushed(self):
        self.notice.subscribe('c2c','a')
        self.add('招聘','job')
        self.add('工作','job2',category='jobstart')
        self.add('未来','future',days=-1)
        self.add('归档','archive',days=31)
        send=AsyncMock()
        asyncio.run(self.notice.push_once(send,lambda _:True))
        send.assert_not_awaited()

    def test_uncertain_delivery_pauses_without_retry(self):
        self.notice.subscribe('c2c','a')
        self.add('新通知','new')
        send=AsyncMock(side_effect=TimeoutError())
        asyncio.run(self.notice.push_once(send,lambda _:True))
        asyncio.run(self.notice.push_once(send,lambda _:True))
        self.assertEqual(send.await_count,1)
        self.assertIn('停用',self.notice.answer('c2c','a','a','订阅状态'))

    def test_official_transport_rejects_proactive_send(self):
        with self.assertRaises(ValueError):
            asyncio.run(self.bot.send('group','GROUP_OPENID','unsupported'))

    def test_official_scheduler_never_sends(self):
        self.notice.subscribe('group','GROUP_OPENID')
        self.add('新通知','new')
        self.bot.send=AsyncMock()
        asyncio.run(self.bot.scheduler())
        self.bot.send.assert_not_awaited()

    def test_saved_filter_query_is_repeatable_and_isolated(self):
        self.notice.save_subscription('group','GROUP_OPENID',filters={'keywords':['竞赛']})
        self.add('竞赛报名','competition')
        self.add('普通会议','meeting')
        before=self.notice.dashboard()['stats']
        for _ in range(2):
            result=self.notice.answer('group','GROUP_OPENID','user','查看订阅')
            self.assertIn('竞赛报名',result)
            self.assertNotIn('普通会议',result)
            self.assertIn('https://school.test/competition',result)
        self.assertEqual(before,self.notice.dashboard()['stats'])
        self.assertIn('尚未启用',self.notice.answer('group','ANOTHER_GROUP','user','查看订阅'))

    def test_cancel_and_permission_revoke_prevent_push(self):
        self.notice.subscribe('c2c','a')
        self.notice.answer('c2c','a','a','取消订阅')
        self.add('新通知','new')
        send=AsyncMock()
        asyncio.run(self.notice.push_once(send,lambda _:False))
        send.assert_not_awaited()

    def test_native_qq_event_routes_reply_without_network(self):
        self.bot.send=AsyncMock()
        message=SimpleNamespace(id='test-message',content='<@!123456> 你好',group_openid='g',author=SimpleNamespace(member_openid='a'))
        asyncio.run(self.bot.receive(message,group=True))
        self.assertEqual(self.bot.send.call_args.args[2],'请说出您要查询的通知')

    def test_restart_preserves_uncertain_inflight_state(self):
        with self.notice.connect() as db:db.execute("INSERT INTO deliveries VALUES('c2c','a','fp','sending')")
        restored=CampusNotice(self.service,self.service.data/'official-state',root=self.root)
        with restored.connect() as db:self.assertEqual(db.execute("SELECT status FROM deliveries WHERE fp='fp'").fetchone()[0],'uncertain')


if __name__=='__main__':unittest.main()
