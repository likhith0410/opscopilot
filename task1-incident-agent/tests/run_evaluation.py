"""Evaluation harness — runs all 12 scenarios + the gold case and reports
metrics suitable for the README.

Usage:
    python tests/run_evaluation.py                 # prints markdown summary
    python tests/run_evaluation.py --json out.json # also writes a machine-readable report

It builds each scenario's data files in a temp directory, invokes the full
LangGraph pipeline (`main.run`), and grades the outputs against the expected
values in `tests/scenarios.json` and `gold/expected.json`.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path

# Force UTF-8 on stdout so unicode glyphs survive Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# allow running as "python tests/run_evaluation.py" without installing the pkg
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.tools import load_all_inputs  # noqa: E402
from main import run  # noqa: E402
from tests.transformations import TRANSFORMATIONS  # noqa: E402

GOLD_DATA_DIR = _ROOT / "data"
GOLD_EXPECTED = _ROOT / "gold" / "expected.json"
SCENARIOS = _ROOT / "tests" / "scenarios.json"


def _materialize(transformed: dict, out_dir: Path) -> None:
    """Write the transformed inputs back to a data directory layout."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "alerts.json").write_text(json.dumps(transformed["alerts"], indent=2), encoding="utf-8")
    (out_dir / "metrics.csv").write_text(transformed["metrics_raw"], encoding="utf-8")
    (out_dir / "chat.txt").write_text(transformed["chat_raw"], encoding="utf-8")
    (out_dir / "runbook.md").write_text(transformed["runbook_raw"], encoding="utf-8")
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    for service, content in transformed["logs"].items():
        (logs_dir / f"{service}.log").write_text(content, encoding="utf-8")


def _grade_scenario(scn: dict, audit: dict, report_text: str) -> tuple[list[str], list[str]]:
    """Return (passed_checks, failed_checks) for one scenario."""
    exp = scn["expected"]
    passed: list[str] = []
    failed: list[str] = []

    severity = audit.get("severity", "")
    impacted = set(audit.get("impacted_services", []))
    vr = audit.get("verifier_report", {})
    stripped = audit.get("stripped_injections", []) or []
    top = next(iter(audit.get("hypotheses", []) or [{}]))
    top_blob = (top.get("statement", "") + " " + " ".join(top.get("supporting_citations", []))).lower()
    safe = bool(audit.get("safe_to_report", False))

    if "severity" in exp:
        (passed if severity == exp["severity"] else failed).append(f"severity={severity} (want {exp['severity']})")

    if "must_include_services" in exp:
        missing = [s for s in exp["must_include_services"] if s not in impacted]
        if missing:
            failed.append(f"missing impacted services: {missing}")
        else:
            passed.append(f"impacted includes {exp['must_include_services']}")

    if "min_evidence_coverage" in exp:
        cov = vr.get("evidence_coverage", 0)
        if cov >= exp["min_evidence_coverage"]:
            passed.append(f"evidence_coverage={cov:.0%}")
        else:
            failed.append(f"evidence_coverage={cov:.0%} (want >= {exp['min_evidence_coverage']:.0%})")

    if "max_hallucination_rate" in exp:
        h = vr.get("hallucination_rate", 1)
        if h <= exp["max_hallucination_rate"]:
            passed.append(f"hallucination_rate={h:.0%}")
        else:
            failed.append(f"hallucination_rate={h:.0%} (want <= {exp['max_hallucination_rate']:.0%})")

    if "min_stripped_injections" in exp:
        if len(stripped) >= exp["min_stripped_injections"]:
            passed.append(f"stripped_injections={len(stripped)}")
        else:
            failed.append(f"stripped_injections={len(stripped)} (want >= {exp['min_stripped_injections']})")

    if "must_have_top_hypothesis_keywords" in exp:
        missing = [k for k in exp["must_have_top_hypothesis_keywords"] if k.lower() not in top_blob]
        if missing:
            failed.append(f"top hypothesis missing keywords: {missing}")
        else:
            passed.append(f"top hypothesis contains {exp['must_have_top_hypothesis_keywords']}")

    if "must_not_have_top_hypothesis_keywords" in exp:
        bad = [k for k in exp["must_not_have_top_hypothesis_keywords"] if k.lower() in top_blob]
        if bad:
            failed.append(f"top hypothesis wrongly contains: {bad}")
        else:
            passed.append(f"top hypothesis excludes {exp['must_not_have_top_hypothesis_keywords']}")

    if exp.get("must_be_inconclusive"):
        text = report_text.lower()
        if "inconclusive" in text:
            passed.append("report is INCONCLUSIVE")
        else:
            failed.append("expected INCONCLUSIVE but report claims a root cause")

    if "safe_to_report" in exp:
        if safe == exp["safe_to_report"]:
            passed.append(f"safe_to_report={safe}")
        else:
            failed.append(f"safe_to_report={safe} (want {exp['safe_to_report']})")

    return passed, failed


def _timeline_accuracy(audit: dict, report_text: str, expected: dict) -> tuple[int, int, list[str]]:
    """Return (anchors_hit, anchors_total, hit_names) — how many gold timeline
    anchors are cited anywhere in the final report (hypotheses, timeline table,
    or evidence sections)."""
    from agent.tools.evidence_indexer import cite

    cited: set[str] = set(cite(report_text))
    for h in audit.get("hypotheses", []) or []:
        cited.update(h.get("supporting_citations", []))
        cited.update(h.get("valid_citations", []))

    anchors = expected.get("expected_timeline_anchors", [])
    hit_names: list[str] = []
    for a in anchors:
        if any(c in cited for c in a.get("must_cite_one_of", [])):
            hit_names.append(a["name"])
    return len(hit_names), len(anchors), hit_names


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", default="", help="optional path to write JSON metrics")
    args = p.parse_args(argv)

    gold_inputs = load_all_inputs(GOLD_DATA_DIR)
    expected_gold = json.loads(GOLD_EXPECTED.read_text(encoding="utf-8"))
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))

    results: list[dict] = []
    total_passed = 0
    total_failed = 0
    cov_sum = 0.0
    halluc_sum = 0.0
    tool_ok_sum = 0.0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for scn in scenarios:
            scn_dir = tmp_path / scn["id"]
            out_dir = tmp_path / f"{scn['id']}-out"
            t_fn = TRANSFORMATIONS[scn["transformation"]]
            _materialize(t_fn(gold_inputs), scn_dir)
            try:
                final = run(str(scn_dir), str(out_dir))
                audit = json.loads((out_dir / "run_audit.json").read_text(encoding="utf-8"))
                report_text = (out_dir / "incident_report.md").read_text(encoding="utf-8")
                passed, failed = _grade_scenario(scn, audit, report_text)
                vr = audit.get("verifier_report", {})
                cov_sum += vr.get("evidence_coverage", 0)
                halluc_sum += vr.get("hallucination_rate", 0)
                tool_ok_sum += vr.get("tool_call_correctness", 0)
                ok = not failed
                results.append({"id": scn["id"], "name": scn["name"], "pass": ok, "passed_checks": passed, "failed_checks": failed})
                total_passed += int(ok)
                total_failed += int(not ok)
            except Exception as e:
                results.append({"id": scn["id"], "name": scn["name"], "pass": False, "error": str(e)})
                total_failed += 1

        # timeline accuracy ONLY on gold case
        gold_out = tmp_path / "S01-gold-out"
        if (gold_out / "run_audit.json").exists():
            gold_audit = json.loads((gold_out / "run_audit.json").read_text(encoding="utf-8"))
            gold_report = (gold_out / "incident_report.md").read_text(encoding="utf-8")
            anchors_hit, anchors_total, hit_names = _timeline_accuracy(gold_audit, gold_report, expected_gold)
        else:
            anchors_hit = anchors_total = 0
            hit_names = []

    n = max(1, len(scenarios))
    overall = {
        "scenarios_run": len(scenarios),
        "scenarios_passed": total_passed,
        "scenarios_failed": total_failed,
        "avg_evidence_coverage": round(cov_sum / n, 3),
        "avg_hallucination_rate": round(halluc_sum / n, 3),
        "avg_tool_call_correctness": round(tool_ok_sum / n, 3),
        "gold_timeline_anchors_hit": anchors_hit,
        "gold_timeline_anchors_total": anchors_total,
        "gold_timeline_accuracy": round(anchors_hit / max(1, anchors_total), 3),
        "results": results,
    }

    # markdown summary
    print()
    print("# opscopilot — Evaluation Report")
    print()
    print(f"- Scenarios run: **{overall['scenarios_run']}**")
    print(f"- Passed: **{overall['scenarios_passed']}** / {overall['scenarios_run']}")
    print(f"- Avg evidence coverage: **{overall['avg_evidence_coverage']:.0%}**")
    print(f"- Avg hallucination rate: **{overall['avg_hallucination_rate']:.0%}**")
    print(f"- Avg tool-call correctness: **{overall['avg_tool_call_correctness']:.0%}**")
    print(f"- Gold timeline accuracy: **{anchors_hit}/{anchors_total} = {overall['gold_timeline_accuracy']:.0%}**")
    print()
    print("## Per-scenario results")
    print()
    print("| ID | Scenario | Result | Notes |")
    print("|---|---|---|---|")
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        notes = ", ".join(r.get("failed_checks", []) or r.get("passed_checks", []))[:160]
        print(f"| {r['id']} | {r['name']} | {status} | {notes} |")
    print()

    if args.json:
        Path(args.json).write_text(json.dumps(overall, indent=2), encoding="utf-8")
        print(f"\nwrote JSON metrics to {args.json}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
