# Autonomous AI Data Analytics — Complete Local Project v1.0

A fully local-first **bounded autonomous analytics agent** with deterministic computation and optional **Ollama** planning/narratives. It reads real CSV/XLSX/Parquet datasets, infers column semantics, proposes data cleaning for approval, executes safe statistical analyses, records every decision, makes offline Plotly dashboards, and stores persistent run history with step-by-step checkpoints.

> **Scope:** Complete runnable implementation of a bounded analytics workflow, not an unrestricted data scientist. Neither model output nor uploaded data can execute arbitrary Python/SQL. Evidence comes from code; LLM commentary is labeled *draft* and must be reviewed.

## 1. Quick start — Windows PowerShell

1. Install Python 3.11+ (recommended 3.11 or 3.12) and extract this project.
2. Open VS Code terminal in the project root.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py run --mode rules
```

It uses bundled **synthetic** `data/sales_demo.csv` and works immediately without any AI model or Internet access once dependencies are installed. Open `outputs/<run_id>/report.html` in your browser. Charts work offline when the whole output folder is preserved.

If you don't have Python 3.11, replace `py -3.11` with the Python version you installed (3.11 or newer).

## 2. Enable an actual autonomous AI planner (optional)

Install Ollama from https://ollama.com/download, then:

```powershell
ollama pull qwen2.5:7b
python main.py run --mode auto
```

- `--mode rules`: deterministic adaptive planner only; requires no LLM.
- `--mode auto`: local Ollama selects from prevalidated candidate IDs; if unreachable, gracefully falls back to rules.
- `--mode ollama`: strict LLM; a planner failure stops the run with `failed` status.

By default only the loopback HTTP endpoint `http://127.0.0.1:11434/api/chat` is allowed. The LLM receives column names/roles, missingness percentages and **aggregate analysis summaries**, not raw rows. For sensitive datasets, review column names and LLM model/privacy settings first. **This is not a security guarantee against an already compromised local machine.**

## 3. Optional graphical UI

```powershell
pip install -r requirements-ui.txt
streamlit run app.py --server.address 127.0.0.1
```

Then open the local URL printed by Streamlit. Upload a CSV/XLSX, define your goal, run analysis, review reports, and approve proposed cleaning operations. Parquet needs `pip install pyarrow`.

## 4. Analyze your own data

Copy your file to `data/` (input paths outside that directory are blocked):

```powershell
python main.py run --input data/orders_2026.csv --goal "Analyse sales trends, region, products, anomalies" --mode rules --max-steps 15
```

Alternatively change `config.json`. Supports UTF-8 CSV, Excel XLSX (first worksheet), and Parquet (optional pyarrow). File, row, column, duration, step and chart limits are configurable.

### Semantic layer

Each column is categorized as `measure`, `dimension`, `date`, `identifier`, or `sensitive` based on dtype and naming patterns. Set explicit `semantic_overrides` in `config.json` for reliability. The shipped config has **no dataset-specific overrides or derived metrics**, so you can analyze your own schema immediately. **Unknown column names should be reviewed.** The agent never groups by sensitive columns and won't aggregate identifiers as numeric measures.

Optional derived metrics use **only an allowlisted multiply formula**, e.g.:

```json
"derived_metrics": {
  "line_value": {"multiply": ["quantity", "unit_price"]}
}
```

No arbitrary formulas or custom Python are executed.

## 5. Review and apply data cleaning (two-phase approval)

1. Run a normal analysis. The agent writes `outputs/<RUN_ID>/cleaning_proposals.json`.
2. Inspect that file. It lists operations, affected rows and risks.
3. Explicitly approve chosen operations:

```powershell
python main.py approve --run-id <RUN_ID> --all
# or select granular IDs:
python main.py approve --run-id <RUN_ID> --ids abc123def456
```

4. Start a **new** analysis, supplying the approval artifact:

```powershell
python main.py run --approval-file outputs/<RUN_ID>/approvals.json
```

The input SHA256 and exact proposal set must match current data or cleaning is rejected. The run writes a new `cleaned_dataset.csv` and records every change. **Original input is never overwritten.** Available low-risk proposals: exact duplicate-row removal, numeric median imputation, missing-category label and whitespace trim. These can still change interpretation; use judgment.

`--cleaning` is defined in `config.json`: `off` or `propose`; cleaning is never applied automatically.

## 6. Memory, resume, and automation

All runs are indexed in `outputs/run_history.sqlite`:

```powershell
python main.py history
```

For interrupted runs, each successful/rejected step is checkpointed to `outputs/<RUN_ID>/state.json`:

```powershell
python main.py run --resume <RUN_ID>
```

Resume requires **unchanged input SHA256 and config**. Already-committed steps will not be repeated. A crash during the middle of a step can rerun that *one unfinished step*.

To poll on changes:

```powershell
python main.py watch --interval-minutes 30
# single scheduled invocation (recommended with Windows Task Scheduler):
python main.py watch --once
```

File-hash and goal deduplication prevents repeat analysis of an already completed identical input. If an unfinished matching job has a valid checkpoint, `watch` resumes it before creating a new run. For reliable startup after Windows restarts, a sample `scripts/schedule_windows_example.ps1` shows a Task Scheduler registration (edit the project path first). If the goal changes, it triggers a new analysis.

## 7. What gets produced

```text
outputs/
  run_history.sqlite
  <RUN_ID>/
    state.json                 # atomic step checkpoint
    audit.json                 # all decisions, records, errors, source checksum
    profile.json               # data dictionary and quality
    evidence.json              # deterministic, source-step-grounded findings
    alerts.json                # threshold alerts
    cleaning_proposals.json    # manual review
    approvals.json             # when explicitly approved (original run)
    approved_plan.json         # when a run applies approved cleaning
    cleaned_dataset.csv        # only when approved operations were applied
    report.html                # offline dashboard and insights
    charts/                    # interactive offline HTML + plotly.min.js
```

## 8. Supported analysis operations

- `missingness`, `duplicates`, `summary`
- `top_categories`, `group_sum`, `group_mean`, `segment_share`
- `monthly_sum`, `monthly_change`
- `correlation` (Pearson), `outliers_iqr` (descriptive only)

AI planning is autonomous **within these tools**. On each step it receives current metadata, previously computed summaries, a fresh set of available tools, and an execution budget. It returns only a candidate ID; Python checks arguments and computes results. The adaptive rule planner prioritizes data quality and business objective terms, and unlocks monthly-change analysis after monthly sums.

## 9. Limitations & safety

- Does not learn causal relationships, predict future sales, build ML models, query arbitrary websites, write SQL, or fabricate decisions. Correlations are not causes.
- Does not automatically recognize all business KPIs; review `semantic_overrides` and derived-metric definitions. Numeric outlier flags are not necessarily bad data.
- LLM-generated narrative can hallucinate; only `evidence.json` contains deterministic, checked source-step summaries. The narrative references evidence IDs but wording itself is not numerically verified.
- Trends include potentially incomplete months; verify date coverage and reporting periods.
- Multiple table joins, database connectors, advanced forecasting, user authentication, multi-user isolation, and cloud deployment are **not included**.
- The Streamlit UI is intended for a single user on `127.0.0.1`. Do not expose it on a public network.
- No credentials are stored. Files can contain sensitive data and will be stored locally in `data/` or `outputs/`.
- `max_seconds` limits the overall planner loop between operations; a single Ollama request can take as long as the configured request timeout, so a hard OS-level timeout may still be necessary.
- Source fingerprints are based on input bytes. `watch` deduplication uses source hash + goal, not every config option; when tuning config, run explicit `run`.

## 10. Run tests

```powershell
pip install pytest
python -m pytest -q
```

## Structure

```text
main.py                       CLI: run, approve, history, watch
app.py                        optional Streamlit local UI
config.json                   guardrails, semantics, KPI config
requirements.txt              minimal dependencies
requirements-ui.txt           optional Streamlit
generate_sample.py             reproducible synthetic example generator

autonalytics/
    settings.py               config validation and data/ sandbox
    ingest.py                 safe CSV/XLSX/Parquet ingestion
    semantics.py              profiles, roles and constrained derived KPI
    cleaning.py               proposals and human approvals
    operations.py             allowlisted statistical tools
    planner.py                adaptive ranked candidates
    llm.py                    Ollama structured output & draft insights
    insights.py               deterministic evidence & alert thresholds
    runner.py                 resume-aware autonomous orchestrator
    reporting.py              offline Plotly dashboards & HTML reports
    storage.py                persistent SQLite memory
    utils.py                  hashes, JSON atomic persistence

scripts/                       optional Windows convenience examples
tests/                         automated smoke, quality and safety tests
```

### References

- Ollama JSON schema outputs: https://docs.ollama.com/api
- Streamlit local app: https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader

License: MIT (see LICENSE). Example data are synthetic.
