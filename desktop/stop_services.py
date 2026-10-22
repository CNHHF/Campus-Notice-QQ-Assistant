"""Stop only verified project processes after checking for active deliveries."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
from contextlib import closing


def selected_process(row, root, gateway_pid):
    command=(row.get('CommandLine') or '').replace('\\','/').lower()
    executable=(row.get('ExecutablePath') or '').replace('\\','/').lower()
    base=root.as_posix().lower().rstrip('/')+'/'
    if executable.endswith(('/python.exe','/pythonw.exe')):
        return any(base+part in command for part in ('qq-service/app.py','qq-service/launch.py','weixin-bridge/bridge.py','bridge/bridge.py'))
    if executable in (base+'school-radar-pkg/school-radar/school-radar.exe',base+'school-radar-pkg/school-radar/school-radar-cli.exe'):
        return True
    if executable.endswith('/qq.exe') and base+'qq-client/napcat/' in command:
        return True
    return row.get('ProcessId')==gateway_pid and executable.endswith('/node.exe') and '/openclaw/' in command and 'index.js gateway' in command


def safe_to_stop(root):
    database=root/'qq-service/runtime/service.db'
    if database.exists():
        with closing(sqlite3.connect('file:'+database.as_posix()+'?mode=ro',uri=True,timeout=2)) as db:
            for table,states in [('deliveries',"'sending'"),('manual_push',"'queued','sending'")]:
                if db.execute('SELECT COUNT(*) FROM '+table+' WHERE status IN ('+states+')').fetchone()[0]:return False
    bridge=root/'weixin-bridge'
    if not bridge.exists():bridge=root/'bridge'
    # A schedule is written during the wait between rounds; leave a margin before wakeup.
    if (bridge/'bridge-config.json').exists() and not (bridge/'crawl-schedule.json').exists():
        return False
    if (bridge/'crawl-schedule.json').exists():
        schedule=json.loads((bridge/'crawl-schedule.json').read_text(encoding='utf-8'))
        config=json.loads((bridge/'bridge-config.json').read_text(encoding='utf-8'))
        elapsed=time.time()-float(schedule['wait_started_epoch'])
        if not 0<=elapsed<int(config.get('interval_minutes',60))*60-30:return False
    return True


def main():
    root=Path(sys.argv[1]).resolve()
    if not (root/'qq-service/app.py').is_file():return 2
    if not safe_to_stop(root):return 10
    script="Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine,ExecutablePath | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',script],capture_output=True,timeout=20,creationflags=0x08000000)
    if result.returncode:return 3
    rows=json.loads(result.stdout.decode('utf-8-sig',errors='replace'))
    try:gateway=int(json.loads((root/'qq-service/runtime/startup-status.json').read_text(encoding='utf-8')).get('gateway_pid',0))
    except (OSError,ValueError):gateway=0
    selected=[r for r in rows if selected_process(r,root,gateway)]
    # Stop the scheduler first, then other components. No process-name-wide termination.
    selected.sort(key=lambda r:0 if 'app.py' in (r.get('CommandLine') or '') else 1)
    database=root/'qq-service/runtime/service.db'
    guard=sqlite3.connect(database,timeout=2) if database.exists() else None
    try:
        # Freeze new delivery claims until the scheduler is stopped. An existing
        # sending claim makes us refuse; we never kill a sender between check/send.
        if guard:guard.execute('BEGIN IMMEDIATE')
        if not safe_to_stop(root):return 10
        for row in selected:
            try:os.kill(int(row['ProcessId']),signal.SIGTERM)
            except ProcessLookupError:pass
    finally:
        if guard:guard.rollback();guard.close()
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception:sys.exit(3)
