"""Reversible-by-design cleaning: only approved changes to in-memory copy, source remains untouched."""
import hashlib
import json
import pandas as pd
from .utils import dump_json, load_json


def proposal_id(operation, column=''):
    return hashlib.sha256(f'{operation}:{column}'.encode()).hexdigest()[:12]


def propose_cleaning(df, roles):
    suggestions = []
    duplicates = int(df.duplicated().sum())
    if duplicates:
        suggestions.append({'id': proposal_id('drop_exact_duplicates'), 'operation': 'drop_exact_duplicates',
                            'column': None, 'affected_rows': duplicates,
                            'explanation': 'Remove only completely identical rows; duplicated business identifiers are NOT automatically dropped.'})
    for col in df.columns:
        s = df[col]
        miss = int(s.isna().sum())
        if miss and miss / len(df) <= .30 and roles[col] == 'measure' and s.notna().sum() >= 3:
            suggestions.append({'id': proposal_id('fill_median', col), 'operation': 'fill_median',
                                'column': col, 'affected_rows': miss,
                                'explanation': 'Fill numeric missing cells with the median; this may bias downstream statistics.'})
        elif miss and roles[col] == 'dimension':
            suggestions.append({'id': proposal_id('fill_unknown', col), 'operation': 'fill_unknown',
                                'column': col, 'affected_rows': miss,
                                'explanation': 'Label missing categories as (Unknown); do not infer actual values.'})
        if pd.api.types.is_object_dtype(s) and roles[col] not in ('sensitive', 'identifier'):
            count = int(s.dropna().astype(str).ne(s.dropna().astype(str).str.strip()).sum())
            if count:
                suggestions.append({'id': proposal_id('trim_strings', col), 'operation': 'trim_strings',
                                    'column': col, 'affected_rows': count,
                                    'explanation': 'Remove surrounding whitespace; can merge category labels.'})
    return suggestions


def create_approval(proposal_path, ids=None, all_items=False):
    payload = load_json(proposal_path)
    proposals = payload['proposals']
    valid = {p['id'] for p in proposals}
    selection = valid if all_items else set(ids or [])
    if not selection or not selection <= valid:
        raise ValueError('Select valid approval IDs; no proposals matched')
    approval = {'source_sha256': payload['source_sha256'], 'source_file': payload['source_file'],
                'proposal_sha256': hashlib.sha256(json.dumps(proposals, sort_keys=True).encode()).hexdigest(),
                'approved_ids': sorted(selection), 'proposals': proposals}
    target = proposal_path.parent / 'approvals.json'
    dump_json(target, approval)
    return target


def apply_approved(df, approval, expected_hash, expected_path):
    if approval['source_sha256'] != expected_hash or approval['source_file'] != expected_path:
        raise ValueError('Approval source differs from current input; regenerate proposals')
    proposals = approval['proposals']
    actual_hash = hashlib.sha256(json.dumps(proposals, sort_keys=True).encode()).hexdigest()
    if approval.get('proposal_sha256') != actual_hash:
        raise ValueError('Approval proposal contents were modified')
    ids = approval['approved_ids']
    if not ids or len(ids) != len(set(ids)) or not set(ids) <= {p['id'] for p in proposals}:
        raise ValueError('Invalid approved IDs')
    # Recompute exact proposals on the SAME raw data, compare before proceeding.
    # Verified by the caller with expected_proposals argument after roles are inferred.
    clean = df.copy(deep=True)
    changes = []
    selected = {p['id']: p for p in proposals if p['id'] in ids}
    for p in proposals:
        if p['id'] not in selected:
            continue
        op, col = p['operation'], p['column']
        before = len(clean)
        if op == 'drop_exact_duplicates':
            clean = clean.drop_duplicates().reset_index(drop=True)
            changed = before - len(clean)
        elif op == 'fill_median':
            if col not in clean or not pd.api.types.is_numeric_dtype(clean[col]):
                raise ValueError('Invalid numeric cleaning target')
            changed = int(clean[col].isna().sum())
            median = clean[col].median()
            if pd.isna(median):
                raise ValueError('Cannot impute all-missing measure')
            clean[col] = clean[col].fillna(median)
        elif op == 'fill_unknown':
            if col not in clean:
                raise ValueError('Invalid category cleaning target')
            changed = int(clean[col].isna().sum())
            clean[col] = clean[col].fillna('(Unknown)')
        elif op == 'trim_strings':
            if col not in clean:
                raise ValueError('Invalid text cleaning target')
            changed = int(clean[col].dropna().astype(str).ne(clean[col].dropna().astype(str).str.strip()).sum())
            clean[col] = clean[col].map(lambda v: v.strip() if isinstance(v, str) else v)
        else:
            raise ValueError('Unsupported cleaning operation')
        changes.append({'id': p['id'], 'operation': op, 'column': col, 'actual_changed': changed})
    return clean, changes
