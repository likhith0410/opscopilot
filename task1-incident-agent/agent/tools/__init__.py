"""Agent tools — callable modules used by the multi-agent orchestrator.

All tools are pure Python functions. They are exposed both as direct imports
(used by deterministic agents) and as LangChain `@tool`-decorated callables
(used by LLM-driven agents). See README.md for the tool catalog.
"""

from agent.tools.file_loader import load_file, load_all_inputs
from agent.tools.log_search import log_search
from agent.tools.metrics_parser import parse_metrics, query_metrics
from agent.tools.anomaly_detector import detect_anomalies
from agent.tools.entity_extractor import extract_entities
from agent.tools.runbook_applier import apply_runbook
from agent.tools.evidence_indexer import build_index, cite
from agent.tools.timeline_builder import build_timeline

__all__ = [
    "load_file",
    "load_all_inputs",
    "log_search",
    "parse_metrics",
    "query_metrics",
    "detect_anomalies",
    "extract_entities",
    "apply_runbook",
    "build_index",
    "cite",
    "build_timeline",
]
