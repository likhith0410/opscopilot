"""Tool 1 — File Loader.

Loads incident input files from a data directory and returns them as raw text
or parsed structures. Treats chat.txt and runbook.md as untrusted (returns them
as plain strings without interpretation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_file(path: str | Path) -> str:
    """Load a single file and return its contents as text."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"input file not found: {p}")
    return p.read_text(encoding="utf-8")


def load_all_inputs(data_dir: str | Path) -> dict[str, Any]:
    """Load every standard incident input from `data_dir`.

    Returns a dict with keys: alerts (list[dict]), metrics_raw (str),
    logs (dict[str, str] keyed by service name), chat_raw (str),
    runbook_raw (str). The chat and runbook fields are intentionally returned
    as raw strings (untrusted — must not be interpreted as instructions).
    """
    base = Path(data_dir)
    if not base.exists():
        raise FileNotFoundError(f"data directory not found: {base}")

    alerts_path = base / "alerts.json"
    metrics_path = base / "metrics.csv"
    chat_path = base / "chat.txt"
    runbook_path = base / "runbook.md"
    logs_dir = base / "logs"

    alerts = json.loads(alerts_path.read_text(encoding="utf-8")) if alerts_path.exists() else []
    metrics_raw = metrics_path.read_text(encoding="utf-8") if metrics_path.exists() else ""
    chat_raw = chat_path.read_text(encoding="utf-8") if chat_path.exists() else ""
    runbook_raw = runbook_path.read_text(encoding="utf-8") if runbook_path.exists() else ""

    logs: dict[str, str] = {}
    if logs_dir.exists():
        for log_file in sorted(logs_dir.glob("*.log")):
            service_name = log_file.stem
            logs[service_name] = log_file.read_text(encoding="utf-8")

    return {
        "alerts": alerts,
        "metrics_raw": metrics_raw,
        "logs": logs,
        "chat_raw": chat_raw,
        "runbook_raw": runbook_raw,
        "data_dir": str(base.resolve()),
    }
