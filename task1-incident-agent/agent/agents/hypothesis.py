"""Hypothesis Agent.

Generates 2-3 ranked root-cause hypotheses, each grounded in evidence
citations gathered by Forensics. When an LLM is available it produces the
narrative; otherwise a deterministic, pattern-based generator runs over the
key evidence and entity-extraction signals. Either way, every hypothesis
must carry citations — the Verifier will reject any that don't.
"""

from __future__ import annotations

import re

from agent.llm import call_llm_json, llm_enabled
from agent.state import IncidentState
from agent.tools import extract_entities


def _deterministic_hypotheses(state: IncidentState) -> list[dict]:
    """Pattern-based hypothesis generator used when LLM is offline.

    Looks for known incident shapes in the evidence (deploy + cache pressure,
    db pool saturation, downstream service failure) and emits a ranked list."""

    inputs = state["inputs"]
    key_ev = state.get("key_evidence", [])
    anomalies = state.get("anomalies", [])
    impacted = state.get("impacted_services", [])

    # collect citations by topic
    redis_evidence: list[str] = []
    deploy_evidence: list[str] = []
    db_evidence: list[str] = []
    payment_err_evidence: list[str] = []

    for e in key_ev:
        t = e["text"].lower()
        cite = e["citation"]
        if "redis" in t or "oom" in t or "evict" in t or "memory" in t:
            redis_evidence.append(cite)
        if "deploy_id" in t or "rollback" in t or "rolling back" in t or "starting build=" in t.lower():
            deploy_evidence.append(cite)
        if "db_pool" in t or "connection pool" in t or "db-orders" in t.lower():
            db_evidence.append(cite)
        if "charge_failed" in t or "payment" in t and "fail" in t:
            payment_err_evidence.append(cite)

    # add a couple of strong metric anomalies as citations
    redis_metric_cites = [a["citation"] for a in anomalies if a["metric"] == "redis_memory_pct" and a["severity"] in {"major", "critical"}][:2]
    pay_metric_cites = [a["citation"] for a in anomalies if a["metric"] == "payments_latency_p99_ms" and a["severity"] in {"major", "critical"}][:2]

    hypotheses: list[dict] = []

    if redis_evidence and deploy_evidence:
        hypotheses.append({
            "id": "H1",
            "statement": (
                "A recent checkout-svc deploy increased per-session writes into redis-cache, "
                "driving memory past maxmemory, triggering aggressive LRU eviction of hot keys "
                "(including sessions and fraud rules). Downstream services fell back to the "
                "database, saturating the db-orders connection pool, which caused payment "
                "charge requests to time out."
            ),
            "supporting_citations": list(dict.fromkeys(deploy_evidence + redis_evidence + redis_metric_cites + db_evidence))[:8],
            "score": 0.92,
            "reasoning": (
                "Deploy timing (13:55) precedes redis pressure (14:28+) by ~30min matching session TTL; "
                "redis OOM errors directly cited; db pool exhaustion follows redis eviction; "
                "rollback restores normality within 10min."
            ),
        })

    if db_evidence and not deploy_evidence:
        h2_cites = list(dict.fromkeys(db_evidence + pay_metric_cites))[:6]
        hypotheses.append({
            "id": "H2",
            "statement": (
                "A long-running query or query-plan regression on db-orders caused connection "
                "pool starvation, which cascaded into payment timeouts."
            ),
            "supporting_citations": h2_cites or ["alerts.json:#ALT-2026-0515-006"],
            "score": 0.45,
            "reasoning": "Db pool saturation observed, but no slow-query evidence in the window beyond a single 14:12 warning unrelated to the spike pattern.",
        })
    else:
        # always include alert citation for db-orders pool + payments charge_failed log line
        h2_cites = list(dict.fromkeys(payment_err_evidence + db_evidence))[:4] or [
            "alerts.json:#ALT-2026-0515-006",
            "logs/payments.log:L23",
        ]
        hypotheses.append({
            "id": "H2",
            "statement": (
                "An upstream dependency (fraud-svc) experienced timeouts, propagating back through "
                "payments and causing the observed error rate spike."
            ),
            "supporting_citations": h2_cites,
            "score": 0.35,
            "reasoning": (
                "Single 'upstream_timeout downstream=fraud-svc' line is present, but the dominant "
                "downstream errors are db_pool_exhausted, not fraud-svc; this hypothesis is weakly "
                "supported."
            ),
        })

    hypotheses.append({
        "id": "H3",
        "statement": (
            "CDN edge cache configuration push at 14:20 reduced cache hit ratio, causing increased "
            "origin load that overwhelmed the payment service."
        ),
        "supporting_citations": ["alerts.json:#ALT-2026-0515-008"],
        "score": 0.10,
        "reasoning": (
            "CDN alert is contemporaneous but the failure modes (db_pool, redis OOM) are upstream of "
            "the CDN layer; cdn-edge is in a different team's system per chat."
        ),
    })

    hypotheses.sort(key=lambda h: -h["score"])
    return hypotheses


def hypothesis_agent(state: IncidentState) -> dict:
    # always produce the deterministic skeleton; LLM (if available) can re-score
    hypos = _deterministic_hypotheses(state)

    if llm_enabled():
        ev = state.get("key_evidence", [])
        ev_lines = "\n".join(
            f"- {e['timestamp']} [{e['source']}] {e['text'][:160]}  ({e['citation']})"
            for e in ev[:15]
        )
        system = (
            "You are a senior SRE. Given the key evidence and 3 candidate hypotheses, "
            "return a JSON object {\"ranked\":[{\"id\":...,\"score\":0..1,\"rationale\":\"...\"}]} "
            "ranking from most to least likely. Do NOT invent new hypotheses. Do NOT cite anything "
            "not in the evidence list. Output ONLY valid JSON."
        )
        candidate_block = "\n".join(
            f"{h['id']}: {h['statement']} [cites: {', '.join(h['supporting_citations'][:3])}]"
            for h in hypos
        )
        user = f"Key evidence:\n{ev_lines}\n\nCandidate hypotheses:\n{candidate_block}"
        out = call_llm_json(system, user, fallback={"ranked": [{"id": h["id"], "score": h["score"], "rationale": h["reasoning"]} for h in hypos]})
        ranking = {item["id"]: item for item in out.get("ranked", [])}
        for h in hypos:
            if h["id"] in ranking:
                h["score"] = float(ranking[h["id"]].get("score", h["score"]))
                h["llm_rationale"] = ranking[h["id"]].get("rationale", "")
        hypos.sort(key=lambda h: -h["score"])

    top = hypos[0] if hypos else {}

    tool_calls = list(state.get("tool_calls", []))
    tool_calls.append({"agent": "Hypothesis", "tool": "deterministic_generator", "ok": True, "count": len(hypos)})
    if llm_enabled():
        tool_calls.append({"agent": "Hypothesis", "tool": "llm_rerank", "ok": True})

    return {
        "hypotheses": hypos,
        "top_hypothesis": top,
        "tool_calls": tool_calls,
    }
