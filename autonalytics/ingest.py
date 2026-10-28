from pathlib import Path
import pandas as pd


def ingest(path: Path, cfg):
    if path.stat().st_size > cfg['max_file_mb'] * 1024 * 1024:
        raise ValueError('File exceeds max_file_mb')
    suffix = path.suffix.lower()
    if suffix == '.csv':
        try:
            df = pd.read_csv(path, nrows=cfg['max_rows'] + 1, encoding='utf-8-sig', low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(path, nrows=cfg['max_rows'] + 1, encoding='latin-1', low_memory=False)
    elif suffix == '.xlsx':
        df = pd.read_excel(path, engine='openpyxl', nrows=cfg['max_rows'] + 1)
    elif suffix == '.parquet':
        try:
            df = pd.read_parquet(path)
        except ImportError as err:
            raise ValueError('Parquet needs optional dependency: pip install pyarrow') from err
    else:
        raise ValueError('Supported files: .csv, .xlsx, .parquet')
    if df.empty or len(df) > cfg['max_rows'] or len(df.columns) > cfg['max_columns']:
        raise ValueError('Empty or oversized dataset (row/column limit reached)')
    df.columns = [str(c).strip() for c in df.columns]
    if not df.columns.is_unique or any(not c for c in df.columns):
        raise ValueError('Duplicate or empty column names')
    return df
