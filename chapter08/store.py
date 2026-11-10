"""Load the four feeds and write sources and cases to SQLite.

load_sources() reads the CSV feeds with their timestamps parsed.
save() creates dispute.db from dispute_schema.sql, lands each feed unchanged
(plus a load timestamp), and writes case_record, case_source_link and a
case_created event for every case. Dates become ISO text and missing values
become SQL NULLs on the way in.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "dispute.db"
SCHEMA = HERE / "dispute_schema.sql"

FEEDS = {
    "authorization": ["authorized_at"],
    "clearing": ["cleared_at"],
    "crm_claim": ["claim_received_at"],
    "merchant_order": ["ordered_at", "shipped_at", "delivered_at"],
}


def load_sources(folder=HERE):
    return {name: pd.read_csv(Path(folder) / f"{name}.csv", parse_dates=dates,
                              dtype={"auth_code": str})
            for name, dates in FEEDS.items()}


def _sql_rows(df):
    """Timestamps to ISO text, NaN/NaT/NA to None, numpy scalars to Python."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
    out = out.astype(object).where(out.notna(), None)
    return [tuple(v.item() if hasattr(v, "item") else v for v in row)
            for row in out.itertuples(index=False)]


def _insert(con, table, df):
    cols = ", ".join(df.columns)
    marks = ", ".join("?" for _ in df.columns)
    con.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", _sql_rows(df))


def connect(path=DB_PATH):
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def save(src, cases, links, path=DB_PATH):
    """Rebuild the database: schema, source tables as received, then the cases."""
    path = Path(path)
    if path.exists():
        path.unlink()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = connect(path)
    with con:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        for name in FEEDS:
            _insert(con, name, src[name].assign(loaded_at=now))
        # first cases, then duplicates that point to them (self-reference)
        cases = cases.sort_values("duplicate_of", na_position="first", key=lambda s: s.notna())
        _insert(con, "case_record", cases)
        _insert(con, "case_source_link", links.assign(linked_at=now))
        events = pd.DataFrame({"case_id": cases.case_id, "event_at": cases.claim_received_at,
                               "event_type": "case_created", "from_state": None,
                               "to_state": "CLAIM_RECEIVED", "source": "assemble_case"})
        _insert(con, "case_event", events)
    con.close()
    return path
