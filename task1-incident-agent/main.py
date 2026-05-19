"""opscopilot — Incident Response Agent (Task 1 entry point).

Runs the LangGraph pipeline end-to-end on a data directory and writes:
  outputs/incident_report.md
  outputs/action_items.json
  outputs/run_audit.json   (state machine trace, tool-call audit)

Usage:
  python main.py                                  # uses ./data and ./outputs
  python main.py --data data --out outputs        # explicit paths
  python main.py --data tests/scenarios/partial_logs --out outputs/partial_logs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent.graph import build_graph
from agent.llm import llm_enabled


def run(data_dir: str, out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    graph = build_graph()
    initial = {"data_dir": data_dir, "tool_calls": [], "errors": []}
    print(f"[opscopilot] starting pipeline (LLM enabled: {llm_enabled()})")
    final_state = graph.invoke(initial)
    print(f"[opscopilot] pipeline completed in 7 nodes")

    # write report
    report_path = out / "incident_report.md"
    report_path.write_text(final_state.get("report_md", "_no report produced_"), encoding="utf-8")
    print(f"[opscopilot] wrote {report_path}")

    # write action items
    actions_path = out / "action_items.json"
    actions_path.write_text(
        json.dumps(final_state.get("action_items", []), indent=2),
        encoding="utf-8",
    )
    print(f"[opscopilot] wrote {actions_path}")

    # write audit
    audit = {
        "llm_enabled": final_state.get("llm_enabled", False),
        "safe_to_report": final_state.get("safe_to_report", False),
        "severity": final_state.get("severity", ""),
        "impacted_services": final_state.get("impacted_services", []),
        "start_time": final_state.get("start_time", ""),
        "end_time": final_state.get("end_time", ""),
        "verifier_report": final_state.get("verifier_report", {}),
        "tool_calls": final_state.get("tool_calls", []),
        "stripped_injections": final_state.get("stripped_injections", []),
        "hypotheses": [
            {k: v for k, v in h.items() if k != "evidence_index"}
            for h in final_state.get("hypotheses", [])
        ],
    }
    audit_path = out / "run_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    print(f"[opscopilot] wrote {audit_path}")

    print()
    print("=== summary ===")
    print(f" severity      : {final_state.get('severity')}")
    print(f" impacted      : {', '.join(final_state.get('impacted_services', []))}")
    print(f" start time    : {final_state.get('start_time')}")
    print(f" top hypothesis: {final_state.get('top_hypothesis', {}).get('id', '?')} (score {final_state.get('top_hypothesis', {}).get('score', 0):.2f})")
    vr = final_state.get("verifier_report", {})
    print(f" evidence cov  : {vr.get('evidence_coverage', 0):.0%}")
    print(f" hallucination : {vr.get('hallucination_rate', 0):.0%}")
    print(f" tool-call ok  : {vr.get('tool_call_correctness', 0):.0%}")
    print(f" injections    : {len(final_state.get('stripped_injections', []))} stripped")
    print()
    return final_state


def main(argv: list[str] | None = None) -> int:
    load_dotenv()  # optional .env in cwd
    parser = argparse.ArgumentParser(prog="opscopilot")
    parser.add_argument("--data", default="data", help="data directory (default: ./data)")
    parser.add_argument("--out", default="outputs", help="output directory (default: ./outputs)")
    args = parser.parse_args(argv)

    if not Path(args.data).exists():
        print(f"error: data directory '{args.data}' not found", file=sys.stderr)
        return 2
    run(args.data, args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
