"""Forensics Agent.

Investigates the incident window using deterministic tool calls (anomaly
detection, log search, timeline merge) and then asks the LLM to summarize
what was found, *grounded in evidence the agent already gathered*. The LLM
is never asked to invent facts — only to narrate the curated evidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent.llm import call_llm, llm_enabled
from agent.state import IncidentState
from agent.tools import (
    build_timeline,
    detect_anomalies,
    log_search,
    parse_metrics,
    query_metrics,
)

# columns we run anomaly detection on (per service)
METRIC_FOR_SERVICE = {
    "payments": ["payments_latency_p99_ms", "payments_error_rate_pct"],
    "checkout": ["checkout_latency_p99_ms", "checkout_error_rate_pct"],
    "auth": ["auth_latency_p99_ms"],
    "redis-cache": ["redis_memory_pct"],
    "db-orders": ["db_active_connections"],
}


def _expand_window(start_iso: str, before_min: int = 30, after_min: int = 60) -> tuple[str, str]:
    if not start_iso:
        return ("", "")
    t = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    return (
        (t - timedelta(minutes=before_min)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        (t + timedelta(minutes=after_min)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _select_key_events(timeline: list[dict], anomalies: list[dict], limit: int = 20) -> list[dict]:
    """Hand-pick the most salient events: first alert per severity, first ERROR per service,
    deploys, rollbacks, recoveries, and top anomalies."""
    key: list[dict] = []
    seen = set()

    def add(ev: dict):
        sig = (ev["timestamp"], ev["source"], ev["text"][:50])
        if sig in seen:
            return
        seen.add(sig)
        key.append(ev)

    # first ERROR per service
    first_err_per_svc: dict[str, dict] = {}
    for ev in timeline:
        if ev["source"] == "log" and ev["severity"] == "ERROR":
            if ev["service"] not in first_err_per_svc:
                first_err_per_svc[ev["service"]] = ev
    for ev in first_err_per_svc.values():
        add(ev)

    # all WARN/CRIT alerts (these carry top citation value for evidence anchors)
    for ev in timeline:
        if ev["source"] == "alert" and ev["severity"] in {"warning", "critical"}:
            add(ev)

    # deploys / rollbacks
    for ev in timeline:
        t = ev["text"].lower()
        if "rollback_initiated" in t or "deploy_id=" in t or "rolling back" in t:
            add(ev)

    # human-marked hypothesis / declaration
    for ev in timeline:
        if ev["source"] == "chat" and ("declaring" in ev["text"].lower() or "hypothesis" in ev["text"].lower()):
            add(ev)

    # recovery markers
    for ev in timeline:
        if "recover" in ev["text"].lower() or "normalized" in ev["text"].lower() or "clearing incident" in ev["text"].lower():
            add(ev)

    # top critical anomalies
    crits = [a for a in anomalies if a["severity"] == "critical"][:3]
    for a in crits:
        add({
            "timestamp": a["timestamp"],
            "source": "metric",
            "service": a["metric"].split("_", 1)[0],
            "severity": a["severity"],
            "text": f"{a['metric']} = {a['value']} (baseline {a['baseline']}, +{a['relative_change_pct']:.0f}%)",
            "citation": a["citation"],
        })

    key.sort(key=lambda e: e["timestamp"])
    return key[:limit]


def forensics_agent(state: IncidentState) -> dict:
    inputs = state["inputs"]
    impacted = state.get("impacted_services", [])
    start_time = state.get("start_time", "")
    # Look back 60 minutes to capture any deploy / config push that may have
    # initiated the incident; forward 60 minutes to cover recovery.
    window_start, window_end = _expand_window(start_time, before_min=60, after_min=60)

    # 1) anomaly detection on each impacted service's metrics
    df = parse_metrics(inputs.get("metrics_raw", ""))
    all_anomalies: list[dict] = []
    if not df.empty:
        rows = query_metrics(df, start_time=window_start or None, end_time=window_end or None)
        for service in impacted:
            for col in METRIC_FOR_SERVICE.get(service, []):
                if col in (rows[0] if rows else {}):
                    all_anomalies.extend(detect_anomalies(rows, col, baseline_window=10))
        # also analyse redis + db globally — they're the most-common upstream causes
        for col in ("redis_memory_pct", "db_active_connections"):
            if rows and col in rows[0]:
                all_anomalies.extend(detect_anomalies(rows, col, baseline_window=10))
    # de-dup by (ts, metric)
    seen = set()
    dedup_anomalies = []
    for a in all_anomalies:
        sig = (a["timestamp"], a["metric"])
        if sig not in seen:
            seen.add(sig)
            dedup_anomalies.append(a)

    # 2) log search for high-signal patterns during the window
    error_hits = log_search(
        inputs.get("logs", {}),
        r"\bERROR\b",
        start_time=window_start or None,
        end_time=window_end or None,
        max_hits=80,
    )

    # 3) build the full timeline
    timeline = build_timeline(
        alerts=inputs.get("alerts", []),
        logs=inputs.get("logs", {}),
        chat_raw=inputs.get("chat_raw", ""),
        anomalies=dedup_anomalies,
        start_time=window_start or None,
        end_time=window_end or None,
    )

    # 4) pick the most salient events
    key_evidence = _select_key_events(timeline, dedup_anomalies)

    # 5) LLM-narrated summary (or template fallback). The fallback must include
    # at least one citation so it doesn't drag down evidence_coverage in the
    # verifier — pull citations from the strongest pieces of key evidence.
    sample_cites = [e["citation"] for e in key_evidence[:3]] or [
        a["citation"] for a in dedup_anomalies[:2] if a.get("severity") in {"major", "critical"}
    ]
    cite_str = ", ".join(sample_cites)
    summary_fallback = (
        f"Investigation window {window_start} -> {window_end}. "
        f"Impacted services: {', '.join(impacted) or 'none identified'}. "
        f"Anomalies detected: {len(dedup_anomalies)}; ERROR log lines: {len(error_hits)}; "
        f"key timeline events: {len(key_evidence)}. "
        f"Evidence: {cite_str}."
    )
    if llm_enabled():
        ev_lines = "\n".join(
            f"- {e['timestamp']} [{e['source']}/{e['service']}] {e['text'][:140]}  ({e['citation']})"
            for e in key_evidence
        )
        system = (
            "You are a forensics analyst. Summarize the supplied evidence in 4-6 sentences. "
            "Do not invent facts. Only refer to events present in the evidence list. "
            "After each factual claim, cite the matching item using its citation in square brackets."
        )
        user = f"Incident window: {window_start} -> {window_end}\n\nKey evidence:\n{ev_lines}"
        forensics_notes = call_llm(system, user, fallback=summary_fallback)
    else:
        forensics_notes = summary_fallback

    tool_calls = list(state.get("tool_calls", []))
    tool_calls.extend([
        {"agent": "Forensics", "tool": "parse_metrics", "ok": True},
        {"agent": "Forensics", "tool": "detect_anomalies", "ok": True, "count": len(dedup_anomalies)},
        {"agent": "Forensics", "tool": "log_search", "ok": True, "count": len(error_hits)},
        {"agent": "Forensics", "tool": "build_timeline", "ok": True, "count": len(timeline)},
    ])

    return {
        "anomalies": dedup_anomalies,
        "timeline": timeline,
        "key_evidence": key_evidence,
        "forensics_notes": forensics_notes,
        "tool_calls": tool_calls,
        "llm_enabled": llm_enabled(),
    }
