"""Verifier / Critic Agent.

Inspects every hypothesis (and other agent-produced claims) and rejects any
citation that doesn't resolve in the EvidenceIndex. Also computes:

  * evidence_coverage  = fraction of claims with >=1 valid citation
  * hallucination_rate = fraction of citations that fail to resolve
  * tool_call_correctness = fraction of upstream tool calls that succeeded

It is intentionally deterministic — no LLM is invoked here so the verification
is reproducible and auditable.
"""

from __future__ import annotations

from agent.state import IncidentState
from agent.tools.evidence_indexer import cite


def _verify_citations(text: str, index) -> tuple[list[str], list[str]]:
    """Return (valid_citations, invalid_citations) extracted from `text`."""
    if not text:
        return [], []
    tokens = cite(text)
    valid: list[str] = []
    invalid: list[str] = []
    for tok in tokens:
        if index.resolve(tok) is not None:
            valid.append(tok)
        else:
            invalid.append(tok)
    return valid, invalid


def verifier_agent(state: IncidentState) -> dict:
    idx = state["evidence_index"]
    hypotheses = state.get("hypotheses", [])
    forensics_notes = state.get("forensics_notes", "")

    accepted: list[dict] = []
    rejected: list[dict] = []

    total_citations = 0
    bad_citations = 0
    claims_with_cite = 0
    total_claims = 0

    # check each hypothesis
    for h in hypotheses:
        h_text = h.get("statement", "") + " " + " ".join(h.get("supporting_citations", []))
        valid, invalid = _verify_citations(h_text, idx)
        total_citations += len(valid) + len(invalid)
        bad_citations += len(invalid)
        total_claims += 1
        if valid:
            claims_with_cite += 1
        verdict = "accepted" if (valid and not invalid) else ("partial" if valid else "rejected")
        record = {
            **h,
            "verdict": verdict,
            "valid_citations": valid,
            "invalid_citations": invalid,
        }
        if verdict in {"accepted", "partial"}:
            accepted.append(record)
        else:
            rejected.append(record)

    # check forensics notes too (each line treated as a candidate claim)
    for line in [l.strip() for l in forensics_notes.splitlines() if l.strip()]:
        valid, invalid = _verify_citations(line, idx)
        total_citations += len(valid) + len(invalid)
        bad_citations += len(invalid)
        total_claims += 1
        if valid:
            claims_with_cite += 1

    evidence_coverage = (claims_with_cite / total_claims) if total_claims else 0.0
    hallucination_rate = (bad_citations / total_citations) if total_citations else 0.0

    # tool-call correctness from the audit log
    tool_calls = state.get("tool_calls", [])
    ok = sum(1 for t in tool_calls if t.get("ok"))
    tool_call_correctness = (ok / len(tool_calls)) if tool_calls else 1.0

    safe = (
        bool(accepted)
        and hallucination_rate <= 0.10
        and evidence_coverage >= 0.6
    )

    report = {
        "accepted_hypotheses": [a["id"] for a in accepted],
        "rejected_hypotheses": [r["id"] for r in rejected],
        "total_claims": total_claims,
        "claims_with_citation": claims_with_cite,
        "evidence_coverage": round(evidence_coverage, 3),
        "hallucination_rate": round(hallucination_rate, 3),
        "tool_call_correctness": round(tool_call_correctness, 3),
        "stripped_injections_count": len(state.get("stripped_injections", [])),
    }

    new_tool_calls = list(tool_calls)
    new_tool_calls.append({"agent": "Verifier", "tool": "verify_citations", "ok": True})

    return {
        "hypotheses": accepted + rejected,  # re-write so verdicts are persisted
        "verifier_report": report,
        "safe_to_report": safe,
        "tool_calls": new_tool_calls,
    }
