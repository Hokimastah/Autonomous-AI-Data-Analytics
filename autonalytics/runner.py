"""Stateful orchestrator: validated planning, deterministic execution, checkpoints and audit."""
import hashlib
import json
import shutil
import time
from pathlib import Path

from .cleaning import propose_cleaning, apply_approved
from .ingest import ingest
from .insights import build_alerts, build_evidence, describe_result
from .llm import choose_ollama, generate_narrative
from .operations import execute
from .planner import candidates, choose_rules
from .reporting import chart_for, write_outputs
from .semantics import derive_metrics, infer_semantics, profile
from .settings import ROOT, file_in_data
from .storage import save_run
from .utils import brief_error, dump_json, load_json, run_id, sha256_file, utc_now


def _config_hash(cfg):
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def run_pipeline(cfg, input_file=None, approval_file=None, resume=None, verbose=True):
    path = file_in_data(input_file or cfg['input_file'])
    src_hash = sha256_file(path)
    src_name = str(path.relative_to(ROOT)).replace('\\','/')
    output_root = ROOT / 'outputs'
    rid = resume or run_id()
    if not rid.replace('Z','').replace('T','').isdigit() or '/' in rid or '\\' in rid:
        raise ValueError('Invalid run ID')
    out = output_root / rid
    cfg_hash = _config_hash(cfg)
    if resume:
        if not (out / 'state.json').is_file():
            raise FileNotFoundError('No state.json for resumed run')
        state = load_json(out/'state.json')
        if (state['source_sha256'] != src_hash or state['source_file'] != src_name or
                state['config_sha256'] != cfg_hash):
            raise ValueError('Cannot resume: source file or configuration has changed')
        if state['status'] == 'complete':
            return {'run_id':rid, 'output_dir':str(out), 'report':str(out/'report.html'),
                    'state':state, 'resumed':True}
        if (out/'approved_plan.json').is_file():
            approval_file = str(out/'approved_plan.json')
    else:
        out.mkdir(parents=True, exist_ok=False)
        state = {'run_id':rid, 'source_file':src_name, 'source_sha256':src_hash,
                 'config_sha256':cfg_hash, 'started_utc':utc_now(), 'completed_utc':None,
                 'goal':cfg['goal'], 'mode':cfg['mode'], 'status':'running', 'stop_reason':None,
                 'history':[], 'charts':[], 'errors':[], 'applied_changes':[], 'narrative':[]}

    raw = ingest(path, cfg)
    raw_roles = infer_semantics(raw, {k:v for k,v in cfg['semantic_overrides'].items() if k in raw.columns})
    proposals = propose_cleaning(raw, raw_roles) if cfg['cleaning'] == 'propose' else []
    proposal_bundle = {'source_sha256':src_hash, 'source_file':src_name, 'proposals':proposals}
    dump_json(out/'cleaning_proposals.json', proposal_bundle)
    data = raw
    if approval_file:
        approval = load_json(approval_file)
        if approval['proposals'] != proposals:
            raise ValueError('Approval plans differ from freshly generated proposals (check data/config)')
        data, applied = apply_approved(raw, approval, src_hash, src_name)
        data.to_csv(out/'cleaned_dataset.csv', index=False, encoding='utf-8-sig')
        if not resume:
            shutil.copy2(approval_file, out/'approved_plan.json')
        state['applied_changes'] = applied
    elif resume and state.get('applied_changes'):
        raise ValueError('Resume requires the original approved plan')

    data = derive_metrics(data, cfg['derived_metrics'])
    roles = infer_semantics(data, {k:v for k,v in cfg['semantic_overrides'].items() if k in data.columns})
    prof = profile(data, roles, src_hash, src_name)
    state['profile'] = prof
    state['cleaning_proposal_count'] = len(proposals)
    dump_json(out/'profile.json', prof)
    dump_json(out/'state.json', state)
    save_run(state, out)
    tick = time.monotonic()

    # Continue from the checkpoint. Completed steps are never repeated.
    for step in range(len(state['history']) + 1, cfg['max_steps'] + 1):
        if time.monotonic() - tick >= cfg['max_seconds']:
            state['stop_reason'] = 'runtime_budget_reached'
            break
        options = candidates(data, roles, cfg['goal'], state['history'])
        if not options:
            state['stop_reason'] = 'no_more_valid_candidates'
            break
        selected = None
        planner_used = 'deterministic'
        if cfg['mode'] in ('auto', 'ollama'):
            try:
                selected = choose_ollama(cfg, options, prof, state['history'])
                planner_used = 'ollama'
            except Exception as exc:
                state['errors'].append(f'Planner step {step}: {brief_error(exc)}')
                if cfg['mode'] == 'ollama':
                    state['stop_reason'] = 'ollama_planner_error'
                    break
        if selected is None:
            selected = choose_rules(options)
        action = selected['action']
        entry = {'step':step, 'planner':planner_used, 'candidate_score':selected['score'],
                 'action':action, 'started_utc':utc_now()}
        try:
            records = execute(data, roles, action)
            entry.update({'status':'ok', 'records':records, 'summary':describe_result(action, records)})
            if len(state['charts']) < cfg['max_charts']:
                try:
                    chart_path = chart_for(action, records, out, step)
                    if chart_path:
                        state['charts'].append({'title':f"Step {step}: {action['operation']}", 'file':chart_path})
                except Exception as exc:
                    state['errors'].append(f'Chart step {step}: {brief_error(exc)}')
        except Exception as exc:
            entry.update({'status':'rejected', 'error':brief_error(exc)})
        entry['finished_utc'] = utc_now()
        state['history'].append(entry)
        dump_json(out/'state.json', state)
        save_run(state,out)
        if verbose:
            print(f"[{step}/{cfg['max_steps']}] {action['operation']:<16} {entry['status']:<10} ({planner_used})", flush=True)
    if state['stop_reason'] is None:
        state['stop_reason'] = 'max_steps_reached' if len(state['history']) >= cfg['max_steps'] else 'stopped'
    state['evidence'] = build_evidence(state['history'])
    state['alerts'] = build_alerts(prof, state['history'], cfg)
    if cfg['mode'] in ('auto','ollama') and state['evidence']:
        try:
            state['narrative'] = generate_narrative(cfg, state['evidence'])
        except Exception as exc:
            state['errors'].append(f'LLM narrative: {brief_error(exc)}')
    state['status'] = 'complete' if state['stop_reason'] != 'ollama_planner_error' else 'failed'
    state['completed_utc'] = utc_now()
    report_path = write_outputs(state, out)
    dump_json(out/'state.json', state)
    save_run(state,out)
    if verbose:
        print(f'Completed: {len(state["history"])} steps; status={state["status"]}; reason={state["stop_reason"]}')
        print(f'Report: {report_path}')
    return {'run_id':rid, 'output_dir':str(out), 'report':str(report_path),
            'state':state, 'resumed':bool(resume)}
