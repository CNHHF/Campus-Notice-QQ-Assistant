import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawl_schedule import read_interval,write_interval,validate_interval
class CrawlScheduleTests(unittest.TestCase):
 def test_bounds_and_types(self):
  for value in (9,181,True,'60',60.5,None):
   with self.assertRaises(ValueError):validate_interval(value)
  self.assertEqual(validate_interval(10),10)
  self.assertEqual(validate_interval(180),180)
 def test_preserves_other_configuration(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json';p.write_text(json.dumps({'target':'private','site_cookies':{'a':'secret'},'interval_minutes':60}))
   self.assertEqual(write_interval(p,120),{'interval_minutes':120})
   data=json.loads(p.read_text());self.assertEqual(data['site_cookies'],{'a':'secret'});self.assertEqual(data['target'],'private');self.assertEqual(read_interval(p),120)
   with self.assertRaises(ValueError):write_interval(p,1)
   self.assertEqual(read_interval(p),120)
 def test_dynamic_wait_reloads_interval(self):
  from test_weixin_limit import b
  with patch.object(b,'load_config',side_effect=[{'interval_minutes':120},{'interval_minutes':60}]),patch.object(b,'save_json'),patch.object(b.time,'monotonic',side_effect=[0,3599,3601]),patch.object(b.time,'sleep') as sleep:
   b.wait_for_next_round()
   sleep.assert_called_once_with(5)
 def test_missing_config_is_not_created(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'missing.json'
   with self.assertRaises(ValueError):write_interval(p,120)
   self.assertFalse(p.exists())
