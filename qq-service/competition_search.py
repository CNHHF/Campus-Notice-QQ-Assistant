"""Title-level safeguards for competition queries; no deadline inference."""
import re

SUBJECTS = ('竞赛', '大赛', '比赛', '锦标赛', '挑战杯', '正大杯')
TRAINING = ('培训', '操作指南', '系统使用', '系统操作', '系统维护')
RESULTS = ('结果', '获奖', '名单', '成绩', '公示', '圆满结束', '圆满落幕', '颁奖', '表彰', '风采', '喜报')
SPORTS = ('运动会', '游泳', '篮球', '足球', '排球', '羽毛球', '乒乓球', '锦标赛', '健身', '体育')
GENERIC = {'竞赛', '比赛', '大赛', '竞赛通知', '通知', '学校', '校园', '最近', '最新'}

def competition_intent(question, plan):
    words = plan.get('keywords', [])
    if not any(w in question for w in SUBJECTS) and not any(any(w in k for w in SUBJECTS) for k in words):
        return None
    stage = 'opportunity'
    if re.search(r'所有类型|全部类型|不限类型|包括.{0,8}(?:培训|结果)', question):
        stage = 'all'
    elif re.search(r'培训|操作指南|系统使用', question):
        stage = 'training'
    elif re.search(r'结果|获奖|名单|成绩|公示|结束|落幕|喜报', question):
        stage = 'result'
    return {'stage': stage, 'sports': any(w in question for w in SPORTS),
            'keywords': [k for k in words if k.strip() not in GENERIC]}

def sql_filters(intent):
    clauses, params = [], []
    def any_title(words):
        params.extend('%' + word + '%' for word in words)
        return '(' + ' OR '.join('title LIKE ?' for _ in words) + ')'
    clauses.append(any_title(SUBJECTS))
    stage = intent['stage']
    if stage == 'training':
        clauses.append(any_title(TRAINING))
    elif stage == 'result':
        clauses.append(any_title(RESULTS))
        clauses.append('NOT ' + any_title(TRAINING))
    elif stage == 'opportunity':
        clauses.append('NOT ' + any_title(TRAINING + RESULTS))
        clauses.append(any_title(('通知', '报名', '举办', '参赛', '征集', '选拔', '启动')))
    if not intent['sports']:
        clauses.append('NOT ' + any_title(SPORTS))
    return ' AND '.join(clauses), params
