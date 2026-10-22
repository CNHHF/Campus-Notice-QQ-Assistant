"""Small fixed-local NapCat adapter. Never forward its management credential."""
import hashlib
import json
import threading
import time
import urllib.request
from urllib.parse import urlsplit


class QQConsole:
    def __init__(self, root, renderer):
        self.root = root
        self.renderer = renderer
        self.lock = threading.Lock()
        self.qr = None
        self.qr_url = ''
        self.qr_created = 0

    def request(self, path, payload, credential=''):
        allowed = {'auth/login', 'QQLogin/CheckLoginStatus', 'QQLogin/RefreshQRcode', 'OB11Config/GetConfig'}
        if path not in allowed:
            raise ValueError('不支持的 QQ 管理操作')
        request = urllib.request.Request('http://127.0.0.1:6099/api/' + path,
            data=json.dumps(payload).encode(), headers={'Content-Type':'application/json', 'Authorization':'Bearer '+credential})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            result = json.loads(response.read(1024*1024))
        if result.get('code') != 0:
            raise ValueError('QQ 管理接口拒绝请求，请检查客户端管理授权')
        return result.get('data') or {}

    def credential(self):
        try:
            config = json.loads((self.root/'qq-client/NapCat/config/webui.json').read_text(encoding='utf-8'))
            token = config['token']
        except (OSError, ValueError, KeyError):
            raise ValueError('未找到本机 NapCat 管理配置，请先安装并启动 QQ 客户端') from None
        result = self.request('auth/login', {'hash':hashlib.sha256((token+'.napcat').encode()).hexdigest()})
        return result['Credential']

    def inspect(self, service, port):
        with self.lock:
            try:
                credential = self.credential()
                login = self.request('QQLogin/CheckLoginStatus', {}, credential)
                logged = bool(login.get('isLogin'))
                if logged or (self.qr and (login.get('qrcodeurl') != self.qr_url or time.monotonic()-self.qr_created>120)):
                    self.qr = None
                network = self.request('OB11Config/GetConfig', {}, credential).get('network', {})
                cfg = service.snapshot()
                outgoing = any(x.get('enable') and x.get('host') in ('127.0.0.1','localhost')
                    and str(x.get('port')) == str(urlsplit(cfg['onebot_url']).port or 80)
                    and x.get('token') == cfg['onebot_token'] and x.get('messagePostFormat') == 'array'
                    for x in network.get('httpServers', []))
                incoming = any(x.get('enable') and x.get('url') == f'http://127.0.0.1:{port}/onebot/events'
                    and x.get('token') == cfg['onebot_token'] and not x.get('reportSelfMessage', False)
                    for x in network.get('httpClients', []))
                phase = str(login.get('loginPhase',''))
                return {'available':True, 'logged_in':logged, 'phase':phase[:40],
                    'message':'QQ 已登录' if logged else '等待本人扫码或在手机 QQ 确认登录',
                    'outgoing_configured':outgoing, 'incoming_configured':incoming,
                    'qr_ready':bool(self.qr), 'qr_revision':hashlib.sha256(self.qr).hexdigest()[:16] if self.qr else '',
                    'connection':service.probe() if logged else {'connected':False}}
            except Exception:
                self.qr = None
                return {'available':False, 'logged_in':False, 'qr_ready':False,
                    'message':'无法读取 QQ 客户端状态，请先点击启动 / 修复服务；仍失败请检查本机客户端管理授权。'}

    def prepare_qr(self, refresh=False):
        with self.lock:
            try:
                credential = self.credential()
                login = self.request('QQLogin/CheckLoginStatus', {}, credential)
                if login.get('isLogin'):
                    self.qr = None
                    return {'qr_ready':False, 'message':'QQ 已登录，无需再次扫码'}
                if login.get('qrLoginAccepted'):
                    return {'qr_ready':bool(self.qr), 'qr_revision':hashlib.sha256(self.qr).hexdigest()[:16] if self.qr else '', 'message':'已扫码，正在等待手机确认或 QQ 登录完成，请稍候。'}
                if self.qr and not refresh and login.get('qrcodeurl') == self.qr_url and time.monotonic()-self.qr_created<120:
                    return {'qr_ready':True, 'qr_revision':hashlib.sha256(self.qr).hexdigest()[:16], 'message':'请使用机器人 QQ 扫码，并在手机上确认登录。'}
                expired = self.qr_created and time.monotonic()-self.qr_created>=120
                if refresh or expired or not login.get('qrcodeurl'):
                    self.request('QQLogin/RefreshQRcode', {}, credential)
                    login = self.request('QQLogin/CheckLoginStatus', {}, credential)
                url = login.get('qrcodeurl','')
                parsed = urlsplit(url)
                if parsed.scheme != 'https' or parsed.hostname != 'txz.qq.com' or len(url)>2048:
                    raise ValueError('二维码暂未就绪，请稍后重试')
                self.qr = self.renderer.svg(url)
                self.qr_url = url
                self.qr_created = time.monotonic()
                return {'qr_ready':True, 'qr_revision':hashlib.sha256(self.qr).hexdigest()[:16], 'message':'请使用机器人 QQ 扫码，并在手机上确认登录。登录后待发通知会按原规则自动发送。'}
            except Exception:
                self.qr = None
                raise ValueError('二维码暂未就绪，页面会自动重试；也可点击启动 / 修复服务。') from None
