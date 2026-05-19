"""Tool 4 — Anomaly Detector.

Detects significant changes / spikes in a metric time series using a rolling-
baseline z-score plus a relative-change threshold. Returns the anomaly points
with citations (metrics.csv:L<row>) and a severity rating.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass
class Anomaly:
    timestamp: str
    metric: str
    value: float
    baseline: float
    z_score: float
    relative_change_pct: float
    severity: str  # "minor" | "major" | "critical"
    citation: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "metric": self.metric,
            "value": self.value,
            "baseline": round(self.baseline, 2),
            "z_score": round(self.z_score, 2),
            "relative_change_pct": round(self.relative_change_pct, 1),
            "severity": self.severity,
            "citation": self.citation,
        }


def _classify(z: float, rel_pct: float) -> str | None:
    """Return severity label or None if not anomalous."""
    if abs(z) >= 5 or abs(rel_pct) >= 200:
        return "critical"
    if abs(z) >= 3 or abs(rel_pct) >= 100:
        return "major"
    if abs(z) >= 2 or abs(rel_pct) >= 50:
        return "minor"
    return None


def detect_anomalies(
    rows: list[dict],
    metric: str,
    *,
    baseline_window: int = 15,
    min_baseline_value: float = 1.0,
) -> list[dict]:
    """Detect anomalies in the column `metric` from a list of metric rows.

    Args:
        rows: output of `query_metrics(...)` — list of dicts each having keys
            `timestamp`, `csv_row`, and the metric column.
        metric: name of the column to analyse.
        baseline_window: number of preceding points used to compute the rolling
            baseline (mean + stdev). Must be >= 3.
        min_baseline_value: floor for the baseline to avoid divide-by-zero on
            metrics that are near-zero in steady state.

    Returns a list of anomaly dicts sorted by timestamp.
    """
    if baseline_window < 3:
        raise ValueError("baseline_window must be >= 3")
    if not rows:
        return []

    anomalies: list[Anomaly] = []
    series: list[float] = []

    for row in rows:
        if metric not in row:
            raise KeyError(f"metric column '{metric}' not in row {row}")
        value = float(row[metric])
        if len(series) >= baseline_window:
            window = series[-baseline_window:]
            baseline = max(statistics.mean(window), min_baseline_value)
            stdev = statistics.pstdev(window) or 1e-6
            z = (value - baseline) / stdev
            rel_pct = ((value - baseline) / baseline) * 100.0
            sev = _classify(z, rel_pct)
            if sev:
                anomalies.append(
                    Anomaly(
                        timestamp=row["timestamp"],
                        metric=metric,
                        value=value,
                        baseline=baseline,
                        z_score=z,
                        relative_change_pct=rel_pct,
                        severity=sev,
                        citation=f"metrics.csv:L{row['csv_row']}",
                    )
                )
        series.append(value)

    return [a.to_dict() for a in anomalies]
