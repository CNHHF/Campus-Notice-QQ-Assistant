import unittest
from unittest.mock import patch
import test_service
from inbox import listing,detail,update,plain
class InboxTests(unittest.TestCase):
 setUp=test_service.ServiceTests.setUp
 tearDown=test_service.ServiceTests.tearDown
 insert=test_service.ServiceTests.insert
 def test_read_star_and_counts_are_independent_and_persist(self):
  self.assertEqual(listing(self.service,{})['counts'],{'all':1,'unread':1,'starred':0})
  update(self.service,{'url':'https://school.example/old','read':True})
  update(self.service,{'url':'https://school.example/old','starred':True})
  row=detail(self.service,'https://school.example/old');self.assertTrue(row['read']);self.assertTrue(row['starred'])
  self.assertEqual(listing(self.service,{'folder':'unread'})['total'],0)
  self.assertEqual(listing(self.service,{'folder':'starred'})['total'],1)
  self.assertEqual(self.sent,[])
 def test_pagination_search_and_category(self):
  for i in range(25):self.insert('new'+str(i),'奖学金'+str(i))
  result=listing(self.service,{'q':'奖学金','category':'money','offset':'20'})
  self.assertEqual(result['total'],26);self.assertEqual(len(result['items']),6);self.assertFalse(result['has_more']);self.assertNotIn('body',result['items'][0])
 def test_validation_and_no_arbitrary_url_fetch(self):
  with self.assertRaises(ValueError):detail(self.service,'https://external.example/anything')
  with self.assertRaises(ValueError):update(self.service,{'url':'https://school.example/old','read':'false'})
  with self.assertRaises(ValueError):listing(self.service,{'start':'2026-02-30'})
  with self.assertRaises(ValueError):listing(self.service,{'folder':'anything'})
 def test_markup_is_returned_as_text_not_active_html(self):
  self.assertEqual(plain('<p>正文</p><script>alert(1)</script><p>第二段</p>'),'正文\n\n第二段')
