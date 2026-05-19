"""Pytest harness for the 12 incident scenarios.

Each scenario is a parametrized case that materializes transformed gold data
to a temp directory, runs the full LangGraph pipeline, and asserts the
expected outcome from `tests/scenarios.json`.

Run with:
    pytest tests/
    pytest tests/ -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.tools import load_all_inputs  # noqa: E402
from main import run  # noqa: E402
from tests.run_evaluation import _grade_scenario, _materialize  # noqa: E402
from tests.transformations import TRANSFORMATIONS  # noqa: E402

SCENARIOS = json.loads((_ROOT / "tests" / "scenarios.json").read_text(encoding="utf-8"))
GOLD_INPUTS = load_all_inputs(_ROOT / "data")


@pytest.fixture(scope="session")
def gold_inputs() -> dict:
    return GOLD_INPUTS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["id"])
def test_scenario(scenario: dict, tmp_path: Path, gold_inputs: dict) -> None:
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    transformed = TRANSFORMATIONS[scenario["transformation"]](gold_inputs)
    _materialize(transformed, data_dir)

    run(str(data_dir), str(out_dir))

    audit = json.loads((out_dir / "run_audit.json").read_text(encoding="utf-8"))
    report = (out_dir / "incident_report.md").read_text(encoding="utf-8")

    passed, failed = _grade_scenario(scenario, audit, report)
    assert not failed, (
        f"scenario {scenario['id']} failed checks:\n  "
        + "\n  ".join(failed)
        + f"\npassed:\n  " + "\n  ".join(passed)
    )
