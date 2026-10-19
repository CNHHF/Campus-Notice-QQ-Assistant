import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import workbench


class WorkbenchTests(unittest.TestCase):
    def test_render_preserves_actions_and_applies_local_theme(self):
        source=b"<html><head></head><script>fetch('/api/items?days=7');fetch('/api/profile',{});</script></html>"
        with patch.object(workbench,'request_local',return_value=source):
            html=workbench.render_workbench().decode()
        self.assertIn("fetch('/workbench/api/items",html)
        self.assertIn("fetch('/workbench/api/profile",html)
        self.assertIn('--accent:#b64d2c',html)

    def test_service_control_routes_are_not_forwarded(self):
        for path,method in [('/api/refresh','GET'),('/api/quit','POST'),('/api/profile','GET')]:
            with self.assertRaises(ValueError):
                workbench.request_local(path,method)
