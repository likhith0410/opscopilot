"""Tool 3 — Metrics Parser.

Parses metrics.csv into a pandas DataFrame and supports time-range / column
queries. Returns numeric data with row numbers preserved for citations
(metrics.csv:L<row>).
"""

from __future__ import annotations

from io import StringIO

import pandas as pd


def parse_metrics(metrics_raw: str) -> pd.DataFrame:
    """Parse the raw CSV string into a DataFrame indexed by timestamp.

    The original 1-based CSV row number (header = row 1) is preserved in
    the column `csv_row`, so callers can build `metrics.csv:L<row>` citations.
    """
    if not metrics_raw.strip():
        return pd.DataFrame()
    df = pd.read_csv(StringIO(metrics_raw))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    # CSV row 1 = header; data rows start at 2
    df["csv_row"] = df.index + 2
    return df


def query_metrics(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[dict]:
    """Slice the DataFrame by time range and optionally select columns.

    Returns a list of dict rows (one per timestamp) with the requested columns
    plus `timestamp` (ISO string) and `csv_row` (citation row number).
    """
    if df.empty:
        return []

    out = df
    if start_time:
        out = out[out["timestamp"] >= pd.to_datetime(start_time, utc=True)]
    if end_time:
        out = out[out["timestamp"] <= pd.to_datetime(end_time, utc=True)]

    if columns:
        keep = ["timestamp", "csv_row", *columns]
        keep = [c for c in keep if c in out.columns]
        out = out[keep]

    records = out.to_dict(orient="records")
    # normalize timestamp back to ISO Z
    for r in records:
        r["timestamp"] = r["timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return records
