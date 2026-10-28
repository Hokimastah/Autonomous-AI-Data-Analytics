import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run_id():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def sha256_file(path, block=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_float(value, digits=4):
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(n, digits) if math.isfinite(n) else None


def json_default(x):
    if hasattr(x, 'item'):
        return x.item()
    if isinstance(x, (datetime, Path)):
        return str(x)
    raise TypeError(f'Not JSON serializable: {type(x).__name__}')


def dump_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=json_default, allow_nan=False), encoding='utf-8')
    os.replace(tmp, path)


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def brief_error(exc):
    return f'{type(exc).__name__}: {str(exc)[:200]}'
