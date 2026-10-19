"""Validated non-secret push preferences shared by both channels."""
import json
from pathlib import Path
CATEGORIES = {'jobstart':'就业创业','examtgt':'考公考研','teacherhire':'教师招聘','makeup':'补考选课','venue':'场地与采购','contest':'竞赛讲座','money':'评奖评优公示','gongshi':'公示名单','teachrun':'教学运行','research':'教研成果','life':'后勤服务','other':'其他信息'}

def strings(value, limit=100):
    if not isinstance(value,list) or len(value)>limit or any(not isinstance(x,str) or not x.strip() or len(x)>100 for x in value):
        raise ValueError('列表最多100项，每项1–100字符')
    return list(dict.fromkeys(x.strip() for x in value))

def category_list(value):
    result=strings(value)
    if any(x not in CATEGORIES for x in result):raise ValueError('通知分类无效')
    return result

def read_policy(path):
    try: cfg=json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):cfg={}
    return {k:cfg.get(k,v) for k,v in {'exclude_keywords':[],'exclude_categories':['jobstart'],'categories':[],'max_age_days':30,'weixin_push_paused':False,'qq_push_paused':False}.items()}

def write_policy(path, value):
    normalized={'exclude_keywords':strings(value.get('exclude_keywords',[])), 'exclude_categories':category_list(value.get('exclude_categories',[])), 'categories':category_list(value.get('categories',[]))}
    days=value.get('max_age_days',30)
    if isinstance(days,bool) or not isinstance(days,int) or not 1<=days<=30:raise ValueError('自动推送有效期为1–30天')
    normalized['max_age_days']=days
    for k in ('weixin_push_paused','qq_push_paused'):
        if type(value.get(k)) is not bool:raise ValueError('暂停状态必须为布尔值')
        normalized[k]=value[k]
    path=Path(path)
    try:cfg=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):raise ValueError('无法读取推送配置') from None
    cfg.update(normalized)
    temp=path.with_name(path.name+'.policy.tmp');temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
    return normalized

def matches_group(group,item):
    return (not group.get('sources') or item.get('source_name') in group['sources']) and (not group.get('categories') or item.get('category') in group['categories'])
