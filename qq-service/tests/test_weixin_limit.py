import importlib.util, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[2]
bridge=root/('weixin-bridge' if (root/'weixin-bridge').is_dir() else 'bridge')/'bridge.py'
spec=importlib.util.spec_from_file_location('wxbridge',bridge)
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class WeixinLimitTests(unittest.TestCase):
 def run_case(self, outcomes):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
  items=[{'url':f'https://example.org/{i}','title':str(i)} for i in range(4)]
  state={'started_once':True,'sent_urls':[]}
  with patch.object(b,'load_config',return_value={}),patch.object(b,'BASE_DIR',Path(temp.name)),patch.object(b,'STATE_PATH',Path(temp.name)/'state.json'),patch.object(b,'log'),patch.object(b,'radar_alive',return_value=True),patch.object(b,'trigger_crawl'),patch.object(b,'wait_crawl_done'),patch.object(b,'fetch_new_items',return_value=items),patch.object(b,'format_message',return_value='single line'),patch.object(b,'send_wechat',side_effect=outcomes) as send,patch.object(b.time,'sleep'):
   b.run_round({'radar_base':'local','radar_db':'mock'},state,False)
   health=b.load_json(Path(temp.name)/'push-health.json',{})
  return state,send.call_count,health
 def test_consecutive_rejections_stop_and_preserve_pending(self):
  state,n,h=self.run_case([('fail','ret=-2 prepare failed')]*2)
  self.assertEqual(n,2);self.assertEqual(state['sent_urls'],[]);self.assertEqual(h['status'],'restricted');self.assertEqual(h['pending'],4)
 def test_success_resets_streak_timeout_still_deduplicated(self):
  state,n,h=self.run_case([('fail','prepare failed'),('ok','sent'),('fail','prepare failed'),('timeout','late')])
  self.assertEqual(n,4);self.assertEqual(state['sent_urls'],['https://example.org/1','https://example.org/3'])
if __name__=='__main__':unittest.main()
