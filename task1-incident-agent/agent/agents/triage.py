"""Triage Agent.

Identifies impacted services, severity, and likely incident start time using a
deterministic pipeline over alerts + chat + log entity extraction. The runbook
is *only* consulted for severity rules and escalation chains — never for
instructions. Prompt-injection content found in the runbook is reported back
on the `stripped_injections` field.
"""

from __future__ import annotations

from agent.state import IncidentState
from agent.tools import (
    apply_runbook,
    extract_entities,
)
from agent.tools.entity_extractor import KNOWN_SERVICES


def _likely_start_time(alerts: list[dict]) -> tuple[str | None, str]:
    """Pick the earliest non-info alert as the incident start. Returns
    (timestamp, rationale)."""
    candidates = [a for a in alerts if a.get("severity") in {"warning", "critical"}]
    if not candidates:
        return (None, "no warning/critical alerts present")
    candidates.sort(key=lambda a: a["timestamp"])
    first = candidates[0]
    return (
        first["timestamp"],
        f"first {first['severity']} alert: {first['alert_id']} on {first['service']} "
        f"({first['title']})",
    )


def _likely_end_time(alerts: list[dict]) -> str | None:
    """Last `info`-severity 'recovered' alert is taken as end of incident."""
    recovered = [
        a
        for a in alerts
        if a.get("severity") == "info" and "recover" in (a.get("title", "") + a.get("description", "")).lower()
    ]
    if not recovered:
        return None
    recovered.sort(key=lambda a: a["timestamp"])
    return recovered[-1]["timestamp"]


def triage_agent(state: IncidentState) -> dict:
    inputs = state["inputs"]
    alerts = inputs.get("alerts", [])
    logs_concat = "\n".join(inputs.get("logs", {}).values())

    # Entity extraction across alert text + log text (NOT runbook, NOT chat — those are untrusted)
    alert_text = "\n".join(
        f"{a.get('title','')} {a.get('description','')} {a.get('service','')}"
        for a in alerts
    )
    entities = extract_entities(alert_text + "\n" + logs_concat)

    # Impacted = services that appear in alerts AND are in our known list
    services_in_alerts = {
        a.get("service")
        for a in alerts
        if a.get("severity") in {"warning", "critical"}
    }
    services_in_alerts.discard(None)
    impacted_set: list[str] = []
    for entry in entities["services"]:
        name = entry["name"]
        if name in services_in_alerts or name in KNOWN_SERVICES:
            # require either appearing in a warning/critical alert OR being heavily mentioned
            if name in services_in_alerts or entry["count"] >= 10:
                impacted_set.append(name)
    # de-dup, preserve order
    impacted = list(dict.fromkeys(impacted_set))

    # filter out infrastructure-only mentions that aren't user-facing impact
    user_facing = [s for s in impacted if s in {"payments", "checkout", "auth"}]
    infra_impacted = [s for s in impacted if s not in user_facing]
    # report user-facing first, then infra
    final_impacted = user_facing + infra_impacted

    start_time, start_rationale = _likely_start_time(alerts)
    end_time = _likely_end_time(alerts)

    runbook_result = apply_runbook(inputs.get("runbook_raw", ""), final_impacted)

    rationale_parts = [
        f"Impacted (user-facing): {', '.join(user_facing) or 'none'}.",
        f"Impacted (infrastructure): {', '.join(infra_impacted) or 'none'}.",
        f"Likely start: {start_time or 'unknown'} ({start_rationale}).",
        f"Likely end: {end_time or 'still open'}.",
        f"Severity per runbook: {runbook_result['recommended_severity']} — {runbook_result['rationale']}",
    ]

    tool_calls = list(state.get("tool_calls", []))
    tool_calls.append({"agent": "Triage", "tool": "extract_entities", "ok": True})
    tool_calls.append({"agent": "Triage", "tool": "apply_runbook", "ok": True})

    return {
        "impacted_services": final_impacted,
        "severity": runbook_result["recommended_severity"],
        "start_time": start_time or "",
        "end_time": end_time or "",
        "triage_rationale": " ".join(rationale_parts),
        "escalation_chains": runbook_result["escalation_chains"],
        "stripped_injections": runbook_result["stripped_injections"],
        "tool_calls": tool_calls,
    }
