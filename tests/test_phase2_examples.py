from pathlib import Path

from uav_crop_analysis.adapters import load_mission_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_phase2_example_manifest_is_loadable() -> None:
    request = load_mission_manifest(PROJECT_ROOT / "docs/phase2/mission.example.json")

    assert request.mission.mission_id.value == "mission-2026-001"
    assert len(request.sources) == 3
    assert [source.drone_id.value for source in request.sources] == [
        "drone-01",
        "drone-02",
        "drone-03",
    ]
