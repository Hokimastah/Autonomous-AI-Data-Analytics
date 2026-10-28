"""Adaptive candidate ranking with explicit decision budget and no duplicate actions."""
from .operations import action_signature


def candidates(df, roles, goal, history):
    seen = {action_signature(item['action']) for item in history}
    numerical = [c for c,role in roles.items() if role == 'measure']
    dimensions = [c for c,role in roles.items() if role == 'dimension' and 1 < df[c].nunique(dropna=True) <= 50]
    dates = [c for c,role in roles.items() if role == 'date']
    goal_l = goal.lower()
    trend = any(x in goal_l for x in ('trend','tren','time','growth','bulan','season','waktu'))
    group = any(x in goal_l for x in ('product','produk','region','wilayah','segment','kategori','contribut','kontribusi'))
    quality = any(x in goal_l for x in ('quality','kualitas','missing','duplicate','clean','anomaly','anomali'))
    priority = [c for c in numerical if any(k in c.lower() for k in ('revenue', 'omzet', 'sales', 'profit', 'line_value', 'total'))]
    priority += [c for c in numerical if c not in priority]
    options = []
    def add(op, score, why, col=None, metric=None):
        obj = {'operation':op, 'column': col, 'metric': metric, 'reason':why}
        if action_signature(obj) not in seen:
            options.append({'id': f'c{len(options)+1:03d}', 'score':round(score,2), 'action':obj})
    missing_signal = any(float(df[c].isna().mean()) > .05 for c in df.columns)
    add('missingness', 95 if quality or missing_signal else 70, 'Check missing values')
    add('duplicates', 90 if quality else 57, 'Check exact-row duplicates')
    if numerical:
        add('summary', 92, 'Establish numeric baselines')
    if len(numerical) >= 2:
        add('correlation', 48, 'Check numerical relationships without causal inference')
    for c in priority[:4]:
        add('outliers_iqr', 55 if quality else 35, 'Detect potentially extreme values', col=c)
    for c in dimensions[:5]:
        add('top_categories', 61 if group else 40, 'Assess frequency of categories', col=c)
        for metric in priority[:3]:
            add('group_sum', 83 if group else 65, 'Rank contributions by dimension', col=c, metric=metric)
            add('segment_share', 77 if group else 57, 'Measure proportional contribution', col=c, metric=metric)
            add('group_mean', 42, 'Compare group averages', col=c, metric=metric)
    for date in dates[:2]:
        for metric in priority[:3]:
            add('monthly_sum', 94 if trend else 72, 'Inspect monthly trend', col=date, metric=metric)
            # Adaptive: monthly change is valuable after previous monthly aggregation.
            prior_monthly = any(x['status']=='ok' and x['action']['operation']=='monthly_sum' and
                                x['action'].get('column')==date and x['action'].get('metric')==metric for x in history)
            if prior_monthly:
                add('monthly_change', 94 if trend else 68, 'Quantify month-to-month changes', col=date, metric=metric)
    options.sort(key=lambda z: (-z['score'], z['id']))
    return options[:40]


def choose_rules(options):
    return options[0] if options else None
