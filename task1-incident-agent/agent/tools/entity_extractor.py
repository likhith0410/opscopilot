"""Tool 5 — Entity Extractor.

Pulls named entities (services, endpoints, error codes, owner handles, deploy
IDs) out of any text source using regex patterns. Used by Triage to identify
impacted services and by Hypothesis to find candidate causes.
"""

from __future__ import annotations

import re
from collections import Counter

KNOWN_SERVICES = {
    "payments",
    "checkout",
    "auth",
    "redis-cache",
    "db-orders",
    "cdn-edge",
    "fraud-svc",
    "monitoring",
}

ENDPOINT_RE = re.compile(r"\b(?:/v\d+/[\w/\-_.]+)\b")
ERROR_TOKEN_RE = re.compile(
    r"\b("
    r"timeout|exhausted|oom|evict(?:ed|ion|s)?|"
    r"5\d\d|4\d\d|"
    r"cache_miss|pool_exhausted|pool_timeout|"
    r"session_lookup_failed|key_not_found|"
    r"upstream_timeout|downstream_timeout|"
    r"oom_error|OOM"
    r")\b",
    re.IGNORECASE,
)
OWNER_RE = re.compile(r"@([a-z][a-z0-9_]{1,30})")
DEPLOY_RE = re.compile(r"\b(dep_\d+|deploy_id=\S+|[a-z-]+-svc-\d+\.\d+\.\d+)\b")
BUILD_RE = re.compile(r"build=([a-zA-Z0-9._\-]+)")


def extract_entities(text: str) -> dict[str, list[dict]]:
    """Extract entities from `text` (any source) and return ranked lists.

    Returns dict with keys:
        services       -> [{name, count}]
        endpoints      -> [{name, count}]
        errors         -> [{token, count}]
        owners         -> [{handle, count}]
        deploys        -> [{id, count}]
        builds         -> [{name, count}]
    """
    if not text:
        return {k: [] for k in ("services", "endpoints", "errors", "owners", "deploys", "builds")}

    lower = text.lower()
    service_counts = Counter()
    for svc in KNOWN_SERVICES:
        # word boundary on both sides
        pat = re.compile(rf"\b{re.escape(svc)}\b")
        c = len(pat.findall(lower))
        if c:
            service_counts[svc] = c

    endpoints = Counter(ENDPOINT_RE.findall(text))
    errors = Counter(m.lower() for m in ERROR_TOKEN_RE.findall(text))
    owners = Counter(OWNER_RE.findall(text))
    deploys = Counter(DEPLOY_RE.findall(text))
    builds = Counter(BUILD_RE.findall(text))

    def rank(counter: Counter, key: str) -> list[dict]:
        return [{key: name, "count": c} for name, c in counter.most_common()]

    return {
        "services": rank(service_counts, "name"),
        "endpoints": rank(endpoints, "name"),
        "errors": rank(errors, "token"),
        "owners": rank(owners, "handle"),
        "deploys": rank(deploys, "id"),
        "builds": rank(builds, "name"),
    }
