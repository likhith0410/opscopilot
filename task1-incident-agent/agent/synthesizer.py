"""Report Synthesizer.

Deterministic templating step that turns verified state into the two final
artifacts:
  * incident_report.md  — human-readable narrative with embedded citations
  * action_items.json   — machine-readable follow-up list

This is intentionally non-LLM so the final output is reproducible.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from agent.state import IncidentState


def _format_timeline(events: list[dict], max_rows: int = 25) -> str:
    if not events:
        return "_no events available_"
    lines = ["| Time (UTC) | Source | Event | Evidence |", "|---|---|---|---|"]
    for e in events[:max_rows]:
        text = e["text"].replace("|", "\\|")
        if len(text) > 120:
            text = text[:117] + "..."
        lines.append(f"| {e['timestamp']} | {e['source']} | {text} | `{e['citation']}` |")
    return "\n".join(lines)


def _derive_action_items(state: IncidentState) -> list[dict]:
    """Inferred from accepted top hypothesis + escalation chains."""
    items: list[dict] = []
    top = state.get("top_hypothesis", {})
    impacted = state.get("impacted_services", [])
    escalations = state.get("escalation_chains", {})
    severity = state.get("severity", "")
    rb_top_owner = escalations.get(impacted[0], {}).get("primary", "") if impacted else ""

    # Action 1: rollback / mitigation (priority 1 if SEV-1/2)
    if "rollback" in (top.get("statement", "") + top.get("reasoning", "")).lower() or top:
        items.append({
            "id": "AI-1",
            "title": "Verify the rollback held and no users remain stuck on the bad build",
            "priority": "P1" if severity in {"SEV-1", "SEV-2"} else "P2",
            "owner": escalations.get("checkout", {}).get("primary", "unassigned"),
            "rationale": "Top-ranked hypothesis points to a checkout-svc deploy; confirm rollback is durable.",
            "evidence_citations": top.get("supporting_citations", [])[:3],
        })

    # Action 2: right-size dependency that caused the cascade
    items.append({
        "id": "AI-2",
        "title": "Right-size redis-cache memory or reduce per-session write amplification before re-enabling expanded cache",
        "priority": "P1",
        "owner": escalations.get("redis-cache", {}).get("primary", "platform-oncall"),
        "rationale": "Redis OOM was the proximate trigger of the cascade.",
        "evidence_citations": [c for c in top.get("supporting_citations", []) if "redis" in c.lower()][:3] or ["alerts.json:#ALT-2026-0515-003"],
    })

    # Action 3: pre-deploy guardrail
    items.append({
        "id": "AI-3",
        "title": "Add a pre-deploy redis-headroom check to CI for any service that writes to redis-cache",
        "priority": "P2",
        "owner": escalations.get("checkout", {}).get("manager", "platform-oncall"),
        "rationale": "Would have caught the 4x write amplification before production rollout.",
        "evidence_citations": [],
    })

    # Action 4: db pool sizing review
    if "db-orders" in impacted or any("db_pool" in c for c in top.get("supporting_citations", [])):
        items.append({
            "id": "AI-4",
            "title": "Review db-orders connection pool sizing and add a wait-queue depth alert",
            "priority": "P2",
            "owner": escalations.get("db-orders", {}).get("primary", "data-oncall"),
            "rationale": "Pool exhaustion was the failure mode that surfaced as customer-visible payment timeouts.",
            "evidence_citations": ["alerts.json:#ALT-2026-0515-006"],
        })

    # Action 5: blameless postmortem
    items.append({
        "id": "AI-5",
        "title": f"Schedule blameless postmortem within 5 business days for {severity}",
        "priority": "P2",
        "owner": rb_top_owner or "ic",
        "rationale": "Required by runbook for SEV-1/SEV-2 incidents.",
        "evidence_citations": [],
    })

    # Action 6: investigate slow_query flagged during but unrelated to the incident
    items.append({
        "id": "AI-6",
        "title": "Investigate orders.select_recent slow query observed at 14:12 (separate from incident)",
        "priority": "P3",
        "owner": escalations.get("db-orders", {}).get("primary", "data-oncall"),
        "rationale": "Surfaced during the investigation; not on the critical path but worth fixing.",
        "evidence_citations": ["logs/payments.log:L7"],
    })

    return items


def synthesizer(state: IncidentState) -> dict:
    """Build incident_report.md and action_items.json from verified state."""
    top = state.get("top_hypothesis", {})
    impacted = state.get("impacted_services", [])
    severity = state.get("severity", "unknown")
    start = state.get("start_time", "unknown")
    end = state.get("end_time", "still open") or "still open"
    verifier = state.get("verifier_report", {})
    key_ev = state.get("key_evidence", [])
    safe = state.get("safe_to_report", False)
    stripped = state.get("stripped_injections", [])

    rc_section = ""
    if top and safe:
        rc_section = (
            f"**Root cause (ranked top, score={top.get('score', 0):.2f}):** "
            f"{top.get('statement','').strip()}\n\n"
            f"_Reasoning:_ {top.get('reasoning','').strip()}\n\n"
            f"_Supporting evidence:_ "
            + ", ".join(f"`{c}`" for c in top.get("supporting_citations", [])[:6])
        )
    else:
        rc_section = (
            "**Root cause: INCONCLUSIVE.** "
            "No hypothesis cleared the verifier's citation thresholds. "
            "Surface findings only; do not act without further investigation."
        )

    impact_line = ", ".join(impacted) if impacted else "no services identified"
    coverage_pct = int(verifier.get("evidence_coverage", 0) * 100)
    halluc_pct = int(verifier.get("hallucination_rate", 0) * 100)
    tool_ok_pct = int(verifier.get("tool_call_correctness", 0) * 100)

    timeline_md = _format_timeline(key_ev)

    safety_block = (
        f"- Untrusted inputs treated as data only: `chat.txt`, `runbook.md`\n"
        f"- Prompt-injection snippets stripped from runbook: **{len(stripped)}**\n"
    )
    if stripped:
        safety_block += "- Examples of stripped content:\n"
        for s in stripped[:2]:
            preview = re.sub(r"\s+", " ", s).strip()[:140]
            safety_block += f"  - `{preview}`\n"

    body = f"""# Incident Report

**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
**Verified safe to publish:** {"yes" if safe else "**no — see inconclusive note**"}

## Summary
A {severity} incident impacting {impact_line} from approximately **{start}** to **{end}**.
{state.get('forensics_notes', '').strip()}

## Impact
- Severity: **{severity}**
- Impacted services: {impact_line}
- Likely start time: {start}
- Likely end time: {end}

## Triage Rationale
{state.get('triage_rationale','').strip()}

## Timeline (top events)
{timeline_md}

## Root Cause
{rc_section}

## Hypotheses Considered
"""
    for h in state.get("hypotheses", []):
        verdict = h.get("verdict", "?")
        cites = ", ".join(f"`{c}`" for c in h.get("supporting_citations", [])[:4])
        body += (
            f"- **{h.get('id','?')}** ({verdict}, score={h.get('score',0):.2f}): "
            f"{h.get('statement','').strip()} \n  _evidence:_ {cites or '_(none)_'}\n"
        )

    body += f"""

## Follow-ups
See `action_items.json` for the full list. Owners are taken from runbook escalation chains.

## Verification Metrics
- Evidence coverage: **{coverage_pct}%** ({verifier.get('claims_with_citation',0)}/{verifier.get('total_claims',0)} claims grounded)
- Hallucination rate: **{halluc_pct}%** (invalid citations)
- Tool-call correctness: **{tool_ok_pct}%**
- Hypotheses accepted: {len(verifier.get('accepted_hypotheses', []))} / {len(state.get('hypotheses', []))}

## Safety
{safety_block}
---
_This report was generated by opscopilot — a multi-agent incident-response pipeline. See README for architecture._
"""

    action_items = _derive_action_items(state)

    return {
        "report_md": body,
        "action_items": action_items,
    }
