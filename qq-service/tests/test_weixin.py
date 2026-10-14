import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from weixin_login import WeixinLogin


class WeixinTests(unittest.TestCase):
    def setUp(self):
        self.login=WeixinLogin(Path(__file__).resolve().parents[1])

    def test_qr_and_confirmation_without_persisting_tokens(self):
        with patch.object(self.login,'svg',return_value=b'<svg/>'):
            self.login.update_output('https://weixin.example/qr-secret\n')
        state=self.login.snapshot()
        self.assertTrue(state['qr_ready'])
        self.assertNotIn('qr-secret',str(state))
        self.login.update_output('已将此 OpenClaw 连接到微信。')
        self.assertEqual(self.login.snapshot()['status'],'connected')
        self.assertFalse(self.login.snapshot()['qr_ready'])

    def test_pairing_prompt_without_newline(self):
        self.login.update_output('输入手机微信显示的数字，以继续连接：')
        self.assertTrue(self.login.snapshot()['code_required'])
        with self.assertRaises(ValueError):
            self.login.code('abc')

    def test_existing_binding_and_save_failure(self):
        self.login.update_output('已连接过此 OpenClaw，无需重复连接。')
        self.assertEqual(self.login.snapshot()['status'],'connected')
        self.login.update_output('保存账号数据失败: token=private')
        state=self.login.snapshot()
        self.assertEqual(state['status'],'error')
        self.assertNotIn('private',str(state))

    def test_local_qr_renderer(self):
        try:
            self.login.locations()
        except ValueError:
            self.skipTest('Official OpenClaw QR module not installed')
        svg=self.login.svg('https://example.org/local-render-only')
        self.assertTrue(svg.startswith(b'<svg'))
        self.assertNotIn(b'https://example.org',svg)


if __name__=='__main__':
    unittest.main()
