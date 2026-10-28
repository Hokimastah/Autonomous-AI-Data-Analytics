import html
import json
from pathlib import Path
import pandas as pd
import plotly.express as px

from .utils import dump_json


def chart_for(action, records, out, n):
    if not records:
        return None
    op = action['operation']
    d = pd.DataFrame(records)
    if op in ('group_sum', 'group_mean', 'segment_share'):
        fig = px.bar(d.head(20), x='category', y='value', title=f"{op}: {action['metric']} by {action['column']}")
    elif op == 'top_categories':
        fig = px.bar(d.head(20), x='category', y='count', title=f"Category frequency: {action['column']}")
    elif op in ('monthly_sum', 'monthly_change'):
        fig = px.line(d, x='month', y='value', markers=True, title=f"Monthly {action['metric']}")
    elif op == 'missingness':
        d = d[d['missing_pct']>0].sort_values('missing_pct', ascending=False).head(20)
        if d.empty: return None
        fig = px.bar(d,x='column',y='missing_pct',title='Missing data (%)')
    elif op == 'correlation':
        d = d[d['r'].notna()]
        if d.empty: return None
        d['pair'] = d['x'] + ' / ' + d['y']
        fig = px.bar(d.head(15),x='pair',y='r',title='Pearson correlations (not causality)')
    else:
        return None
    chart_dir = out / 'charts'
    chart_dir.mkdir(exist_ok=True)
    dest = chart_dir / f'chart_{n:02d}.html'
    # Writes local plotly.min.js once: dashboard works without an Internet connection.
    fig.write_html(str(dest), include_plotlyjs='directory', full_html=True, auto_open=False)
    return 'charts/' + dest.name


def _esc(obj):
    return html.escape(str(obj), quote=True)


def render_report(state, out):
    charts = state.get('charts', [])
    profile = state['profile']
    evidence = state.get('evidence', [])
    narrative = state.get('narrative', [])
    alerts = state.get('alerts', [])
    css = '''body{font-family:system-ui,-apple-system,sans-serif;background:#f7f9fc;color:#172233;margin:0}
    .shell{max-width:1150px;margin:0 auto;padding:32px 22px}.hero{background:#152844;color:#fff;padding:26px;border-radius:16px}
    .muted{color:#67788a}.hero .muted{color:#b7c9db}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:14px;margin:18px 0}
    .card{background:white;border:1px solid #e3e9f0;border-radius:12px;padding:18px;box-shadow:0 1px 6px #18284109}
    .value{font-size:28px;font-weight:700}.section{margin-top:30px}p{line-height:1.55}code,pre{font-size:12px}
    table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid #dce5ee;text-align:left;padding:9px;font-size:13px}
    th{background:#ebf1f7}iframe{width:100%;height:440px;border:1px solid #e3e9f0;border-radius:12px;background:#fff}
    .pill{display:inline-block;border-radius:12px;padding:4px 9px;background:#edf2fb;margin:3px;font-size:12px}
    .warning{border-left:4px solid #e9a038}.note{border-left:4px solid #6c91d9}small{color:#67788a}
    .scroll{overflow-x:auto}a{color:#1464b5}'''
    s=['<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>Autonomous Analytics Report</title><style>',css,'</style></head><body><div class="shell">',
       f'<div class="hero"><h1>Autonomous Data Analytics</h1><p>{_esc(state["goal"])}</p>',
       f'<div class="muted">Run {_esc(state["run_id"])} • source {_esc(state["source_file"])} • {_esc(state["mode"])} mode</div></div>',
       '<div class="cards">']
    for label,value in [('Rows',profile['rows']),('Columns',profile['columns']),('Exact duplicates',profile['duplicates']),
                        ('Analysis steps',len(state['history'])),('Verified findings',len(evidence)),('Alerts',len(alerts))]:
        s.append(f'<div class="card"><div class="muted">{_esc(label)}</div><div class="value">{_esc(value)}</div></div>')
    s.append('</div><section class="section"><h2>Verified findings (computed from data)</h2>')
    if not evidence: s.append('<p>No verified findings available.</p>')
    for e in evidence:
        s.append(f'<div class="card note"><b>{_esc(e["evidence_id"])}</b> — {_esc(e["observation"])}</div>')
    s.append('</section><section class="section"><h2>Data quality alerts</h2>')
    if not alerts: s.append('<p>No alert crossed configured thresholds.</p>')
    for a in alerts: s.append(f'<div class="card warning"><b>{_esc(a["name"])}</b>: {_esc(a["detail"])}</div>')
    s.append('</section>')
    if narrative:
        s.append('<section class="section"><h2>LLM interpretations — draft, human verification required</h2>')
        for a in narrative:
            s.append(f'<div class="card"><b>Based on {_esc(a["evidence_id"])}</b><p>{_esc(a["observation"])}</p><small>Suggested next action: {_esc(a["next_action"])}</small></div>')
        s.append('</section>')
    s.append('<section class="section"><h2>Data dictionary</h2><div class="scroll"><table><thead><tr><th>Column</th><th>Role</th><th>Type</th><th>Missing %</th><th>Unique</th></tr></thead><tbody>')
    for c in profile['column_info']:
        s.append('<tr>'+''.join(f'<td>{_esc(c[k])}</td>' for k in ('name','role','dtype','missing_pct','unique'))+'</tr>')
    s.append('</tbody></table></div></section><section class="section"><h2>Charts (available offline)</h2>')
    for item in charts:
        s.append(f'<h3>{_esc(item["title"])}</h3><iframe loading="lazy" title="Chart" src="{_esc(item["file"])}"></iframe>')
    if not charts: s.append('<p>No chartable results.</p>')
    s.append('</section><section class="section"><h2>Agent decisions & execution log</h2>')
    for h in state['history']:
        a=h['action']; s.append(f'<div class="card"><b>Step {h["step"]}: {_esc(a["operation"])}</b> '
                               f'<span class="pill">{_esc(h["status"])}</span> <span class="pill">{_esc(h["planner"])}</span>'
                               f'<p>{_esc(h.get("summary", h.get("error", "")))}</p></div>')
    s.append('</section><section class="section"><h2>Downloads</h2>')
    for filename in ('profile.json','audit.json','evidence.json','cleaning_proposals.json','alerts.json'):
        if (out / filename).exists():
            s.append(f'<p><a href="{filename}">{filename}</a></p>')
    s.append('<p><small>This is observational analytics. Do not infer causality from correlation. '
             'Verify business context, missing data impacts and incomplete periods before acting. '
             'The original input file is never overwritten.</small></p></section></div></body></html>')
    path = out/'report.html'
    path.write_text('\n'.join(s),encoding='utf-8')
    return path


def write_outputs(state, out):
    dump_json(out/'profile.json', state['profile'])
    dump_json(out/'audit.json', state)
    dump_json(out/'evidence.json', state.get('evidence',[]))
    dump_json(out/'alerts.json', state.get('alerts',[]))
    return render_report(state,out)
