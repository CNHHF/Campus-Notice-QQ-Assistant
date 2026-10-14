"""Double-click launcher helper. Keep admin secret off the process command line."""
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

base = Path(__file__).resolve().parent
url = 'http://127.0.0.1:8788'

if sys.platform == 'win32':
    result = subprocess.run(['powershell.exe','-NoProfile','-File',str(base/'start-services.ps1')],
        capture_output=True,text=True,timeout=65,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        print('Service startup failed. Check qq-service/runtime/startup-status.json')
    else:
        try:
            status = json.loads(result.stdout.strip())
            print('WeChat gateway:', 'running' if status['gateway_ready'] else 'not ready')
            print('WeChat bridge:', 'running' if status['bridge_pid'] else 'not running')
            print('QQ client:', 'ready' if status['qq_ready'] else 'waiting for login')
        except ValueError:
            print('Service startup status unavailable.')


def alive():
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url + '/api/health', timeout=1) as r:
            return json.load(r).get('service') == 'campus-qq'
    except Exception:
        return False


if not alive():
    runtime = base / 'runtime'
    runtime.mkdir(exist_ok=True)
    with (runtime / 'process.log').open('ab') as log:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        process = subprocess.Popen([sys.executable, str(base / 'app.py')], cwd=base, stdout=log, stderr=log, creationflags=flags)
    for _ in range(50):
        if alive():
            break
        if process.poll() is not None:
            raise SystemExit('Startup failed. See qq-service/runtime/process.log')
        time.sleep(.2)
    else:
        raise SystemExit('Startup timeout. See qq-service/runtime/process.log')
config = json.loads((base / 'runtime/config.json').read_text(encoding='utf-8'))
webbrowser.open(url + '/#token=' + config['admin_token'])
