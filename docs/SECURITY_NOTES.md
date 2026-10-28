# Threat model and safeguards

- Goal: single-user, localhost analytics for untrusted CSV/XLSX data.
- The model only selects IDs from validated candidates; it never executes arbitrary model-generated Python/SQL, never shells out, never edits source.
- Input files resolve under `data/`, preventing path traversal and symlinks pointing outside.
- File size / row count / column count / step count / chart count / per-request LLM timeout are bounded. In-memory Parquet or pathological XLSX expansion can still exhaust memory; OS resource limits are recommended for unknown files.
- The model endpoint is restricted to local HTTP loopback. Only column-level metadata, missingness and short aggregate summaries go into its context.
- Cleaning proposals must match the same raw source fingerprint and algorithmically regenerated proposal set, and selected IDs require a separate user approval artifact.
- HTML report text is escaped. Plotly renders untrusted column/category labels as data; use caution if consuming hostile inputs in a shared browser.
- The UI stores uploaded files on disk. Use disk encryption if datasets are sensitive. Do not run Streamlit with public bind address.
- SQLite is a local audit index, not a tamper-proof ledger. An admin/root account can edit it.
- LLM-written narratives are clearly separated from computed evidence; they require human review.
- `max_seconds` is a cooperative budget checked between steps; it does not forcibly interrupt a running LLM request. Use process-level monitoring if required.
