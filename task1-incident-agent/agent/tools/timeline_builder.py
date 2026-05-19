"""Tool 8 — Timeline Builder.

Merges events from alerts, logs (filtered), chat (notable lines), and metric
anomalies into a single, sorted timeline. Every entry carries a citation
suitable for grounding.
"""

from __future__ import annotations

import re
from typing import Iterable

_CHAT_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+(@\S+):\s*(.+)$")
# notable chat triggers (case-insensitive) — kept narrow to avoid noise
_NOTABLE_CHAT = re.compile(
    r"\b("
    r"deploy(?:ed|ing)?|rollback|rolling back|incident|sev[-\s]?[1234]|"
    r"declaring|ack(?:nowledged)?|crit|oom|"
    r"recovered?|cleared?|monitoring|confirm(?:ed|ing)?|"
    r"redis|payment|checkout|auth|hypothesis|root cause"
    r")\b",
    re.IGNORECASE,
)
# notable log levels (we surface WARN/ERROR and key INFO transitions)
_NOTABLE_LOG = re.compile(r"\b(ERROR|WARN)\b")
_INFO_TRANSITION = re.compile(
    r"\b(starting|listening|rollback_initiated|shutdown_initiated|recovered|normalized|cache_hit_ratio)\b",
    re.IGNORECASE,
)


def _from_alerts(alerts: list[dict]) -> list[dict]:
    out = []
    for a in alerts:
        out.append(
            {
                "timestamp": a["timestamp"],
                "source": "alert",
                "service": a.get("service", "unknown"),
                "severity": a.get("severity", ""),
                "text": f"[{a.get('severity','').upper()}] {a.get('title', '')}",
                "citation": f"alerts.json:#{a['alert_id']}",
            }
        )
    return out


def _from_logs(logs: dict[str, str]) -> list[dict]:
    out = []
    for service, content in logs.items():
        for i, line in enumerate(content.splitlines(), start=1):
            if not line:
                continue
            ts_m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+(\w+)\s+", line)
            if not ts_m:
                continue
            ts, level = ts_m.group(1), ts_m.group(2)
            if not (_NOTABLE_LOG.search(line) or _INFO_TRANSITION.search(line)):
                continue
            out.append(
                {
                    "timestamp": ts,
                    "source": "log",
                    "service": service,
                    "severity": level,
                    "text": line.strip(),
                    "citation": f"logs/{service}.log:L{i}",
                }
            )
    return out


def _from_chat(chat_raw: str) -> list[dict]:
    out = []
    for i, line in enumerate(chat_raw.splitlines(), start=1):
        m = _CHAT_TS_RE.match(line)
        if not m:
            continue
        ts, user, body = m.group(1), m.group(2), m.group(3)
        if _NOTABLE_CHAT.search(body):
            out.append(
                {
                    "timestamp": ts,
                    "source": "chat",
                    "service": "humans",
                    "severity": "",
                    "text": f"{user}: {body}",
                    "citation": f"chat.txt:L{i}",
                }
            )
    return out


def _from_anomalies(anomalies: list[dict]) -> list[dict]:
    out = []
    for a in anomalies:
        out.append(
            {
                "timestamp": a["timestamp"],
                "source": "metric",
                "service": a["metric"].split("_", 1)[0],
                "severity": a["severity"],
                "text": (
                    f"{a['metric']} anomaly: {a['value']} (baseline {a['baseline']}, "
                    f"z={a['z_score']}, rel={a['relative_change_pct']}%)"
                ),
                "citation": a["citation"],
            }
        )
    return out


def build_timeline(
    *,
    alerts: list[dict] | None = None,
    logs: dict[str, str] | None = None,
    chat_raw: str | None = None,
    anomalies: list[dict] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    sources: Iterable[str] | None = None,
) -> list[dict]:
    """Merge events into a single sorted timeline.

    Args:
        sources: subset of {"alert","log","chat","metric"} to include; default = all.
    """
    enabled = set(sources) if sources else {"alert", "log", "chat", "metric"}
    events: list[dict] = []
    if alerts and "alert" in enabled:
        events.extend(_from_alerts(alerts))
    if logs and "log" in enabled:
        events.extend(_from_logs(logs))
    if chat_raw and "chat" in enabled:
        events.extend(_from_chat(chat_raw))
    if anomalies and "metric" in enabled:
        events.extend(_from_anomalies(anomalies))

    if start_time:
        events = [e for e in events if e["timestamp"] >= start_time]
    if end_time:
        events = [e for e in events if e["timestamp"] <= end_time]

    events.sort(key=lambda e: (e["timestamp"], e["source"]))
    return events
