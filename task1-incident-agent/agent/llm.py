"""LLM helper — wraps Gemini via langchain-google-genai with a deterministic
offline fallback so the full pipeline can be exercised without an API key.

If GOOGLE_API_KEY is set, the live model is used. Otherwise `call_llm()` returns
a structured deterministic response based on a simple keyword router. This
lets reviewers run the project end-to-end without any cloud credentials, and
lets us run the LLM-augmented path in CI.
"""

from __future__ import annotations

import json
import os
from typing import Any

_LLM = None


def llm_enabled() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY", "").strip())


def _get_llm():
    global _LLM
    if _LLM is not None:
        return _LLM
    if not llm_enabled():
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    _LLM = ChatGoogleGenerativeAI(
        model=model,
        temperature=0.1,
        max_output_tokens=2048,
    )
    return _LLM


def call_llm(system: str, user: str, *, fallback: dict | str | None = None) -> str:
    """Call the LLM, or return the deterministic `fallback` if no API key.

    Always returns a string. JSON callers should pass `fallback=` as a dict and
    we'll json.dumps it for them.
    """
    llm = _get_llm()
    if llm is None:
        if isinstance(fallback, (dict, list)):
            return json.dumps(fallback)
        return fallback or ""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:  # pragma: no cover — defensive
        if isinstance(fallback, (dict, list)):
            return json.dumps(fallback)
        return fallback or f"[LLM error: {e}]"


def call_llm_json(system: str, user: str, *, fallback: Any) -> Any:
    """Convenience: call the LLM, parse JSON, or return `fallback` on any failure."""
    raw = call_llm(system, user, fallback=fallback)
    # try fenced ```json ... ``` then bare
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()
        # drop trailing fence if any
        if txt.endswith("```"):
            txt = txt[:-3].strip()
    try:
        return json.loads(txt)
    except Exception:
        return fallback
