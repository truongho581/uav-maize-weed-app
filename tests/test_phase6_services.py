from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from uav_crop_analysis.adapters import (
    RegistryModelCatalog,
    SQLiteAnalysisJobRepository,
    SQLiteMissionRepository,
)
from uav_crop_analysis.application import (
    AnalysisRequest,
    AnalysisTask,
    AnalysisWorkspaceService,
    MissionDataWorkspaceService,
)
from uav_crop_analysis.domain import DroneId, GeoPoint, ImageAsset, SurveyMission
from uav_crop_analysis.errors import JobStateError, ModelUnavailableError
from uav_crop_analysis.jobs import AnalysisJobService, JobStatus


NOW = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)


def _mission() -> SurveyMission:
    return SurveyMission.create(
        "mission-phase6",
        "Khảo sát Phase 6",
        ("drone-01", "drone-02", "drone-03"),
        created_at=NOW,
    )


def _asset(
    root: Path,
    mission: SurveyMission,
    drone_id: str,
    *,
    exists: bool,
    metadata: bool,
) -> ImageAsset:
    path = root / drone_id / "image-001.jpg"
    if exists:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test-image")
    return ImageAsset(
        asset_id=f"{drone_id}-image-001",
        mission_id=mission.mission_id,
        drone_id=DroneId(drone_id),
        source_path=path,
        sha256=hashlib.sha256(drone_id.encode()).hexdigest(),
        size_bytes=10,
        captured_at=NOW,
        width_px=1920,
        height_px=1080,
        sequence_index=0,
        position=GeoPoint(10.75, 106.67) if metadata else None,
        relative_altitude_m=10.0 if metadata else None,
    )


def _registry(root: Path) -> Path:
    checkpoint = root / "semantic.ckpt"
    checkpoint.write_bytes(b"semantic-checkpoint")
    checksum = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    common = {
        "version": "1",
        "input_size": [640, 640],
        "dataset_version": "test",
        "preprocessing": {
            "color_space": "rgb",
            "resize_mode": "stretch",
            "interpolation": "bilinear",
            "value_scale": 1 / 255,
            "mean": [0, 0, 0],
            "std": [1, 1, 1],
        },
    }
    payload = {
        "schema_version": 2,
        "artifact_root": ".",
        "models": [
            {
                **common,
                "id": "semantic-ready",
                "family": "attention_unet",
                "task": "semantic_segmentation",
                "status": "deployment_ready",
                "class_names": ["background", "crop", "weed"],
                "target_classes": ["crop", "weed"],
                "runtime": {"kind": "pytorch", "output_adapter": "semantic_logits"},
                "artifacts": [
                    {
                        "role": "best",
                        "path": checkpoint.name,
                        "sha256": checksum,
                        "format": "pytorch",
                    }
                ],
            },
            {
                **common,
                "id": "instance-pending",
                "family": "yolov8",
                "task": "maize_instance_segmentation",
                "status": "awaiting_checkpoint_path",
                "class_names": ["maize2", "maize4", "maize6"],
                "target_classes": ["maize2", "maize4", "maize6"],
                "runtime": {
                    "kind": "ultralytics",
                    "output_adapter": "ultralytics_masks",
                },
                "artifacts": [],
            },
        ],
    }
    path = root / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _services(tmp_path: Path) -> tuple[
    SQLiteMissionRepository,
    AnalysisWorkspaceService,
    SurveyMission,
]:
    database = tmp_path / "app.db"
    missions = SQLiteMissionRepository(database)
    mission = _mission()
    images = (
        _asset(tmp_path, mission, "drone-01", exists=True, metadata=True),
        _asset(tmp_path, mission, "drone-02", exists=True, metadata=False),
        _asset(tmp_path, mission, "drone-03", exists=False, metadata=True),
    )
    missions.save_bundle(mission, (), images, ())
    jobs = AnalysisJobService(SQLiteAnalysisJobRepository(database))
    analysis = AnalysisWorkspaceService(
        missions,
        jobs,
        RegistryModelCatalog(_registry(tmp_path)),
        tmp_path / "registry.json",
        tmp_path / "results",
    )
    return missions, analysis, mission


def test_data_workspace_groups_three_drones_and_quality_issues(tmp_path: Path) -> None:
    missions, _, mission = _services(tmp_path)

    data = MissionDataWorkspaceService(missions).get_data(mission.mission_id.value)

    assert data is not None
    assert data.image_count == 3
    assert [group.drone_id for group in data.drones] == [
        "drone-01",
        "drone-02",
        "drone-03",
    ]
    assert not data.drones[0].images[0].has_issues
    assert set(data.drones[1].images[0].issue_codes) == {
        "missing_gps",
        "missing_altitude",
    }
    assert data.drones[2].images[0].issue_codes == ("source_missing",)


def test_analysis_catalog_keeps_crop_weed_semantic_and_maize_instance_separate(
    tmp_path: Path,
) -> None:
    _, analysis, _ = _services(tmp_path)

    semantic = analysis.list_models(AnalysisTask.SEMANTIC)
    instance = analysis.list_models(AnalysisTask.MAIZE_INSTANCE)

    assert semantic[0].target_classes == ("crop", "weed")
    assert semantic[0].available
    assert instance[0].target_classes == ("maize2", "maize4", "maize6")
    assert not instance[0].available


def test_analysis_submit_builds_persisted_job_from_mission_images(tmp_path: Path) -> None:
    _, analysis, mission = _services(tmp_path)

    job = analysis.submit(
        AnalysisRequest(
            mission_id=mission.mission_id.value,
            model_id="semantic-ready",
            artifact_role="best",
            tile_size=640,
            overlap=64,
            weed_threshold=0.55,
        ),
        auto_start=False,
        job_id="job-phase6",
    )

    assert job.status is JobStatus.QUEUED
    assert len(job.config.inputs) == 3
    assert job.config.weed_threshold == 0.55
    assert analysis.list_jobs(mission.mission_id.value) == (job,)


def test_analysis_rejects_pending_instance_and_unknown_image(tmp_path: Path) -> None:
    _, analysis, mission = _services(tmp_path)
    with pytest.raises(ModelUnavailableError):
        analysis.submit(
            AnalysisRequest(
                mission.mission_id.value,
                "instance-pending",
                "best",
            ),
            auto_start=False,
        )
    with pytest.raises(JobStateError):
        analysis.submit(
            AnalysisRequest(
                mission.mission_id.value,
                "semantic-ready",
                "best",
                selected_image_ids=("unknown",),
            ),
            auto_start=False,
        )
