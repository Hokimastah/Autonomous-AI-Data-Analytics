"""Evidence produced deterministically from actual data, never by model estimation."""
from .utils import safe_float


def describe_result(action, records):
    op = action['operation']
    if not records:
        return f'{op}: no data available'
    if op == 'missingness':
        significant = sorted(records, key=lambda r:r['missing_pct'], reverse=True)
        r = significant[0]
        return f"Maximum missing: {r['column']} ({r['missing_pct']}%)."
    if op == 'duplicates':
        return f"Found {records[0]['exact_duplicates']} exact duplicate rows."
    if op == 'summary':
        return f'Computed descriptive statistics for {len(records)} numeric measures.'
    if op in ('group_sum','group_mean','segment_share'):
        best = records[0]
        share = f" ({best['share_pct']}% share)" if 'share_pct' in best else ''
        return f"Top {action['column']}: {best['category']} = {best['value']}{share}."
    if op == 'top_categories':
        return f"Most frequent {action['column']}: {records[0]['category']} ({records[0]['count']} rows)."
    if op == 'monthly_sum':
        return f"Summed {action['metric']} across {len(records)} months; latest {records[-1]['month']} = {records[-1]['value']}."
    if op == 'monthly_change':
        changes = [x for x in records if x.get('change_pct') is not None]
        if changes:
            peak = max(changes, key=lambda r: abs(r['change_pct']))
            return f"Largest absolute MoM change: {peak['month']} ({peak['change_pct']}%)."
        return 'No comparable month-to-month values.'
    if op == 'correlation':
        top = records[0]
        return f"Strongest sampled Pearson correlation: {top['x']} vs {top['y']} (r={top['r']}); not causal."
    if op == 'outliers_iqr':
        return f"{records[0]['count']} potential IQR outliers in {action['column']}."
    return f'Executed {op}.'


def build_evidence(history):
    out=[]
    for h in history:
        if h['status'] != 'ok':
            continue
        summary = h.get('summary', '')
        if summary:
            out.append({'evidence_id':f"step-{h['step']}", 'operation':h['action']['operation'],
                        'observation':summary})
    return out


def build_alerts(prof, history, settings):
    conf = settings['alerts']
    alerts = []
    for col in prof['column_info']:
        if col['missing_pct'] >= float(conf['missing_pct']):
            alerts.append({'level':'warning', 'name':'missing_values', 'detail':f"{col['name']} missing {col['missing_pct']}%"})
    if prof['duplicate_pct'] >= float(conf['duplicate_pct']):
        alerts.append({'level':'warning','name':'duplicates',
                       'detail':f"Exact duplicate rows: {prof['duplicate_pct']}%"})
    for h in history:
        if h['status'] != 'ok' or h['action']['operation'] != 'monthly_change':
            continue
        for row in h['records']:
            ch = row.get('change_pct')
            if ch is not None and ch <= -abs(float(conf['monthly_drop_pct'])):
                alerts.append({'level':'warning','name':'monthly_drop',
                               'detail':f"{h['action']['metric']} declined {abs(ch)}% in {row['month']} vs prior month; check partial-month effects"})
    return alerts[:30]
