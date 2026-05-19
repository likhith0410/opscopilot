"""Shared LangGraph state schema for the incident-response pipeline.

Each node reads from the dict-like state and returns a partial dict that is
merged in. The TypedDict here is the single source of truth for what fields
flow between agents.
"""

from __future__ import annotations

from typing import Any, TypedDict


class IncidentState(TypedDict, total=False):
    # --- Ingest ---
    data_dir: str
    inputs: dict[str, Any]            # output of load_all_inputs
    evidence_index: Any               # tools.evidence_indexer.EvidenceIndex

    # --- Triage ---
    impacted_services: list[str]
    severity: str                     # "SEV-1" .. "SEV-4"
    start_time: str                   # ISO-8601 incident start
    end_time: str                     # ISO-8601 incident end (if known)
    triage_rationale: str
    escalation_chains: dict[str, dict[str, str]]
    stripped_injections: list[str]    # what the safety layer removed

    # --- Forensics ---
    anomalies: list[dict]
    timeline: list[dict]              # sorted events with citations
    key_evidence: list[dict]          # curated subset of timeline
    forensics_notes: str

    # --- Hypothesis ---
    hypotheses: list[dict]            # [{id, statement, citations, score, verdict?}]
    top_hypothesis: dict              # the highest-ranked one

    # --- Verifier ---
    verifier_report: dict             # {accepted, rejected, evidence_coverage, hallucination_rate}
    safe_to_report: bool

    # --- Final outputs ---
    report_md: str
    action_items: list[dict]

    # --- Bookkeeping ---
    tool_calls: list[dict]            # audit log of every tool invocation
    errors: list[str]
    llm_enabled: bool                 # whether LLM was used this run
