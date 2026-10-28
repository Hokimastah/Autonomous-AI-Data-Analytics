import json
import sqlite3
from pathlib import Path
from .settings import ROOT
from .utils import utc_now

DB = ROOT / 'outputs' / 'run_history.sqlite'


def connect():
    DB.parent.mkdir(exist_ok=True,parents=True)
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute('''CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY, started_utc TEXT, completed_utc TEXT,
        source_file TEXT, source_sha256 TEXT, goal TEXT, status TEXT,
        steps INTEGER, output_path TEXT, summary TEXT)''')
    conn.execute('CREATE INDEX IF NOT EXISTS ix_run_source ON runs(source_sha256, goal)')
    return conn


def save_run(state, output_path):
    with connect() as conn:
        conn.execute('''INSERT INTO runs(run_id, started_utc, completed_utc, source_file,
                        source_sha256, goal, status, steps, output_path, summary)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(run_id) DO UPDATE SET completed_utc=excluded.completed_utc,
                        status=excluded.status, steps=excluded.steps, summary=excluded.summary''',
                     (state['run_id'], state['started_utc'],utc_now(),state['source_file'],
                      state['source_sha256'],state['goal'],state['status'],len(state['history']),
                      str(output_path),json.dumps({'evidence_count':len(state.get('evidence',[])),
                                                   'alerts':len(state.get('alerts',[]))})))


def recent_runs(limit=20):
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute('SELECT * FROM runs ORDER BY started_utc DESC LIMIT ?', (min(int(limit),100),))]


def already_processed(sha, goal):
    with connect() as conn:
        return conn.execute('SELECT run_id FROM runs WHERE source_sha256=? AND goal=? AND status="complete" LIMIT 1',
                            (sha,goal)).fetchone() is not None


def interrupted_run(sha, goal, cfg_hash):
    """Return a matching checkpointed running job, if one exists."""
    from .utils import load_json
    with connect() as conn:
        rows = conn.execute('SELECT run_id, output_path FROM runs WHERE source_sha256=? AND goal=? AND status="running" ORDER BY started_utc DESC LIMIT 10',
                            (sha,goal)).fetchall()
    for rid, output_path in rows:
        checkpoint = Path(output_path)/'state.json'
        if checkpoint.is_file():
            try:
                state=load_json(checkpoint)
                if state.get('config_sha256')==cfg_hash and state.get('source_sha256')==sha:
                    return rid
            except (OSError, ValueError, KeyError):
                pass
    return None
