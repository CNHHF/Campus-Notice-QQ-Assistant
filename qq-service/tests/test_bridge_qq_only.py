import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

root=Path(__file__).resolve().parents[2]
path=root/('weixin-bridge' if (root/'weixin-bridge').is_dir() else 'bridge')/'bridge.py'
spec=importlib.util.spec_from_file_location('qq_only_crawl_bridge',path)
bridge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class QQOnlyCollectorTests(unittest.TestCase):
    def test_paused_wechat_does_not_require_wechat_target(self):
        cfg={'radar_db':'fixture.db','weixin_push_paused':True,'interval_minutes':60}
        with patch.object(sys,'argv',['bridge.py','--once']),patch.object(bridge,'load_config',return_value=cfg),patch.object(bridge,'clear_pause_marker'),patch.object(bridge,'load_json',return_value={}),patch.object(bridge,'backfill_titles'),patch.object(bridge,'run_round') as run,patch.object(bridge,'resolve_openclaw',side_effect=AssertionError('Unrelated gateway requested')):
            self.assertEqual(bridge.main(),0)
            run.assert_called_once()


if __name__=='__main__':unittest.main()
