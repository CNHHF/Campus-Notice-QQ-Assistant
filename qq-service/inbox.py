"""Read-only campus archive + administrator-local inbox flags. No network requests."""
import re
import sqlite3
from contextlib import closing
from html import unescape
from html.parser import HTMLParser
from datetime import datetime

class PlainText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if not self.skip and tag in ('p','br','div','li','tr','h1','h2','h3'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:self.skip-=1
        if not self.skip and tag in ('p','div','li','tr','h1','h2','h3'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def plain(value):
    value=str(value or '')
    if re.search(r'<(?:p|div|br|script|style|span|a|table)\b',value,re.I):
        parser=PlainText();parser.feed(value);value=''.join(parser.parts)
    return re.sub(r'\n[ \t]*\n+', '\n\n',unescape(value)).strip()

def archive(service):
    with closing(sqlite3.connect(f'file:{service.radar.as_posix()}?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        cols={r[1] for r in db.execute('PRAGMA table_info(items)')}
        fields=['url','title','digest','body','source_name','pub_date','category','category_name','first_seen']
        for optional in ('read','files','deadline'):
            if optional in cols:fields.append(optional)
        rows=[dict(r) for r in db.execute('SELECT '+','.join(fields)+" FROM items ORDER BY COALESCE(pub_date,first_seen,'') DESC,url")]
    with service.connect() as db:
        flags={r['url']:dict(r) for r in db.execute('SELECT * FROM inbox_flags')}
    for r in rows:
        flag=flags.get(r['url'],{})
        r['read']=bool(flag.get('is_read',r.get('read',0)))
        r['starred']=bool(flag.get('starred',0))
    return rows

def listing(service,args):
    folder=args.get('folder','all')
    if folder not in ('all','unread','starred'):raise ValueError('收件箱分组无效')
    offset=max(0,min(int(args.get('offset',0)),100000))
    start,end=args.get('start',''),args.get('end','')
    for value in (start,end):
        if value:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('日期格式无效')
            datetime.strptime(value,'%Y-%m-%d')
    if start and end and start>end:raise ValueError('开始日期不能晚于结束日期')
    rows=archive(service)
    counts={'all':len(rows),'unread':sum(not r['read'] for r in rows),'starred':sum(r['starred'] for r in rows)}
    sources={};categories={}
    for r in rows:
        name=r.get('source_name') or ''
        if name:sources[name]=sources.get(name,0)+1
        key=r.get('category') or 'other'
        categories.setdefault(key,{'id':key,'name':r.get('category_name') or '其他信息','count':0})['count']+=1
    terms=str(args.get('q',''))[:120].split()[:5]
    filtered=[]
    for r in rows:
        if folder=='unread' and r['read']:continue
        if folder=='starred' and not r['starred']:continue
        if args.get('source') and r.get('source_name')!=args['source']:continue
        if args.get('category') and r.get('category')!=args['category']:continue
        date=(r.get('pub_date') or '')[:10]
        if start and (not date or date<start):continue
        if end and (not date or date>end):continue
        if terms and not any(t.casefold() in ((r.get('title') or '')+' '+(r.get('digest') or '')).casefold() for t in terms):continue
        filtered.append(r)
    page=[{k:v for k,v in r.items() if k not in ('body','files')} for r in filtered[offset:offset+20]]
    return {'items':page,'has_more':len(filtered)>offset+20,'total':len(filtered),'counts':counts,'sources':sources,'categories':list(categories.values())}

def detail(service,url):
    row=next((r for r in archive(service) if r['url']==url),None)
    if row is None:raise ValueError('通知不存在')
    row['body']=plain(row.get('body'))
    row['digest']=plain(row.get('digest'))
    row['files']=plain(row.get('files'))
    return row

def update(service,value):
    url=value.get('url')
    if not isinstance(url,str):raise ValueError('通知链接无效')
    changes={k:value[k] for k in ('read','starred') if k in value}
    if not changes or any(type(v) is not bool for v in changes.values()):raise ValueError('标记状态必须为布尔值')
    with service.lock:
        row=detail(service,url)
        with service.connect() as db:
            db.execute('INSERT INTO inbox_flags(url,is_read,starred,updated) VALUES(?,?,?,?) ON CONFLICT(url) DO UPDATE SET is_read=excluded.is_read,starred=excluded.starred,updated=excluded.updated',
                (url,int(changes.get('read',row['read'])),int(changes.get('starred',row['starred'])),datetime.now().isoformat(timespec='seconds')))
    return {'url':url,'read':changes.get('read',row['read']),'starred':changes.get('starred',row['starred'])}
