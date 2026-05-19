"""Tool 6 — Runbook Applier.

Parses the runbook to extract structured severity rules + escalation chains,
**stripping prompt-injection attempts** (any HTML comment, "SYSTEM:",
"ASSISTANT_OVERRIDE:", "Ignore" instructions, etc.) before parsing.

Returns the recommended severity for a given impact pattern and the
on-call escalation chain for a service.
"""

from __future__ import annotations

import re

# patterns we treat as prompt-injection vectors and strip from the runbook
INJECTION_PATTERNS = [
    re.compile(r"<!--.*?-->", re.DOTALL | re.IGNORECASE),  # HTML comments
    re.compile(r"^\s*(?:SYSTEM|ASSISTANT|ASSISTANT_OVERRIDE|USER)\s*:.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*ignore (?:all|the|previous|above).*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*disregard.*(?:rules|policy|instructions).*$", re.MULTILINE | re.IGNORECASE),
]


def sanitize_runbook(raw: str) -> tuple[str, list[str]]:
    """Strip prompt-injection content. Returns (cleaned_text, list_of_stripped_snippets)."""
    stripped: list[str] = []
    cleaned = raw
    for pat in INJECTION_PATTERNS:
        for m in pat.finditer(cleaned):
            snippet = m.group(0).strip()
            if snippet:
                stripped.append(snippet[:200])
        cleaned = pat.sub("", cleaned)
    return cleaned, stripped


# regex helpers for table parsing
_SEV_ROW_RE = re.compile(
    r"\|\s*(SEV-\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(Yes[^|]*|No[^|]*)\|"
)
_ESC_ROW_RE = re.compile(
    r"\|\s*([a-z][a-z0-9_\-]+)\s*\|\s*(@[a-z0-9_]+)\s*\|\s*(@[a-z0-9_]+)\s*\|\s*(@[a-z0-9_]+)\s*\|"
)


def _parse_severity_table(text: str) -> list[dict]:
    rows = []
    for m in _SEV_ROW_RE.finditer(text):
        rows.append(
            {
                "severity": m.group(1),
                "user_impact": m.group(2).strip(),
                "examples": m.group(3).strip(),
                "page_on_call": m.group(4).strip().lower().startswith("yes"),
            }
        )
    return rows


def _parse_escalation_table(text: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for m in _ESC_ROW_RE.finditer(text):
        service, primary, secondary, manager = m.groups()
        out[service] = {"primary": primary, "secondary": secondary, "manager": manager}
    return out


def apply_runbook(runbook_raw: str, impacted_services: list[str]) -> dict:
    """Sanitize the runbook and produce severity + escalation guidance.

    Returns:
        {
          "sanitized_text": str,
          "stripped_injections": list[str],
          "severity_table": list[dict],
          "escalation_chains": {service: {primary, secondary, manager}},
          "recommended_severity": "SEV-1" | "SEV-2" | "SEV-3" | "SEV-4",
          "rationale": str,
        }
    """
    cleaned, stripped = sanitize_runbook(runbook_raw)
    sev_table = _parse_severity_table(cleaned)
    esc_table = _parse_escalation_table(cleaned)

    critical_services = {"payments", "checkout", "auth", "search", "product-catalog"}
    hit = [s for s in impacted_services if s in critical_services]

    if len(hit) >= 2:
        recommended = "SEV-2"
        rationale = (
            f"{len(hit)} critical revenue-path services impacted ({', '.join(hit)}). "
            "Per runbook, multiple critical services with >5% error rate qualifies for SEV-2."
        )
    elif len(hit) == 1:
        recommended = "SEV-2"
        rationale = (
            f"Single critical revenue-path service impacted ({hit[0]}). "
            "Per runbook, >5% error on a critical service for >5m is SEV-2."
        )
    elif impacted_services:
        recommended = "SEV-3"
        rationale = "No critical revenue-path services impacted; treat as partial degradation."
    else:
        recommended = "SEV-4"
        rationale = "No customer-visible impact detected."

    return {
        "sanitized_text": cleaned,
        "stripped_injections": stripped,
        "severity_table": sev_table,
        "escalation_chains": {s: esc_table.get(s, {}) for s in impacted_services if s in esc_table},
        "recommended_severity": recommended,
        "rationale": rationale,
    }
