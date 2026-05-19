"""The four agents that make up the incident-response pipeline.

Each agent is a pure function `(state: IncidentState) -> dict` returning the
partial state update. The Verifier is a critic that can reject unsupported
claims from upstream agents.
"""
from agent.agents.triage import triage_agent
from agent.agents.forensics import forensics_agent
from agent.agents.hypothesis import hypothesis_agent
from agent.agents.verifier import verifier_agent

__all__ = ["triage_agent", "forensics_agent", "hypothesis_agent", "verifier_agent"]
