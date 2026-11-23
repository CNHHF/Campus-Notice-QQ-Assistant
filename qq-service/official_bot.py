"""Official QQ transport hosted by this campus service, without an external app."""
import asyncio
import json
import re
import threading
from campus_notice import CampusNotice

_runtime = None


class OfficialBot:
    def __init__(self, service):
        self.service = service
        self.path = service.data / 'official-qq.json'
        self.notice = CampusNotice(service, service.data / 'official-state', root=service.root)
        self.setup = {'status': 'starting'}
        self.client = self.loop = None
        self.stopping = False
        self.sequence = 0
        self.seen = set()

    def config(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    def allowed(self, sender):
        names = self.config().get('allow_from', [])
        return '*' in names or sender in names

    def dashboard(self):
        cfg = self.config()
        return {**self.notice.dashboard(), 'available': True, 'setup': dict(self.setup),
                'app_id': cfg.get('app_id', ''), 'configured': bool(cfg.get('secret')),
                'allow_all': '*' in cfg.get('allow_from', []),
                'allow_from': [v for v in cfg.get('allow_from', []) if v != '*'],
                'model': self.service.snapshot()['model'], 'provider': 'deepseek',
                'model_configured': bool(self.service.model_key())}

    async def send(self, kind, target, text, message_id=None):
        if not message_id:
            raise ValueError('官方 QQ 版仅在收到用户消息后回复，不提供主动推送')
        self.sequence += 1
        payload = {'content': text, 'msg_type': 0, 'msg_seq': self.sequence}
        if message_id:
            payload['msg_id'] = message_id
        if kind == 'group':
            return await self.client.api.post_group_message(group_openid=target, **payload)
        return await self.client.api.post_c2c_message(openid=target, **payload)

    async def receive(self, message, group=False):
        if message.id in self.seen:
            return
        if len(self.seen) > 2000:
            self.seen.clear()
        self.seen.add(message.id)
        if group:
            target, sender = message.group_openid, str(message.author.member_openid)
        else:
            sender = str(getattr(message.author, 'user_openid', None) or getattr(message.author, 'id', ''))
            target = sender
        if not sender or not self.allowed(sender):
            return
        text = re.sub(r'^(?:<@!?[^>]+>\s*)+', '', message.content or '').strip()
        kind = 'group' if group else 'c2c'
        self.notice.record_contact(kind, target)
        try:
            answer = await asyncio.to_thread(self.notice.answer, kind, target, sender, text)
            self.service.record('query', '官方 QQ 校园通知查询或订阅命令已处理')
        except Exception:
            answer = '校园通知查询暂不可用，请稍后重试；不会改动订阅或重发通知。'
        try:
            if self.allowed(sender):
                await self.send(kind, target, answer, message.id)
        except Exception:
            self.service.record('reply_error', '官方 QQ 回复失败，未自动重发')

    async def scheduler(self):
        # Proactive messages are unavailable on the official QQ platform.
        # Collection belongs to the existing hourly crawler; QQ only replies.
        return

    async def run(self):
        self.loop = asyncio.get_running_loop()
        try:
            import botpy
        except ImportError:
            self.setup = {'status': 'unavailable', 'message': '请先运行本项目 qq-service/setup.ps1 安装官方 QQ SDK。'}
            return
        owner = self

        class Client(botpy.Client):
            def __init__(self):
                super().__init__(intents=botpy.Intents(public_messages=True, direct_message=True), bot_log=False, ext_handlers=False)

            async def on_ready(self):
                owner.setup = {'status': 'connected'}

            async def on_c2c_message_create(self, message):
                await owner.receive(message)

            async def on_group_at_message_create(self, message):
                await owner.receive(message, group=True)

        scheduler = asyncio.create_task(self.scheduler())
        try:
            while not self.stopping:
                cfg = self.config()
                if not cfg.get('app_id') or not cfg.get('secret'):
                    self.setup = {'status': 'action_required', 'message': '请在桌面接入设置填写 AppID 和 AppSecret。'}
                    await asyncio.sleep(2)
                    continue
                try:
                    self.setup = {'status': 'connecting'}
                    self.client = Client()
                    await self.client.start(appid=cfg['app_id'], secret=cfg['secret'])
                except Exception:
                    self.setup = {'status': 'error', 'message': '官方 QQ 连接失败，请检查凭据、网络及平台权限。'}
                if not self.stopping:
                    await asyncio.sleep(3)
        finally:
            scheduler.cancel()
            if self.client:
                await self.client.close()

    def start(self):
        self.thread = threading.Thread(target=lambda: asyncio.run(self.run()), daemon=True, name='campus-official-qq')
        self.thread.start()

    def reconnect(self):
        self.setup = {'status': 'connecting'}
        if self.client and self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.client.close(), self.loop)

    def stop(self):
        self.stopping = True
        self.reconnect()


def start(service):
    global _runtime
    _runtime = OfficialBot(service)
    _runtime.start()


def stop():
    if _runtime:
        _runtime.stop()


def dashboard():
    if _runtime:
        return _runtime.dashboard()
    return {'available': False, 'setup': {'status': 'offline'}, 'configured': False,
            'subscriptions': [], 'stats': {}, 'usage': {'input_tokens': 0, 'output_tokens': 0},
            'activity': [], 'model': '', 'provider': 'deepseek', 'app_id': '', 'allow_all': False,
            'allow_from': [], 'model_configured': False}


def probe():
    data = dashboard()
    connected = data['setup'].get('status') == 'connected'
    return {'connected': connected, 'message': '官方 QQ Bot 已连接' if connected else data['setup'].get('message') or '官方 QQ Bot 未连接', 'qq': data['app_id']}


def overlay(state):
    data = dashboard()
    state.update(official_qq=data, transport='qq-official', connection=probe(), stats=data['stats'],
                 usage=data['usage'], activity=data['activity'], model_ready=data['model_configured'],
                 last_event=data['activity'][0]['at'] if data['activity'] else None)
    state['config'].update(groups=[], private_users=[], model=data['model'])
    return state


def save(value):
    if not _runtime:
        raise ValueError('官方 QQ 服务尚未初始化')
    app_id, secret = str(value.get('app_id') or '').strip(), str(value.get('secret') or '').strip()
    if not re.fullmatch(r'[0-9]{5,20}', app_id):
        raise ValueError('AppID 必须为 5–20 位数字')
    names = value.get('allow_from', [])
    if len(secret) > 256 or type(value.get('allow_all')) is not bool:
        raise ValueError('QQ Bot 配置格式不正确')
    if not isinstance(names, list) or len(names) > 100 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,128}', v) for v in names):
        raise ValueError('OpenID 名单无效，每行填写一个 OpenID')
    if not value['allow_all'] and not names:
        raise ValueError('限制访问时至少填写一个 OpenID')
    with _runtime.service.lock:
        cfg = _runtime.config()
        cfg.update(app_id=app_id, allow_from=['*'] if value['allow_all'] else list(dict.fromkeys(names)))
        if secret:
            cfg['secret'] = secret
        if not cfg.get('secret'):
            raise ValueError('首次配置需要填写 AppSecret')
        temporary = _runtime.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(_runtime.path)
    _runtime.reconnect()
    return {'ok': True}


def save_model(value):
    if not _runtime:
        raise ValueError('官方 QQ 服务尚未初始化')
    model, key = str(value.get('model') or '').strip(), str(value.get('api_key') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', model) or len(key) > 256:
        raise ValueError('DeepSeek 模型或凭据格式不正确')
    with _runtime.service.lock:
        cfg = _runtime.service.snapshot()
        cfg['model'] = model
        if key:
            cfg['deepseek_key'] = key
        temporary = _runtime.service.data / 'config.tmp'
        temporary.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(_runtime.service.data / 'config.json')
        _runtime.service.config = cfg
    return {'ok': True}


def pause(value):
    if not _runtime or value.get('kind') not in ('c2c', 'group') or not isinstance(value.get('target'), str):
        raise ValueError('订阅对象无效')
    _runtime.notice.pause_subscription(value['kind'], value['target'])
    return {'ok': True}


def save_subscription(value):
    if not _runtime:
        raise ValueError('官方 QQ 服务尚未初始化')
    message = _runtime.notice.save_subscription(value.get('kind'), value.get('target'),
        label=value.get('label', ''), filters=value.get('filters', {}), enabled=value.get('enabled', True))
    return {'ok': True, 'message': message, 'will_send_existing': False}


def preview_subscription(value):
    if not _runtime:
        raise ValueError('官方 QQ 服务尚未初始化')
    return _runtime.notice.preview(value.get('filters', {}))
