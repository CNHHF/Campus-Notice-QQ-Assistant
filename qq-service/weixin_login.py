"""Wrap the installed Tencent OpenClaw plugin's login flow, without copying auth logic."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path


class WeixinLogin:
    def __init__(self, base):
        self.base = Path(base)
        self.lock = threading.RLock()
        self.process = None
        self.qr_svg = None
        self.buffer = ''
        self.qr_url = ''
        self.state = {'status':'idle','message':'可使用现有微信通道，按需扫码授权','code_required':False}

    def snapshot(self):
        with self.lock:
            state = dict(self.state)
            state['qr_ready'] = bool(self.qr_svg)
            state['configured'] = any((Path.home()/'.openclaw/openclaw-weixin/accounts').glob('*.json'))
            return state

    def locations(self):
        node = shutil.which('node')
        command = Path(os.environ.get('APPDATA', ''))/'npm/node_modules/openclaw/dist/index.js'
        candidates = list((Path.home()/'.openclaw/npm/projects').glob('*/node_modules/qrcode-terminal/vendor/QRCode'))
        if not node or not command.exists() or not candidates:
            raise ValueError('未找到本机 OpenClaw 或微信二维码组件，请先安装官方微信通道')
        return node, command, candidates[0]

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                return self.snapshot()
            node, command, _ = self.locations()
            self.qr_svg = None
            self.qr_url = ''
            self.buffer = ''
            self.state = {'status':'starting','message':'正在向微信请求登录二维码','code_required':False}
            self.process = subprocess.Popen([node,str(command),'channels','login','--channel','openclaw-weixin'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                env={**os.environ,'FORCE_COLOR':'0','NO_COLOR':'1'})
            threading.Thread(target=self.read_output,args=(self.process,),daemon=True).start()
            threading.Thread(target=self.expire,args=(self.process,),daemon=True).start()
            return self.snapshot()

    def svg(self, text):
        node, _, module = self.locations()
        result = subprocess.run([node,str(self.base/'qr_svg.cjs')],
            input=json.dumps({'module':str(module),'text':text}),capture_output=True,text=True,
            timeout=10,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode or not result.stdout.startswith('<svg'):
            raise ValueError('二维码渲染失败')
        return result.stdout.encode()

    def update_output(self, text):
        # Raw CLI output stays in bounded memory, never in the browser or application log.
        with self.lock:
            self.buffer = (self.buffer + text)[-12000:]
            clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]','',self.buffer)
            urls = re.findall(r'(?m)^\s*(https://[^\s<>]+)\s*$',clean)
            if urls and urls[-1] != self.qr_url:
                self.qr_svg = self.svg(urls[-1])
                self.qr_url = urls[-1]
                self.state.update(status='waiting',message='请用微信扫描二维码，并在手机上确认',code_required=False)
            if '正在验证' in text:
                self.state.update(status='scanned',message='已扫码，请按手机提示完成确认',code_required=False)
            if '输入手机微信显示的数字' in clean or '你输入的数字不匹配' in clean:
                self.state.update(status='verifying',message='请输入手机微信显示的配对数字',code_required=True)
            if '已将此 OpenClaw 连接到微信' in clean or '已连接过此 OpenClaw，无需重复连接' in clean:
                self.state.update(status='connected',message='微信授权完成。请在微信给 bot 发一条消息刷新推送会话',code_required=False)
                self.qr_svg = None
            if '保存账号数据失败' in clean:
                self.state.update(status='error',message='微信授权信息保存失败，请检查 OpenClaw',code_required=False)
                self.qr_svg = None

    def read_output(self, process):
        import codecs
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        try:
            while True:
                chunk = os.read(process.stdout.fileno(),4096)
                if not chunk:
                    break
                self.update_output(decoder.decode(chunk))
            code = process.wait()
            with self.lock:
                if self.process is process and self.state['status'] not in ('connected','cancelled','expired','error'):
                    self.state.update(status='error',message='微信扫码流程未完成，请重试或检查 OpenClaw 通道',code_required=False)
        except Exception:
            with self.lock:
                if self.process is process:
                    self.state.update(status='error',message='微信登录流程异常，请检查本机 OpenClaw',code_required=False)
        finally:
            # Only the login subprocess owned by this page; never stop the gateway.
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdout.close()
            process.stdin.close()
            with self.lock:
                self.buffer = ''
                self.qr_url = ''
                self.qr_svg = None

    def expire(self, process):
        try:
            process.wait(timeout=540)
        except subprocess.TimeoutExpired:
            with self.lock:
                if self.process is process and process.poll() is None:
                    self.state.update(status='expired',message='二维码授权超时，请重新获取',code_required=False)
                    process.terminate()

    def code(self, value):
        if not re.fullmatch(r'[0-9]{4,12}',str(value)):
            raise ValueError('请输入手机显示的 4–12 位数字')
        with self.lock:
            if not self.state['code_required'] or not self.process or self.process.poll() is not None:
                raise ValueError('当前不需要配对数字')
            self.buffer = ''
            self.process.stdin.write((str(value)+'\n').encode())
            self.process.stdin.flush()
            self.state.update(status='scanned',message='配对数字已提交，等待微信确认',code_required=False)
        return self.snapshot()

    def cancel(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.state.update(status='cancelled',message='已取消本次扫码；现有微信服务继续运行',code_required=False)
                self.qr_svg = None
                self.process.terminate()
        return self.snapshot()
