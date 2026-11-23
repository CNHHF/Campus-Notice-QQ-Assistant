"""Campus notice subscriptions owned by this project; no external app runtime."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
from datetime import date, datetime
from push_preferences import CATEGORIES


class CampusNotice:
    def __init__(self, service, state, root=None):
        self.root = Path(root or Path(__file__).resolve().parent.parent)
        self.query = service
        state = Path(state)
        state.mkdir(parents=True, exist_ok=True)
        self.db_path = state / "subscriptions.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS subscriptions(kind TEXT,target TEXT,enabled INTEGER,last_error TEXT DEFAULT '',PRIMARY KEY(kind,target));"
                "CREATE TABLE IF NOT EXISTS deliveries(kind TEXT,target TEXT,fp TEXT,status TEXT,PRIMARY KEY(kind,target,fp));"
            )
            db.execute("UPDATE deliveries SET status='uncertain' WHERE status='sending'")
            fields = {row[1] for row in db.execute('PRAGMA table_info(subscriptions)')}
            for name, definition in [('label', "TEXT NOT NULL DEFAULT ''"), ('filters_json', "TEXT NOT NULL DEFAULT '{}'" )]:
                if name not in fields:
                    db.execute(f'ALTER TABLE subscriptions ADD COLUMN {name} {definition}')
            db.execute("CREATE TABLE IF NOT EXISTS contacts(kind TEXT,target TEXT,last_seen TEXT,PRIMARY KEY(kind,target))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def fingerprint(row):
        title = re.sub(r"\s+", "", row.get("title") or "").casefold()
        return hashlib.sha256((title or row["url"]).encode()).hexdigest()

    def subscribe(self, kind, target):
        return self.save_subscription(kind, target)

    @staticmethod
    def normalize_filters(value):
        if value is None:
            return {'sources': [], 'categories': [], 'keywords': []}
        if not isinstance(value, dict) or set(value) - {'sources', 'categories', 'keywords'}:
            raise ValueError('订阅筛选格式不正确')
        result = {}
        for key in ('sources', 'categories', 'keywords'):
            values = value.get(key, [])
            if not isinstance(values, list) or len(values) > 100 or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in values):
                raise ValueError('订阅筛选每项最多100个非空值，每个不超过200字')
            result[key] = list(dict.fromkeys(v.strip() for v in values))
        if any(v not in CATEGORIES for v in result['categories']):
            raise ValueError('通知分类无效')
        return result

    @staticmethod
    def matches(row, filters):
        haystack = ((row.get('title') or '') + ' ' + (row.get('digest') or '')).casefold()
        return (not filters['sources'] or row.get('source_name') in filters['sources']) and (not filters['categories'] or row.get('category') in filters['categories']) and (not filters['keywords'] or any(v.casefold() in haystack for v in filters['keywords']))

    def record_contact(self, kind, target):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO contacts VALUES(?,?,?)', (kind, target, datetime.now().isoformat(timespec='seconds')))

    def save_subscription(self, kind, target, *, label=None, filters=None, enabled=True):
        if kind not in ('c2c', 'group') or not isinstance(target, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', target) or target.isdecimal():
            raise ValueError('请选择已接入会话，或填写官方 OpenID；QQ号码和群号不能直接使用')
        if type(enabled) is not bool or (label is not None and (not isinstance(label, str) or len(label) > 80)):
            raise ValueError('订阅备注或启用状态无效')
        normalized = self.normalize_filters(filters) if filters is not None else None
        # Read the complete baseline first: a DB error must not enable a
        # subscription with an empty baseline and flood it with history.
        rows = self.query.radar_rows()
        with self.lock, self.connect() as db:
            existing = db.execute("SELECT enabled,label,filters_json FROM subscriptions WHERE kind=? AND target=?", (kind, target)).fetchone()
            stored_filters = self.normalize_filters(json.loads(existing[2])) if existing else self.normalize_filters(None)
            next_filters = normalized if normalized is not None else stored_filters
            next_label = label.strip() if label is not None else existing[1] if existing else ''
            if existing and existing[0] and label is None and filters is None and enabled:
                return "当前会话已保存筛选。发送‘查看订阅’查询匹配通知；官方版不主动推送。"
            # First subscribe, resume, or content changes establish a new baseline.
            # Existing sent/uncertain records remain intact; label-only edits do not
            # swallow pending new notices.
            if not existing or (not existing[0] and enabled) or next_filters != stored_filters:
                db.executemany("INSERT OR IGNORE INTO deliveries VALUES(?,?,?,'baseline')",
                               [(kind, target, self.fingerprint(row)) for row in rows])
            db.execute("INSERT INTO subscriptions(kind,target,enabled,last_error,label,filters_json) VALUES(?,?,?,'',?,?) ON CONFLICT(kind,target) DO UPDATE SET enabled=excluded.enabled,last_error='',label=excluded.label,filters_json=excluded.filters_json",
                       (kind, target, int(enabled), next_label, json.dumps(next_filters, ensure_ascii=False)))
        return "已保存通知筛选。发送‘查看订阅’查询匹配通知，每条附原文链接；官方版不主动推送。" if enabled else "已保存筛选，当前会话筛选已停用。"

    def answer(self, kind, target, sender, text):
        text = text.strip()
        if text in ("订阅通知", "/subscribe"):
            return self.subscribe(kind, target)
        if text in ("取消订阅", "/unsubscribe"):
            with self.lock, self.connect() as db:
                db.execute("UPDATE subscriptions SET enabled=0 WHERE kind=? AND target=?", (kind, target))
            return "已取消当前会话的自动通知订阅，仍可查询通知。"
        if text in ("订阅状态", "/status"):
            with self.connect() as db:
                row = db.execute("SELECT enabled,last_error FROM subscriptions WHERE kind=? AND target=?", (kind, target)).fetchone()
            if not row:
                return "尚未保存筛选。发送‘订阅通知’创建，再发送‘查看订阅’查询；官方版不主动推送。"
            return ("会话筛选已启用" if row[0] else "会话筛选已停用") + "。发送‘查看订阅’查询；官方版不主动推送。"
        if text in ('查看订阅', '领取通知', '/subscriptions'):
            with self.connect() as db:
                sub = db.execute('SELECT enabled,filters_json FROM subscriptions WHERE kind=? AND target=?', (kind,target)).fetchone()
            if not sub or not sub[0]:
                return '尚未启用会话筛选，请在桌面保存并启用，或发送‘订阅通知’。仍可直接查询‘最新通知’。'
            filters, policy = self.normalize_filters(json.loads(sub[1])), self.policy()
            rows = []
            seen = set()
            for row in self.query.radar_rows():
                fp = self.fingerprint(row)
                if fp not in seen and self.eligible(row,policy) and self.matches(row,filters):
                    seen.add(fp)
                    rows.append(row)
            if not rows:
                return '当前没有符合会话筛选和全局规则的通知。'
            return '按已保存筛选查询，显示最近匹配的最多5条（可重复查询，并非未读队列）：\n' + '\n'.join(self.query.brief(r,i+1) for i,r in enumerate(rows[:5]))
        if text in ("帮助", "/help"):
            return "东方知讯·校园通知助手：查通知 奖学金 / 最新通知 / 最近有哪些竞赛通知 / 第2条详情；订阅通知 / 查看订阅 / 取消订阅 / 订阅状态。群里每次请 @ 我。官方版仅回复查询，不主动推送。"
        with self.lock:
            return self.query.answer({"key": f"{kind}:{target}:{sender}", "text": text})

    def dashboard(self):
        with self.connect() as db:
            subscriptions = [dict(zip(("kind", "target", "enabled", "last_error", "label", "filters_json"), row)) for row in db.execute("SELECT kind,target,enabled,last_error,label,filters_json FROM subscriptions ORDER BY kind,target")]
            for sub in subscriptions:
                sub['filters'] = self.normalize_filters(json.loads(sub.pop('filters_json')))
            contacts = [dict(zip(('kind', 'target', 'last_seen'), row)) for row in db.execute("SELECT kind,target,last_seen FROM contacts UNION SELECT kind,target,'' FROM subscriptions WHERE (kind,target) NOT IN (SELECT kind,target FROM contacts) ORDER BY last_seen DESC")]
            stats = dict(db.execute("SELECT status,COUNT(*) FROM deliveries GROUP BY status"))
        with self.query.connect() as db:
            usage = dict(zip(("input_tokens", "output_tokens"), db.execute("SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0) FROM usage").fetchone()))
            activity = [dict(zip(("at", "kind", "detail"), row)) for row in db.execute("SELECT at,kind,detail FROM activity ORDER BY id DESC LIMIT 40")]
        return {"subscriptions": subscriptions, "contacts": contacts, "stats": stats, "usage": usage, "activity": activity}

    def policy(self):
        bridge = self.root / ("weixin-bridge" if (self.root / "weixin-bridge").is_dir() else "bridge")
        return json.loads((bridge / "bridge-config.json").read_text(encoding="utf-8"))

    def preview(self, filters):
        normalized, policy = self.normalize_filters(filters), self.policy()
        rows = [r for r in self.query.radar_rows() if self.eligible(r, policy) and self.matches(r, normalized)]
        return {'total': len(rows), 'items': [{k: row.get(k) for k in ('title','url','pub_date','source_name','category_name')} for row in rows[:5]], 'will_send': False}

    def pause_subscription(self, kind, target):
        with self.lock, self.connect() as db:
            db.execute("UPDATE subscriptions SET enabled=0,last_error='' WHERE kind=? AND target=?", (kind, target))

    def eligible(self, row, policy):
        title = row.get("title") or ""
        if row.get("category") in policy.get("exclude_categories", ["jobstart"]):
            return False
        if policy.get("categories") and row.get("category") not in policy["categories"]:
            return False
        if any(word and word.casefold() in title.casefold() for word in policy.get("exclude_keywords", [])):
            return False
        try:
            age = (date.today() - date.fromisoformat((row.get("pub_date") or "")[:10])).days
        except ValueError:
            return False
        return 0 <= age <= min(30, max(1, int(policy.get("max_age_days") or 30))) and row["url"].startswith(("https://", "http://"))

    async def push_once(self, send, allowed):
        policy = self.policy()
        if policy.get("qq_push_paused"):
            return
        rows = self.query.radar_rows()
        with self.connect() as db:
            targets = db.execute("SELECT kind,target FROM subscriptions WHERE enabled=1").fetchall()
        for kind, target in targets:
            if not allowed(target):
                continue
            for row in reversed(rows):
                if not self.eligible(row, policy):
                    continue
                fp = self.fingerprint(row)
                with self.lock, self.connect() as db:
                    current = db.execute("SELECT filters_json FROM subscriptions WHERE kind=? AND target=? AND enabled=1", (kind, target)).fetchone()
                    if not current:
                        break
                    if not self.matches(row, self.normalize_filters(json.loads(current[0]))):
                        continue
                    claimed = db.execute("INSERT OR IGNORE INTO deliveries VALUES(?,?,?,'sending')", (kind, target, fp)).rowcount
                if not claimed:
                    continue
                message = re.sub(r"\s+", " ", "📢 " + self.query.brief(row))
                try:
                    receipt = await send(kind, target, message)
                    status = "sent" if isinstance(receipt, dict) and receipt.get("id") else "uncertain"
                except Exception:
                    status = "uncertain"
                with self.lock, self.connect() as db:
                    db.execute("UPDATE deliveries SET status=? WHERE kind=? AND target=? AND fp=?", (status, kind, target, fp))
                    if status != "sent":
                        db.execute("UPDATE subscriptions SET enabled=0,last_error=? WHERE kind=? AND target=?",
                                   ("QQ 主动消息被限制或回执不确定；已暂停，未自动重发。", kind, target))
                if status != "sent":
                    break
                # Yield between notifications; do not burst a backlog.
                import asyncio
                await asyncio.sleep(1.2)
