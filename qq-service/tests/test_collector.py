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
        with patch.object(sys,'argv',['collector']),patch.object(b,'wait_for_next_round',side_effect=RuntimeError('stop')),patch.object(b,'run_round') as run:
            with self.assertRaises(RuntimeError):b.main()
            run.assert_not_called()

    def test_qq_qr_is_local_and_independent(self):
        from qr_renderer import QRRenderer
        svg=QRRenderer().svg('https://txz.qq.com/p?k=fixture')
        self.assertIn(b'<svg',svg)
        self.assertNotIn(b'fixture',svg)

