"""Limited access to the crawler interval; never return bridge credentials."""
import json
from pathlib import Path


def validate_interval(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 10 <= value <= 180:
        raise ValueError('抓取间隔必须是 10–180 分钟的整数')
    return value


def read_interval(path):
    try:
        config = json.loads(Path(path).read_text(encoding='utf-8'))
        return validate_interval(config.get('interval_minutes', 60))
    except (OSError, ValueError, TypeError):
        return 60


def write_interval(path, value):
    value = validate_interval(value)
    path = Path(path)
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(config, dict):
            raise ValueError()
    except (OSError, ValueError):
        raise ValueError('无法读取抓取配置，请先完成本机部署') from None
    config['interval_minutes'] = value
    temp = path.with_name(path.name + '.schedule.tmp')
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)
    return {'interval_minutes': value}
