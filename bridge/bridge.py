"""Collect public notices on schedule; this process never sends messages."""
import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / 'bridge-config.json'
SCHEDULE_PATH = BASE_DIR / 'crawl-schedule.json'


def load_config():
    value = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    value.setdefault('radar_base', 'http://127.0.0.1:8765')
    return value


def log(message):
    with (BASE_DIR / 'collector.log').open('a', encoding='utf-8') as stream:
        stream.write(datetime.now().isoformat(timespec='seconds') + ' ' + message + '\n')


def save_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value), encoding='utf-8')
    temp.replace(path)


def api(base, path, timeout=15):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base.rstrip('/') + path, timeout=timeout) as response:
        return json.load(response)


def radar_alive(base):
    try:
        api(base, '/api/alive', timeout=3)
        return True
    except Exception:
        return False


def trigger_crawl(base):
    try:
        api(base, '/api/refresh', timeout=10)
        return True
    except Exception:
        return False


def wait_crawl_done(base, budget_seconds=360):
    deadline = time.monotonic() + budget_seconds
    while time.monotonic() < deadline:
        try:
            if not api(base, '/api/items?days=1').get('crawling'):
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def run_round(config):
    base = config['radar_base']
    if not radar_alive(base) or not trigger_crawl(base):
        return False
    return wait_crawl_done(base)


def wait_for_next_round(resume=False):
    started = time.time()
    if resume:
        try:
            previous = float(json.loads(SCHEDULE_PATH.read_text(encoding='utf-8'))['wait_started_epoch'])
            interval = min(180, max(10, int(load_config().get('interval_minutes') or 60))) * 60
            if 0 <= started - previous < interval:
                started = previous
        except (OSError, ValueError, KeyError, TypeError):
            pass
    save_json(SCHEDULE_PATH, {'wait_started_epoch': started})
    while True:
        interval = min(180, max(10, int(load_config().get('interval_minutes') or 60))) * 60
        remaining = interval - (time.time() - started)
        if remaining <= 0:
            return
        time.sleep(min(5, remaining))


def main():
    parser = argparse.ArgumentParser(description='Collect campus notices; never sends messages')
    parser.add_argument('--wait-first-round', action='store_true')
    args = parser.parse_args()
    wait_for_next_round(resume=args.wait_first_round)
    while True:
        try:
            run_round(load_config())
        except Exception:
            log('Collection failed; waiting for next cycle')
        wait_for_next_round()


if __name__ == '__main__':
    main()
