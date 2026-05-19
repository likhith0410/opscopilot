"""Tool 2 — Log Search.

Regex/keyword search across one or more log files, with optional time-range
filtering. Returns matches with `path:lineStart-lineEnd` citations ready for
the evidence indexer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

# matches: 2026-05-15T14:30:12Z at the start of a log line
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")


@dataclass(frozen=True)
class LogHit:
    service: str
    line_number: int
    timestamp: str | None
    text: str
    citation: str  # e.g. "logs/payments.log:L34"


def _parse_ts(line: str) -> str | None:
    m = _TS_RE.match(line)
    return m.group(1) if m else None


def _in_range(ts: str | None, start: str | None, end: str | None) -> bool:
    if ts is None:
        return start is None and end is None
    if start and ts < start:
        return False
    if end and ts > end:
        return False
    return True


def log_search(
    logs: dict[str, str],
    pattern: str,
    *,
    regex: bool = True,
    case_sensitive: bool = False,
    services: Iterable[str] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    max_hits: int = 200,
    citation_path_prefix: str = "logs",
) -> list[dict]:
    """Search log files for `pattern`.

    Args:
        logs: mapping of service name -> full log text (as returned by load_all_inputs)
        pattern: regex (if regex=True) or literal substring
        services: restrict to these services; default = all
        start_time, end_time: ISO-8601 UTC bounds (e.g. "2026-05-15T14:30:00Z"); inclusive
        max_hits: cap on results

    Returns a list of dicts with keys: service, line_number, timestamp, text, citation.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        prog = re.compile(pattern, flags)
        match_fn = lambda line: prog.search(line) is not None
    else:
        needle = pattern if case_sensitive else pattern.lower()
        match_fn = lambda line: (needle in (line if case_sensitive else line.lower()))

    services_filter = set(services) if services else None
    hits: list[dict] = []

    for service, content in logs.items():
        if services_filter and service not in services_filter:
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            ts = _parse_ts(line)
            if not _in_range(ts, start_time, end_time):
                continue
            if match_fn(line):
                hits.append(
                    {
                        "service": service,
                        "line_number": i,
                        "timestamp": ts,
                        "text": line.rstrip(),
                        "citation": f"{citation_path_prefix}/{service}.log:L{i}",
                    }
                )
                if len(hits) >= max_hits:
                    return hits
    return hits
