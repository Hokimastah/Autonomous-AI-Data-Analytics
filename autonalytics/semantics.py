import re
import pandas as pd
from .utils import safe_float

DATE_WORDS = ('date', 'tanggal', 'time', 'waktu', 'bulan', 'created_at', 'timestamp')
ID_WORDS = ('_id', 'id_', 'uuid', 'kode', 'code', 'nomor', 'number', 'invoice', 'sku')
METRIC_WORDS = ('revenue', 'sales', 'omzet', 'pendapatan', 'jumlah', 'amount', 'qty', 'quantity',
                'price', 'harga', 'biaya', 'cost', 'profit', 'margin', 'total', 'value', 'nilai')
SENSITIVE_WORDS = ('email', 'phone', 'telp', 'alamat', 'address', 'nik', 'passport', 'password', 'token', 'secret')


def likely_date(col, series):
    name = col.lower()
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if pd.api.types.is_numeric_dtype(series) or not any(k in name for k in DATE_WORDS):
        return False
    sample = series.dropna().head(80)
    if len(sample) == 0:
        return False
    try:
        parsed = pd.to_datetime(sample, errors='coerce', format='mixed')
        return float(parsed.notna().mean()) >= .8
    except (ValueError, TypeError, OverflowError):
        return False


def infer_semantics(df, overrides=None):
    overrides = overrides or {}
    result = {}
    allowed = {'measure', 'dimension', 'date', 'identifier', 'sensitive'}
    if any(k not in df.columns for k in overrides):
        raise ValueError('Semantic override contains unknown column')
    for col in df.columns:
        s = df[col]
        low = col.lower()
        if col in overrides:
            role = overrides[col]
            if role not in allowed:
                raise ValueError(f'Unknown semantic role {role}')
        elif any(word in low for word in SENSITIVE_WORDS):
            role = 'sensitive'
        elif likely_date(col, s):
            role = 'date'
        elif (low == 'id' or any(word in low for word in ID_WORDS)):
            role = 'identifier'
        elif pd.api.types.is_numeric_dtype(s):
            role = 'measure' if any(word in low for word in METRIC_WORDS) else ('identifier' if s.nunique() == len(df) and len(df) > 30 else 'measure')
        else:
            role = 'dimension' if s.nunique(dropna=True) <= max(50, len(df)//3) else 'identifier'
        # Even erroneous overrides cannot enable aggregating strings as measures
        if role == 'measure' and not pd.api.types.is_numeric_dtype(s):
            raise ValueError(f'Measure {col} is not numeric')
        result[col] = role
    return result


def derive_metrics(df, config):
    """Safe derived metrics: multiplication of two existing numeric columns only."""
    df = df.copy()
    for name, spec in config.items():
        if name in df.columns or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError(f'Invalid or already-existing derived metric {name}')
        if not isinstance(spec, dict) or set(spec) != {'multiply'} or not isinstance(spec['multiply'], list) or len(spec['multiply']) != 2:
            raise ValueError('Derived metric must specify {"multiply": ["numeric_col1", "numeric_col2"]}')
        a, b = spec['multiply']
        if any(c not in df.columns or not pd.api.types.is_numeric_dtype(df[c]) for c in (a, b)):
            raise ValueError(f'Derived metric {name} needs two existing numeric columns')
        df[name] = df[a].mul(df[b])
    return df


def profile(df, roles, source_hash, source_name):
    entries = []
    for col in df.columns:
        s = df[col]
        values = {'name': col, 'role': roles[col], 'dtype': str(s.dtype),
                  'missing': int(s.isna().sum()), 'missing_pct': round(float(s.isna().mean()*100), 2),
                  'unique': int(s.nunique(dropna=True))}
        if roles[col] == 'measure':
            values['mean'] = safe_float(s.mean())
            values['sum'] = safe_float(s.sum())
        entries.append(values)
    duplicates = int(df.duplicated().sum())
    return {'source_name': source_name, 'source_sha256': source_hash,
            'rows': int(len(df)), 'columns': int(len(df.columns)),
            'duplicates': duplicates, 'duplicate_pct': round(100 * duplicates/len(df), 2),
            'roles': roles, 'column_info': entries}
