"""Allowlisted, deterministic statistics: never eval, exec or run model-supplied SQL/Python."""
import pandas as pd
from .utils import safe_float

OPS = ('missingness', 'summary', 'duplicates', 'top_categories', 'group_sum',
       'group_mean', 'monthly_sum', 'correlation', 'outliers_iqr',
       'segment_share', 'monthly_change')


def action_signature(action):
    return (action['operation'], action.get('column'), action.get('metric'))


def validate_action(df, roles, a):
    if not isinstance(a, dict) or a.get('operation') not in OPS:
        raise ValueError('Operation is not on allowlist')
    op, col, metric = a['operation'], a.get('column'), a.get('metric')
    if col is not None and col not in df.columns:
        raise ValueError('Unknown column')
    if metric is not None and metric not in df.columns:
        raise ValueError('Unknown metric')
    if metric is not None and roles[metric] != 'measure':
        raise ValueError('Metric must be an approved numeric measure')
    if col is not None and roles[col] == 'sensitive':
        raise ValueError('Sensitive columns cannot be analyzed at individual level')
    if op in ('group_sum', 'group_mean', 'segment_share'):
        if col is None or metric is None or roles[col] != 'dimension':
            raise ValueError('Group operation requires dimension and numeric measure')
        if df[col].nunique(dropna=False) > 50:
            raise ValueError('Too many dimension groups')
    if op in ('monthly_sum', 'monthly_change') and (col is None or metric is None or roles[col] != 'date'):
        raise ValueError('Monthly operation requires date and numeric measure')
    if op == 'top_categories' and (col is None or roles[col] != 'dimension'):
        raise ValueError('Category operation requires dimension')
    if op == 'outliers_iqr' and (col is None or roles[col] != 'measure'):
        raise ValueError('Outlier operation requires numeric measure')


def _months(df, col, metric):
    parsed = pd.to_datetime(df[col], errors='coerce', format='mixed')
    if parsed.notna().mean() < .8:
        raise ValueError('Less than 80% of dates are parseable')
    work = pd.DataFrame({'month': parsed.dt.to_period('M'), 'value': df[metric]})
    grouped = work.loc[parsed.notna()].groupby('month')['value'].sum().sort_index()
    return [{'month': str(k), 'value': safe_float(v)} for k,v in grouped.items()]


def execute(df, roles, action):
    validate_action(df, roles, action)
    op, col, metric = action['operation'], action.get('column'), action.get('metric')
    if op == 'missingness':
        return [{'column': c, 'missing_count': int(df[c].isna().sum()),
                 'missing_pct': safe_float(df[c].isna().mean() * 100)} for c in df.columns]
    if op == 'duplicates':
        n = int(df.duplicated().sum())
        return [{'exact_duplicates': n, 'duplicate_pct': safe_float(n / len(df) * 100)}]
    if op == 'summary':
        return [{'column': c, 'count': int(df[c].notna().sum()),
                 'sum': safe_float(df[c].sum()), 'mean': safe_float(df[c].mean()),
                 'median': safe_float(df[c].median()), 'min': safe_float(df[c].min()),
                 'max': safe_float(df[c].max())}
                for c in df.columns if roles[c] == 'measure']
    if op == 'correlation':
        cols = [c for c in df.columns if roles[c] == 'measure']
        if len(cols) < 2:
            raise ValueError('At least two numeric measures required')
        mat = df[cols].corr()
        entries = [{'x': x, 'y': y, 'r': safe_float(mat.loc[x,y])}
                   for i,x in enumerate(cols) for y in cols[i+1:]]
        return sorted(entries, key=lambda r: abs(r['r'] or 0), reverse=True)[:20]
    if op == 'top_categories':
        vals = df[col].fillna('(Unknown)').astype(str).value_counts().head(20)
        return [{'category': str(k)[:120], 'count': int(v)} for k,v in vals.items()]
    if op in ('group_sum', 'group_mean', 'segment_share'):
        x = df.groupby(col, dropna=False)[metric]
        agg = x.mean() if op == 'group_mean' else x.sum(min_count=1)
        total = agg.sum() if op == 'segment_share' else None
        agg = agg.sort_values(ascending=False).head(20)
        return [{'category': str(k)[:120], 'value': safe_float(v),
                 **({'share_pct': safe_float(v / total * 100) if total else None} if op == 'segment_share' else {})}
                for k,v in agg.items()]
    if op in ('monthly_sum', 'monthly_change'):
        rows = _months(df, col, metric)
        if op == 'monthly_change':
            for i,row in enumerate(rows):
                prev = rows[i-1]['value'] if i else None
                row['change_pct'] = safe_float((row['value']-prev)/abs(prev)*100) if prev not in (None, 0) and row['value'] is not None else None
        return rows
    if op == 'outliers_iqr':
        s = df[col].dropna()
        if len(s) < 5:
            raise ValueError('Need at least five values')
        q1, q3 = s.quantile([.25,.75]); iqr = q3-q1
        low, high = q1 - 1.5*iqr, q3 + 1.5*iqr
        count = int(((s < low) | (s > high)).sum())
        return [{'column': col, 'count': count, 'pct': safe_float(count / len(s) * 100),
                 'lower_bound': safe_float(low), 'upper_bound': safe_float(high),
                 'note': 'IQR flags potential outliers, not necessarily errors.'}]
    raise AssertionError('Unreachable')
