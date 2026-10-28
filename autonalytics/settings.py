from pathlib import Path
from urllib.parse import urlsplit
from .utils import load_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    'input_file': 'data/sales_demo.csv', 'goal': 'Explore important patterns and data quality',
    'mode': 'rules', 'model': 'qwen2.5:7b',
    'ollama_url': 'http://127.0.0.1:11434/api/chat', 'ollama_timeout_seconds': 60,
    'max_steps': 12, 'max_seconds': 600, 'max_rows': 200000, 'max_columns': 100,
    'max_file_mb': 100, 'max_charts': 10, 'cleaning': 'propose',
    'derived_metrics': {}, 'semantic_overrides': {},
    'alerts': {'missing_pct': 20, 'duplicate_pct': 3, 'monthly_drop_pct': 30}
}


def load_config(path=None, overrides=None):
    cfg = dict(DEFAULTS)
    file = Path(path).resolve() if path else ROOT / 'config.json'
    if file.is_file():
        loaded = load_json(file)
        if not isinstance(loaded, dict):
            raise ValueError('Configuration must be a JSON object')
        unknown = set(loaded) - set(DEFAULTS)
        if unknown:
            raise ValueError(f'Unknown configuration keys: {sorted(unknown)}')
        cfg.update(loaded)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    if cfg['mode'] not in ('rules', 'auto', 'ollama'):
        raise ValueError('mode must be rules, auto, or ollama')
    if cfg['cleaning'] not in ('off', 'propose'):
        raise ValueError('cleaning must be off or propose; approval file required to apply')
    for key, low, high in [('max_steps', 1, 40), ('max_seconds', 5, 86400),
                            ('max_rows', 10, 1000000), ('max_columns', 1, 300),
                            ('max_file_mb', 1, 1024), ('max_charts', 0, 40),
                            ('ollama_timeout_seconds', 1, 300)]:
        cfg[key] = int(cfg[key])
        if not low <= cfg[key] <= high:
            raise ValueError(f'{key} must be in {low}..{high}')
    endpoint = urlsplit(str(cfg['ollama_url']))
    if endpoint.scheme != 'http' or endpoint.hostname not in ('localhost', '127.0.0.1', '::1') or endpoint.path != '/api/chat':
        raise ValueError('Ollama URL must use a local HTTP /api/chat endpoint (privacy protection)')
    if not isinstance(cfg['derived_metrics'], dict) or not isinstance(cfg['semantic_overrides'], dict):
        raise ValueError('derived_metrics and semantic_overrides must be objects')
    return cfg


def file_in_data(path):
    root = (ROOT / 'data').resolve()
    path = Path(path)
    candidate = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError('Input must be inside project data/ directory')
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate
