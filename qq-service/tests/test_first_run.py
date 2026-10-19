import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from first_run import notify_first_run


class FirstRunTests(unittest.TestCase):
    def test_existing_deployment_is_not_shown(self):
        with tempfile.TemporaryDirectory() as folder:
            show = Mock()
            self.assertFalse(notify_first_run(folder, show))
            show.assert_not_called()

    def test_first_notice_acknowledged_only_once_without_changing_token(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root/'config.json'
            config.write_text(json.dumps({'admin_token':'temporary-test-token'}))
            before = config.read_bytes()
            (root/'admin-token-notice.pending').touch()
            show = Mock(return_value=True)
            self.assertTrue(notify_first_run(root, show))
            self.assertFalse(notify_first_run(root, show))
            show.assert_called_once_with('temporary-test-token',config.resolve())
            self.assertEqual(config.read_bytes(),before)

    def test_failed_window_remains_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'config.json').write_text(json.dumps({'admin_token':'temporary-test-token'}))
            (root/'admin-token-notice.pending').touch()
            self.assertFalse(notify_first_run(root, Mock(side_effect=RuntimeError('no display'))))
            self.assertTrue((root/'admin-token-notice.pending').exists())
