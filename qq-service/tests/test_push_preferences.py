import json,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import test_service
app=test_service.app
from push_preferences import write_policy,read_policy,matches_group
class PushPreferenceTests(unittest.TestCase):
 setUp=test_service.ServiceTests.setUp
 tearDown=test_service.ServiceTests.tearDown
 insert=test_service.ServiceTests.insert
 def test_paused_qq_never_queues_or_sends(self):
  self.insert('new','新通知')
  with patch.object(app,'read_policy',return_value={'qq_push_paused':True}):self.service.push_round()
  self.assertEqual(self.sent,[])
 def test_group_source_and_category_both_required(self):
  cfg=self.service.snapshot();cfg['groups'][0].update(sources=['学院'],categories=['money']);self.service.save_config(cfg)
  self.insert('match','奖学金');self.insert('wrong','会议',category='teachrun')
  self.service.push_round();self.assertEqual(len(self.sent),1)
  self.assertIn('奖学金',str(self.sent))
 def test_changed_subscription_holds_old_queued_item(self):
  self.insert('new','奖学金');self.service.probe=lambda:{'connected':False};self.service.push_round()
  cfg=self.service.snapshot();cfg['groups'][0]['sources']=['其他学院'];self.service.save_config(cfg)
  self.service.probe=lambda:{'connected':True};self.service.push_round();self.assertEqual(self.sent,[])
 def test_crawl_status_reads_only_safe_fields(self):
  with patch.object(app,'request_local',return_value=json.dumps({'last_run':'today','crawling':False,'report':{'x':{'name':'学院','status':'error','count':0,'secret':'hidden'}},'unreachable':{'y':'未接通'},'profile':{'secret':'hidden'}}).encode()):
   status=self.service.crawl_status()
  self.assertTrue(status['available']);self.assertNotIn('secret',str(status))
 def test_policy_preserves_credentials_and_validates(self):
  p=self.base/'bridge.json';p.write_text(json.dumps({'target':'secret','site_cookies':{'a':'private'}}))
  value={'exclude_keywords':['招聘'],'categories':['money'],'exclude_categories':['jobstart'],'max_age_days':30,'weixin_push_paused':True,'qq_push_paused':False}
  write_policy(p,value);self.assertEqual(json.loads(p.read_text())['target'],'secret');self.assertNotIn('target',read_policy(p))
  for bad in ({'max_age_days':0},{'categories':['invalid']},{'qq_push_paused':'false'}):
   with self.assertRaises(ValueError):write_policy(p,{**value,**bad})
 def test_paused_weixin_still_crawls_without_sending(self):
  from test_weixin_limit import b
  with patch.object(b,'radar_alive',return_value=True),patch.object(b,'trigger_crawl') as crawl,patch.object(b,'wait_crawl_done'),patch.object(b,'fetch_new_items',return_value=[{'url':'x','title':'x'}]),patch.object(b,'send_wechat') as send,patch.object(b,'log'):
   b.run_round({'radar_base':'local','radar_db':'mock','weixin_push_paused':True},{'started_once':True},False)
   crawl.assert_called_once();send.assert_not_called()
