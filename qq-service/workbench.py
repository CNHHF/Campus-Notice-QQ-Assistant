"""Fixed local workbench adapter; never forwards admin credentials or arbitrary URLs."""
import urllib.parse
import urllib.request
from pathlib import Path

GET_PATHS = {'/', '/api/items', '/api/read'}
POST_PATHS = {'/api/profile', '/api/correct'}


def request_local(path, method='GET', body=None):
    parsed = urllib.parse.urlsplit(path)
    allowed = GET_PATHS if method == 'GET' else POST_PATHS if method == 'POST' else set()
    if parsed.scheme or parsed.netloc or parsed.fragment or parsed.path not in allowed:
        raise ValueError('工作台接口不可用')
    query = urllib.parse.parse_qs(parsed.query,keep_blank_values=True)
    if parsed.path == '/api/items':
        allowed_keys = {'days','sort','cat','source','aud','unread','mode','q','unread_only','unreadOnly'}
        if not set(query).issubset(allowed_keys):
            raise ValueError('工作台筛选参数无效')
    req = urllib.request.Request('http://127.0.0.1:8765'+path, data=body,method=method,
        headers={'Content-Type':'application/json'} if body else {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req,timeout=10) as response:
        data = response.read(5*1024*1024+1)
        if len(data)>5*1024*1024:
            raise ValueError('工作台数据过大，请缩小时间范围')
        return data


def render_workbench():
    source = request_local('/').decode('utf-8')
    source = source.replace("fetch('/api/", "fetch('/workbench/api/")
    css = (Path(__file__).parent/'web/workbench.css').read_text(encoding='utf-8')
    return source.replace('</head>', '<style>'+css+'</style></head>').encode('utf-8')
