"""Tool 7 — Evidence Indexer.

Builds an in-memory index that maps citation strings (e.g.
`logs/payments.log:L34`, `chat.txt:L42-L45`, `metrics.csv:L31`) to the actual
text content at that location. Used by the Verifier to check that every claim
in the final report has a citation pointing to real evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CITATION_RE = re.compile(
    r"\b("
    r"(?:logs/)?[a-z0-9_\-]+\.log:L\d+(?:-L\d+)?"
    r"|chat\.txt:L\d+(?:-L\d+)?"
    r"|runbook\.md:L\d+(?:-L\d+)?"
    r"|metrics\.csv:L\d+(?:-L\d+)?"
    r"|metrics\.csv:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
    r"|alerts\.json:#[A-Z0-9\-]+"
    r")\b"
)


@dataclass
class EvidenceIndex:
    """Holds line-indexed contents of every input file plus alert lookup."""

    file_lines: dict[str, list[str]]  # citation prefix -> lines (1-indexed via list[idx-1])
    alerts_by_id: dict[str, dict]
    metrics_by_ts: dict[str, dict]
    metrics_by_row: dict[int, dict]

    def resolve(self, citation: str) -> str | None:
        """Resolve a citation string to its actual text, or None if invalid."""
        c = citation.strip()

        # alerts: alerts.json:#ALT-2026-0515-001
        if c.startswith("alerts.json:#"):
            alert_id = c.split("#", 1)[1]
            alert = self.alerts_by_id.get(alert_id)
            return f"{alert_id}: {alert['title']}" if alert else None

        # metrics by timestamp: metrics.csv:2026-05-15T14:30:00Z
        m_ts = re.match(r"metrics\.csv:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)", c)
        if m_ts:
            row = self.metrics_by_ts.get(m_ts.group(1))
            return f"row at {m_ts.group(1)}: {row}" if row else None

        # metrics by row: metrics.csv:L31
        m_row = re.match(r"metrics\.csv:L(\d+)$", c)
        if m_row:
            row = self.metrics_by_row.get(int(m_row.group(1)))
            return f"row {m_row.group(1)}: {row}" if row else None

        # text files: path:Lstart[-Lend]
        m_file = re.match(r"(.+?):L(\d+)(?:-L(\d+))?$", c)
        if m_file:
            path, start, end = m_file.group(1), int(m_file.group(2)), m_file.group(3)
            lines = self._lookup_file(path)
            if not lines:
                return None
            end_n = int(end) if end else start
            if start < 1 or end_n > len(lines) or start > end_n:
                return None
            return "\n".join(lines[start - 1 : end_n])

        return None

    def _lookup_file(self, path: str) -> list[str] | None:
        # support both "logs/payments.log" and "payments.log"
        for key in (path, path.split("/")[-1]):
            if key in self.file_lines:
                return self.file_lines[key]
        # try bare-name match for logs/*.log
        if path.endswith(".log") and not path.startswith("logs/"):
            return self.file_lines.get(f"logs/{path}")
        return None


def build_index(inputs: dict) -> EvidenceIndex:
    """Build an EvidenceIndex from a `load_all_inputs(...)` result."""
    file_lines: dict[str, list[str]] = {}

    if inputs.get("chat_raw"):
        file_lines["chat.txt"] = inputs["chat_raw"].splitlines()
    if inputs.get("runbook_raw"):
        file_lines["runbook.md"] = inputs["runbook_raw"].splitlines()
    for service, content in inputs.get("logs", {}).items():
        file_lines[f"logs/{service}.log"] = content.splitlines()
        file_lines[f"{service}.log"] = file_lines[f"logs/{service}.log"]

    alerts_by_id = {a["alert_id"]: a for a in inputs.get("alerts", [])}

    # metrics by ts + row
    metrics_by_ts: dict[str, dict] = {}
    metrics_by_row: dict[int, dict] = {}
    metrics_raw = inputs.get("metrics_raw", "")
    if metrics_raw.strip():
        lines = metrics_raw.splitlines()
        header = lines[0].split(",")
        for idx, line in enumerate(lines[1:], start=2):  # csv row 2 = first data row
            cells = line.split(",")
            row = dict(zip(header, cells))
            ts = row.get("timestamp")
            row["_csv_row"] = idx
            if ts:
                metrics_by_ts[ts] = row
            metrics_by_row[idx] = row

    return EvidenceIndex(
        file_lines=file_lines,
        alerts_by_id=alerts_by_id,
        metrics_by_ts=metrics_by_ts,
        metrics_by_row=metrics_by_row,
    )


def cite(text: str) -> list[str]:
    """Extract every citation token from a piece of text. Used by the Verifier."""
    return CITATION_RE.findall(text)
