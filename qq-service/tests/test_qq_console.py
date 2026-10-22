import json
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import Mock
from qq_console import QQConsole


class QQConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.console = QQConsole(self.root, Mock())
        self.console.credential = Mock(return_value='private-credential')
        self.service = Mock()
        self.service.snapshot.return_value = {'onebot_url':'http://127.0.0.1:3000','onebot_token':'private-token'}
        self.service.probe.return_value = {'connected':True,'qq':'12345'}

    def test_status_only_returns_safe_fields_and_checks_exact_channels(self):
        network = {'httpServers':[{'enable':True,'host':'127.0.0.1','port':3000,'token':'private-token','messagePostFormat':'array'}],
                   'httpClients':[{'enable':True,'url':'http://127.0.0.1:8788/onebot/events','token':'private-token'}]}
        self.console.request = Mock(side_effect=[{'isLogin':True,'qrcodeurl':'secret-login-url'}, {'network':network}])
        value = self.console.inspect(self.service,8788)
        self.assertTrue(value['logged_in'])
        self.assertTrue(value['incoming_configured'])
        self.assertTrue(value['outgoing_configured'])
        self.assertNotIn('private-',json.dumps(value))
        self.assertNotIn('secret-login-url',json.dumps(value))
        self.assertEqual(self.console.request.call_count,2)

    def test_login_qr_rendered_locally_and_refresh_is_explicit(self):
        self.console.request = Mock(side_effect=[{'isLogin':False},{},{'qrcodeurl':'https://txz.qq.com/p?k=local-secret'}])
        self.console.renderer.svg.return_value = b'<svg/>'
        value = self.console.prepare_qr()
        self.assertTrue(value['qr_ready'])
        self.assertEqual(self.console.qr,b'<svg/>')
        self.assertNotIn('local-secret',json.dumps(value))

    def test_logged_in_account_never_relogs_or_refreshes_qr(self):
        self.console.request = Mock(return_value={'isLogin':True})
        self.assertFalse(self.console.prepare_qr()['qr_ready'])
        self.assertEqual(self.console.request.call_count,1)
        self.console.renderer.svg.assert_not_called()

    def test_existing_login_code_is_reused_without_refresh(self):
        self.console.request = Mock(return_value={'qrcodeurl':'https://txz.qq.com/p?k=existing'})
        self.console.renderer.svg.return_value = b'<svg/>'
        first = self.console.prepare_qr()
        second = self.console.prepare_qr()
        self.assertEqual(first['qr_revision'], second['qr_revision'])
        self.assertEqual(self.console.renderer.svg.call_count,1)
        self.assertEqual([call.args[0] for call in self.console.request.call_args_list],['QQLogin/CheckLoginStatus']*2)

    def test_expired_code_refreshes_and_changes_revision(self):
        self.console.qr=b'<svg>old</svg>'
        self.console.qr_created=time.monotonic()-121
        self.console.request=Mock(side_effect=[{'qrcodeurl':'https://txz.qq.com/p?k=old'}, {}, {'qrcodeurl':'https://txz.qq.com/p?k=new'}])
        self.console.renderer.svg.return_value=b'<svg>new</svg>'
        self.assertTrue(self.console.prepare_qr()['qr_ready'])
        self.assertEqual(self.console.request.call_args_list[1].args[0],'QQLogin/RefreshQRcode')

    def test_scanned_code_is_not_replaced_while_waiting_for_phone(self):
        self.console.request=Mock(return_value={'qrLoginAccepted':True})
        result=self.console.prepare_qr(refresh=True)
        self.assertFalse(result['qr_ready'])
        self.assertEqual(self.console.request.call_count,1)
        self.console.renderer.svg.assert_not_called()

    def test_untrusted_qr_url_is_rejected(self):
        self.console.request = Mock(side_effect=[{}, {}, {'qrcodeurl':'https://untrusted.example/secret'}])
        with self.assertRaises(ValueError):self.console.prepare_qr()
        self.console.renderer.svg.assert_not_called()
        self.assertIsNone(self.console.qr)

    def test_errors_never_expose_credentials(self):
        self.console.request = Mock(side_effect=RuntimeError('private-credential'))
        result = self.console.inspect(self.service,8788)
        self.assertFalse(result['available'])
        self.assertNotIn('private-',json.dumps(result))
        self.service.probe.assert_not_called()

    def test_adapter_has_no_generic_proxy(self):
        with self.assertRaises(ValueError):self.console.request('QQLogin/PasswordLogin',{})
