from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
import pytest
from pytestqt.qtbot import QtBot

from uav_crop_analysis.application import (
    AnalysisModelOption,
    AnalysisRequest,
    AnalysisTask,
    DataQualityIssue,
    DroneDataGroup,
    ImageDataRow,
    ImportMissionData,
    ImportReport,
    MetadataCoverage,
    MissionImportRequest,
    MissionDataWorkspace,
    ModelArtifactOption,
)
from uav_crop_analysis.domain import SurveyMission
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    AnalysisResult,
    JobError,
)
from uav_crop_analysis.ui.result_layers import LayerMode, result_entries, render_layer
from uav_crop_analysis.ui.import_controller import MissionImportController
from uav_crop_analysis.ui.views import AnalysisWorkspacePage, DataWorkspacePage
from uav_crop_analysis.ui.views.result_viewer import ResultViewer


NOW = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)


def _mission() -> SurveyMission:
    return SurveyMission.create(
        "mission-phase6-ui",
        "Khảo sát ngô Phase 6",
        ("drone-01", "drone-02", "drone-03"),
        created_at=NOW,
    )


def _row(root: Path, drone_id: str, *, issue: bool = False) -> ImageDataRow:
    return ImageDataRow(
        image_id=f"{drone_id}-image",
        drone_id=drone_id,
        sequence_index=0,
        source_path=root / drone_id / "image.jpg",
        captured_at=NOW,
        width_px=1920,
        height_px=1080,
        latitude=None if issue else 10.75,
        longitude=None if issue else 106.67,
        relative_altitude_m=None if issue else 10.0,
        telemetry_offset_ms=20,
        camera_profile_id=None,
        source_exists=not issue,
        issue_codes=("missing_gps",) if issue else (),
    )


def _data(root: Path) -> MissionDataWorkspace:
    rows = (
        _row(root, "drone-01"),
        _row(root, "drone-02", issue=True),
        _row(root, "drone-03"),
    )
    issue = DataQualityIssue(
        code="missing_gps",
        message="Ảnh chưa có tọa độ GPS.",
        severity="error",
        drone_id="drone-02",
        image_id="drone-02-image",
    )
    groups = tuple(
        DroneDataGroup(
            drone_id=f"drone-0{index + 1}",
            lane_index=index,
            images=(rows[index],),
            telemetry_count=1,
            issue_count=1 if index == 1 else 0,
        )
        for index in range(3)
    )
    return MissionDataWorkspace(_mission(), groups, (), (issue,))


def _model(root: Path, *, semantic: bool) -> AnalysisModelOption:
    artifact = root / "model.ckpt"
    if semantic:
        artifact.write_bytes(b"checkpoint")
    return AnalysisModelOption(
        model_id="semantic-ready" if semantic else "instance-pending",
        version="1",
        family="attention_unet" if semantic else "yolov8",
        task=(AnalysisTask.SEMANTIC if semantic else AnalysisTask.MAIZE_INSTANCE),
        status="deployment_ready" if semantic else "awaiting_checkpoint_path",
        runtime="pytorch" if semantic else "ultralytics",
        target_classes=("weed",) if semantic else ("maize2", "maize4", "maize6"),
        artifacts=(ModelArtifactOption("best", artifact, semantic),) if semantic else (),
    )


def _job_config(root: Path, image_count: int = 1) -> AnalysisJobConfig:
    inputs = tuple(
        AnalysisInput(
            f"image-{index:02d}",
            root / ("source.png" if index == 1 else f"source-{index:02d}.png"),
        )
        for index in range(1, image_count + 1)
    )
    return AnalysisJobConfig(
        mission_id="mission-phase6-ui",
        model_id="semantic-ready",
        artifact_role="best",
        registry_path=root / "registry.json",
        inputs=inputs,
        output_root=root / "results",
    )


def _completed_job(root: Path, image_count: int = 1) -> AnalysisJob:
    artifact_dir = root / "results" / "job-completed" / "artifacts"
    artifact_dir.mkdir(parents=True)
    summaries = []
    for index, analysis_input in enumerate(_job_config(root, image_count).inputs, start=1):
        original = np.zeros((3, 4, 3), dtype=np.uint8)
        original[:, :] = (30 + index, 120, 55)
        Image.fromarray(original).save(analysis_input.source_path)
        mask = np.zeros((3, 4), dtype=np.uint8)
        mask[0, 0] = 255
        Image.fromarray(mask).save(
            artifact_dir / f"{analysis_input.image_id}.weed_mask.png"
        )
        probability = np.linspace(0, 1, 12, dtype=np.float32).reshape(3, 4)
        np.save(
            artifact_dir / f"{analysis_input.image_id}.weed_probability.npy",
            probability,
        )
        summaries.append(
            {
                "image_id": analysis_input.image_id,
                "source_path": str(analysis_input.source_path),
                "width": 4,
                "height": 3,
                "weed_coverage_percent": 100 / 12,
                "tile_count": 1,
            }
        )
    result = AnalysisResult(
        artifact_dir=artifact_dir,
        manifest_sha256="0" * 64,
        image_summaries=tuple(summaries),
        provenance={},
    )
    return AnalysisJob("job-completed", _job_config(root, image_count)).start().complete(result)


def test_data_workspace_exposes_three_drone_tabs_and_issue_filter(
    qtbot: QtBot, tmp_path: Path
) -> None:
    page = DataWorkspacePage()
    qtbot.addWidget(page)
    page.set_data(_data(tmp_path))

    assert page.drone_tabs.count() == 3
    assert page.issue_model.rowCount() == 1
    assert page.image_model.rowCount() == 1

    page.drone_tabs.setCurrentIndex(0)
    page.only_issues.setChecked(True)
    assert page.image_model.rowCount() == 0

    page.drone_tabs.setCurrentIndex(1)
    assert page.image_model.rowCount() == 1


@pytest.mark.parametrize("drone_count", [1, 2])
def test_data_workspace_tab_count_matches_mission_assignments(
    qtbot: QtBot,
    drone_count: int,
) -> None:
    drone_ids = tuple(f"drone-{index}" for index in range(1, drone_count + 1))
    mission = SurveyMission.create(
        f"mission-{drone_count}",
        f"Mission {drone_count}",
        drone_ids,
        created_at=NOW,
    )
    groups = tuple(
        DroneDataGroup(drone_id, index, (), 0, 0)
        for index, drone_id in enumerate(drone_ids)
    )
    page = DataWorkspacePage()
    qtbot.addWidget(page)

    page.set_data(MissionDataWorkspace(mission, groups, (), ()))

    assert page.drone_tabs.count() == drone_count


def test_analysis_workspace_keeps_weed_semantic_and_maize_instance_separate(
    qtbot: QtBot, tmp_path: Path
) -> None:
    page = AnalysisWorkspacePage()
    qtbot.addWidget(page)
    page.set_workspace(
        "mission-phase6-ui",
        (_model(tmp_path, semantic=True),),
        (_model(tmp_path, semantic=False),),
        (),
    )

    assert page.run_button.isEnabled()
    with qtbot.waitSignal(page.submitRequested, timeout=1000) as signal:
        qtbot.mouseClick(page.run_button, Qt.MouseButton.LeftButton)
    request = signal.args[0]
    assert isinstance(request, AnalysisRequest)
    assert request.model_id == "semantic-ready"
    assert request.weed_threshold == 0.5

    page.threshold.setValue(0.65)
    assert page.run_button.isEnabled()
    with qtbot.waitSignal(page.submitRequested, timeout=1000) as rerun_signal:
        qtbot.mouseClick(page.run_button, Qt.MouseButton.LeftButton)
    rerun_request = rerun_signal.args[0]
    assert isinstance(rerun_request, AnalysisRequest)
    assert rerun_request.weed_threshold == 0.65
    assert page.workspace_splitter.orientation() is Qt.Orientation.Horizontal
    assert not page.settings_dialog.isVisible()

    page.task_tabs.setCurrentIndex(1)
    assert not page.run_button.isEnabled()
    assert "đối tượng" in page.model_status.text().lower()


def test_analysis_workspace_can_submit_available_maize_instance_checkpoint(
    qtbot: QtBot, tmp_path: Path
) -> None:
    checkpoint = tmp_path / "instance.pt"
    checkpoint.write_bytes(b"checkpoint")
    instance = AnalysisModelOption(
        model_id="yolov8-ready",
        version="7.2",
        family="yolov8",
        task=AnalysisTask.MAIZE_INSTANCE,
        status="production_default",
        runtime="ultralytics",
        target_classes=("maize2", "maize4", "maize6"),
        artifacts=(ModelArtifactOption("best", checkpoint, True),),
    )
    page = AnalysisWorkspacePage()
    qtbot.addWidget(page)
    page.set_workspace("mission-phase6-ui", (), (instance,), ())
    page.task_tabs.setCurrentIndex(1)

    assert page.run_button.isEnabled()
    assert not page.threshold.isEnabled()
    with qtbot.waitSignal(page.submitRequested, timeout=1000) as signal:
        qtbot.mouseClick(page.run_button, Qt.MouseButton.LeftButton)
    request = signal.args[0]
    assert isinstance(request, AnalysisRequest)
    assert request.model_id == "yolov8-ready"


def test_analysis_job_actions_follow_selected_job_state(
    qtbot: QtBot, tmp_path: Path
) -> None:
    page = AnalysisWorkspacePage()
    qtbot.addWidget(page)
    page.set_workspace(
        "mission-phase6-ui",
        (_model(tmp_path, semantic=True),),
        (),
        (AnalysisJob("job-queued", _job_config(tmp_path)),),
    )
    assert page.cancel_button.isEnabled()
    assert not page.retry_button.isEnabled()
    assert page.delete_button.isEnabled()
    assert page.job_model.columnCount() == 3

    failed = AnalysisJob("job-failed", _job_config(tmp_path)).start().fail(
        JobError("inference_failed", "failed", True, {})
    )
    page.set_jobs((failed,))
    assert not page.cancel_button.isEnabled()
    assert page.retry_button.isEnabled()

    page.set_jobs((_completed_job(tmp_path),))
    assert page.open_result_button.isEnabled()


def test_result_viewer_renders_original_mask_probability_and_overlay(
    qtbot: QtBot, tmp_path: Path
) -> None:
    job = _completed_job(tmp_path)
    viewer = ResultViewer()
    qtbot.addWidget(viewer)
    viewer.resize(900, 500)
    viewer.set_job(job)

    assert viewer.image_combo.count() == 1
    assert not viewer._pixmap_item.pixmap().isNull()
    assert viewer.size_value.text() == "4 × 3"

    entry = result_entries(job)[0]
    mask_image = render_layer(entry, LayerMode.WEED_MASK)
    weed = mask_image.pixelColor(0, 0)
    background = mask_image.pixelColor(1, 0)
    assert (weed.red(), weed.green(), weed.blue()) == (214, 74, 58)
    assert (background.red(), background.green(), background.blue()) == (0, 0, 0)
    for index in range(viewer.layer_tabs.count()):
        viewer.layer_tabs.setCurrentIndex(index)
        assert not viewer._pixmap_item.pixmap().isNull()
    assert viewer.opacity.isVisibleTo(viewer)

    entry.source_path.unlink()
    assert not render_layer(entry, LayerMode.WEED_MASK).isNull()
    assert not render_layer(entry, LayerMode.PROBABILITY).isNull()


def test_result_viewer_moves_between_images_with_arrow_buttons(
    qtbot: QtBot, tmp_path: Path
) -> None:
    viewer = ResultViewer()
    qtbot.addWidget(viewer)
    viewer.set_job(_completed_job(tmp_path, image_count=2))

    assert viewer.image_combo.currentIndex() == 0
    assert viewer.image_position.text() == "1 / 2"
    assert not viewer.previous_image.isEnabled()
    assert viewer.next_image.isEnabled()

    qtbot.mouseClick(viewer.next_image, Qt.MouseButton.LeftButton)
    assert viewer.image_combo.currentIndex() == 1
    assert viewer.image_position.text() == "2 / 2"
    assert viewer.previous_image.isEnabled()
    assert not viewer.next_image.isEnabled()

    qtbot.mouseClick(viewer.previous_image, Qt.MouseButton.LeftButton)
    assert viewer.image_combo.currentIndex() == 0


def test_result_viewer_uses_distinct_legend_entries_for_maize_stages(
    qtbot: QtBot,
) -> None:
    viewer = ResultViewer()
    qtbot.addWidget(viewer)

    viewer._configure_layers("maize_instance_segmentation")  # noqa: SLF001

    assert viewer.legend_label.text() == "Ngô 2 lá"
    assert viewer.swatch.objectName() == "Maize2Swatch"
    assert viewer.crop_legend_label.text() == "Ngô 4 lá"
    assert viewer.crop_swatch.objectName() == "Maize4Swatch"
    assert viewer.maize6_legend_label.text() == "Ngô 6 lá"
    assert viewer.maize6_swatch.objectName() == "Maize6Swatch"
    assert viewer.crop_swatch.isVisibleTo(viewer)
    assert viewer.maize6_swatch.isVisibleTo(viewer)


def test_mission_import_controller_runs_manifest_import_off_ui_thread(
    qtbot: QtBot,
) -> None:
    class FakeImportService:
        def execute(self, request: MissionImportRequest) -> ImportReport:
            return ImportReport(
                mission_id=request.mission.mission_id.value,
                images=(),
                telemetry_samples=(),
                camera_profiles=(),
                issues=(),
                image_counts_by_drone={
                    assignment.drone_id.value: 0
                    for assignment in request.mission.assignments
                },
                metadata_coverage=MetadataCoverage(0, 0, 0, 0),
                persisted=True,
            )

    controller = MissionImportController(
        cast(ImportMissionData, FakeImportService())
    )
    manifest = Path(__file__).parents[1] / "docs/phase2/mission.example.json"
    with qtbot.waitSignal(controller.completed, timeout=2000) as signal:
        assert controller.start(manifest)
    report = signal.args[0]
    assert isinstance(report, ImportReport)
    assert report.persisted
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=2000)
