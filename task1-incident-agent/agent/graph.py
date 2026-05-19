"""LangGraph state machine.

Wires together the four agents + synthesizer into the assignment-required
flow:

  Ingest -> Index Evidence -> Triage -> Investigate (Forensics) ->
  Hypothesize -> Verify -> Report

Each node is a pure function returning a partial state update; LangGraph merges
those into the running IncidentState.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.agents import (
    forensics_agent,
    hypothesis_agent,
    triage_agent,
    verifier_agent,
)
from agent.state import IncidentState
from agent.synthesizer import synthesizer
from agent.tools import build_index, load_all_inputs


def ingest_node(state: IncidentState) -> dict:
    inputs = load_all_inputs(state["data_dir"])
    return {
        "inputs": inputs,
        "tool_calls": [{"agent": "Ingest", "tool": "load_all_inputs", "ok": True}],
    }


def index_evidence_node(state: IncidentState) -> dict:
    idx = build_index(state["inputs"])
    calls = list(state.get("tool_calls", []))
    calls.append({"agent": "IndexEvidence", "tool": "build_index", "ok": True})
    return {"evidence_index": idx, "tool_calls": calls}


def build_graph():
    g = StateGraph(IncidentState)

    g.add_node("ingest", ingest_node)
    g.add_node("index_evidence", index_evidence_node)
    g.add_node("triage", triage_agent)
    g.add_node("forensics", forensics_agent)
    g.add_node("hypothesis", hypothesis_agent)
    g.add_node("verifier", verifier_agent)
    g.add_node("synthesizer", synthesizer)

    g.set_entry_point("ingest")
    g.add_edge("ingest", "index_evidence")
    g.add_edge("index_evidence", "triage")
    g.add_edge("triage", "forensics")
    g.add_edge("forensics", "hypothesis")
    g.add_edge("hypothesis", "verifier")
    g.add_edge("verifier", "synthesizer")
    g.add_edge("synthesizer", END)

    return g.compile()
