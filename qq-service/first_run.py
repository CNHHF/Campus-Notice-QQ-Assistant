"""Show the generated admin token once, locally, without logging it."""
import json
import sys
from pathlib import Path


def show_token(token, config_path):
    message = ('首次部署已完成，请保存你的管理口令：\n\n' + token +
        '\n\n口令保存位置：\n' + str(config_path) +
        '\n\n正常重启不会改变口令。请勿分享运行配置文件。'
        '\nWindows 可按 Ctrl+C 复制本窗口文字。')
    if sys.platform == 'win32':
        import ctypes
        return ctypes.windll.user32.MessageBoxW(None, message, '校园通知管理中心 · 首次部署口令', 0x00040040) == 1
    from tkinter import Tk, messagebox
    root = Tk()
    root.withdraw()
    try:
        messagebox.showinfo('校园通知管理中心 · 首次部署口令', message, parent=root)
        return True
    finally:
        root.destroy()


def notify_first_run(runtime, show=None):
    runtime = Path(runtime)
    marker = runtime / 'admin-token-notice.pending'
    if not marker.exists():
        return False
    try:
        config_path = runtime / 'config.json'
        token = json.loads(config_path.read_text(encoding='utf-8'))['admin_token']
        if (show or show_token)(token, config_path.resolve()):
            marker.unlink(missing_ok=True)
            return True
    except Exception:
        # Keep pending for the next desktop launch; never put the secret in logs.
        pass
    return False
