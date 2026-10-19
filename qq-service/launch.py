"""Double-click launcher helper. Keep admin secret off the process command line."""
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from first_run import notify_first_run

base = Path(__file__).resolve().parent
url = 'http://127.0.0.1:8788'

if sys.platform == 'win32':
    runtime = base/'runtime'
    runtime.mkdir(exist_ok=True)
    with (runtime/'startup.log').open('ab') as log:
        subprocess.Popen(['powershell.exe','-NoProfile','-File',str(base/'start-services.ps1')],
            stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    print('Starting services in background. See the live status on the admin page.')


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
notify_first_run(base / 'runtime')
webbrowser.open(url + '/#token=' + config['admin_token'])
