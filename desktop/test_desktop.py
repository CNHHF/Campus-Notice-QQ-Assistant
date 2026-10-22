import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from stop_services import selected_process,safe_to_stop


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()

    def test_stop_selection_leaves_unrelated_python_and_qq_alone(self):
        self.assertFalse(selected_process({'ExecutablePath':'C:/Python/python.exe','CommandLine':'python other.py'},self.root,0))
        self.assertFalse(selected_process({'ExecutablePath':'C:/QQ/QQ.exe','CommandLine':'QQ.exe'},self.root,0))
        self.assertTrue(selected_process({'ExecutablePath':'C:/Python/python.exe','CommandLine':'python "'+str(self.root/'qq-service/app.py')+'"'},self.root,0))
        self.assertFalse(selected_process({'ExecutablePath':'C:/Python/python.exe','CommandLine':'python "'+str(self.root.parent/'other/qq-service/app.py')+'"'},self.root,0))

    def test_gateway_requires_both_known_pid_and_verified_command(self):
        row={'ProcessId':42,'ExecutablePath':'C:/Node/node.exe','CommandLine':'node C:/npm/openclaw/dist/index.js gateway'}
        self.assertTrue(selected_process(row,self.root,42))
        self.assertFalse(selected_process(row,self.root,43))
        row['CommandLine']='node other.js'
        self.assertFalse(selected_process(row,self.root,42))

    def test_in_flight_delivery_blocks_stop(self):
        folder=self.root/'qq-service/runtime';folder.mkdir(parents=True)
        with closing(sqlite3.connect(folder/'service.db')) as db:
            db.executescript("CREATE TABLE deliveries(status TEXT);CREATE TABLE manual_push(status TEXT);INSERT INTO deliveries VALUES('sending');")
            db.commit()
        self.assertFalse(safe_to_stop(self.root))
        with closing(sqlite3.connect(folder/'service.db')) as db:
            db.execute("UPDATE deliveries SET status='sent'");db.commit()
        self.assertTrue(safe_to_stop(self.root))

    def test_stop_only_during_wechat_wait_period(self):
        folder=self.root/'weixin-bridge';folder.mkdir()
        (folder/'bridge-config.json').write_text('{"interval_minutes":60}',encoding='utf-8')
        self.assertFalse(safe_to_stop(self.root))
        (folder/'crawl-schedule.json').write_text(json.dumps({'wait_started_epoch':time.time()}),encoding='utf-8')
        self.assertTrue(safe_to_stop(self.root))
        (folder/'crawl-schedule.json').write_text(json.dumps({'wait_started_epoch':time.time()-3590}),encoding='utf-8')
        self.assertFalse(safe_to_stop(self.root))


if __name__=='__main__':unittest.main()
