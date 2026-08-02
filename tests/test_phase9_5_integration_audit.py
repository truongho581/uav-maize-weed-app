from __future__ import annotations

import json
from pathlib import Path

from tools.phase9_5_integration_audit import golden_projection, run_audit


ROOT = Path(__file__).resolve().parents[1]


def test_phase9_5_golden_audit_for_one_to_three_drones(tmp_path: Path) -> None:
    summary = run_audit(tmp_path / "audit")
    expected = json.loads(
        (ROOT / "tests/fixtures/phase9_5/planner_audit_golden.json").read_text(
            encoding="utf-8"
        )
    )

    assert golden_projection(summary) == expected
    assert (tmp_path / "audit/audit-summary.json").is_file()
    assert [item["drone_count"] for item in summary["scenarios"]] == [1, 2, 3]
    assert summary["safety"]["exposed_forbidden_methods"] == []
