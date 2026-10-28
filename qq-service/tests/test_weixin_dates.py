import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta

root = Path(__file__).resolve().parents[2]
path = root / ('weixin-bridge' if (root/'weixin-bridge').exists() else 'bridge') / 'bridge.py'
spec = importlib.util.spec_from_file_location('bridge_date_tests', path)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class DateProtectionTests(unittest.TestCase):
    def test_newly_exposed_archives_are_not_pushed(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/'radar.db'
            with sqlite3.connect(db) as con:
                con.execute('CREATE TABLE items(url,title,digest,source_name,pub_date,deadline,category,category_name,doc_type,audience,score,first_seen)')
                for key, day in [('empty',''),('bad','2026-02-30'),('future',str(date.today()+timedelta(days=1))),('old',str(date.today()-timedelta(days=31))),('today',str(date.today()))]:
                    con.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(key,key,'','test',day,'','other','','','',0,str(date.today())))
            con.close()
            self.assertEqual([x['url'] for x in bridge.fetch_new_items(str(db),set(),{})],['today'])
            self.assertEqual({x['url'] for x in bridge.fetch_new_items(str(db),set(),{'max_age_days':0})},{'today','old'})

if __name__=='__main__':unittest.main()
