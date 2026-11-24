import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

path=Path(__file__).resolve().parents[2]/'bridge/bridge.py'
spec=importlib.util.spec_from_file_location('collector_under_test',path)
b=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class CollectorTests(unittest.TestCase):
    def test_collection_has_no_delivery_side_effects(self):
        with patch.object(b,'radar_alive',return_value=True),patch.object(b,'trigger_crawl',return_value=True) as start,patch.object(b,'wait_crawl_done',return_value=True):
            self.assertTrue(b.run_round({'radar_base':'fixture'}))
            start.assert_called_once_with('fixture')
        self.assertFalse(hasattr(b,'send_wechat'))

    def test_unavailable_crawler_is_not_triggered(self):
        with patch.object(b,'radar_alive',return_value=False),patch.object(b,'trigger_crawl') as start:
            self.assertFalse(b.run_round({'radar_base':'fixture'}))
            start.assert_not_called()

    def test_startup_waits_before_first_collection(self):
        with patch.object(sys,'argv',['collector','--wait-first-round']),patch.object(b,'wait_for_next_round',side_effect=RuntimeError('stop')),patch.object(b,'run_round') as run:
            with self.assertRaises(RuntimeError):b.main()
            run.assert_not_called()

    def test_normal_start_uses_last_real_crawl(self):
        with patch.object(b,'load_config',return_value={'radar_base':'fixture'}),patch.object(b,'api',return_value={'last_run':'2026-11-24 10:00:00'}),patch.object(b.time,'time',return_value=b.datetime(2026,11,24,12).timestamp()),patch.object(b,'wait_for_next_round') as wait:
            b.wait_for_startup()
            wait.assert_called_once_with(started=b.datetime(2026,11,24,10).timestamp())

    def test_overdue_anchor_does_not_sleep(self):
        with patch.object(b,'load_config',return_value={'interval_minutes':60}),patch.object(b.time,'time',return_value=10000),patch.object(b,'save_json'),patch.object(b.time,'sleep') as sleep:
            b.wait_for_next_round(started=1000)
            sleep.assert_not_called()

    def test_qq_qr_is_local_and_independent(self):
        from qr_renderer import QRRenderer
        svg=QRRenderer().svg('https://txz.qq.com/p?k=fixture')
        self.assertIn(b'<svg',svg)
        self.assertNotIn(b'fixture',svg)

