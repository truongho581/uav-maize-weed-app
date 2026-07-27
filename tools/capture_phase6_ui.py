"""Render deterministic Phase 6 Data and Analysis workspace screenshots."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--view", choices=("data", "analysis"), required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)

    import numpy as np
    from PIL import Image
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from uav_crop_analysis.application import (
        AnalysisModelOption,
        AnalysisTask,
        DataQualityIssue,
        DroneCoverage,
        DroneDataGroup,
        ImageDataRow,
        MissionDataStatus,
        MissionDataWorkspace,
        MissionOverview,
        MissionSummary,
        ModelArtifactOption,
    )
    from uav_crop_analysis.domain import CameraProfile, SurveyMission
    from uav_crop_analysis.jobs import (
        AnalysisInput,
        AnalysisJob,
        AnalysisJobConfig,
        AnalysisResult,
        JobStatus,
    )
    from uav_crop_analysis.ui.shell import MainWindow
    from uav_crop_analysis.ui.tokens import application_font, stylesheet
    from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel

    now = datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc)
    mission = SurveyMission.create(
        "mission-2026-khu-a",
        "Khảo sát ngô khu A",
        ("drone-01", "drone-02", "drone-03"),
        created_at=now,
    )
    root = args.output.parent / ".phase6-fixtures"
    root.mkdir(parents=True, exist_ok=True)
    source = root / "field.png"
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    height, width = 540, 960
    y, x = np.indices((height, width))
    original = np.empty((height, width, 3), dtype=np.uint8)
    original[..., 0] = 55 + ((x // 80) % 2) * 15
    original[..., 1] = 105 + ((y // 54) % 2) * 28
    original[..., 2] = 48 + ((x + y) % 35)
    mask = ((x - 460) ** 2 + (y - 250) ** 2 < 75**2) | (
        (x - 730) ** 2 + (y - 350) ** 2 < 48**2
    )
    probability = np.where(mask, 0.88, 0.08).astype(np.float32)
    Image.fromarray(original).save(source)
    Image.fromarray(mask.astype(np.uint8) * 255).save(
        artifact_dir / "field-001.weed_mask.png"
    )
    np.save(artifact_dir / "field-001.weed_probability.npy", probability)

    image_rows = []
    issues = []
    for drone_index in range(3):
        drone_id = f"drone-0{drone_index + 1}"
        rows = []
        for sequence in range(8):
            issue_codes = ("telemetry_skew",) if drone_index == 1 and sequence == 4 else ()
            row = ImageDataRow(
                image_id=f"{drone_id}-{sequence + 1:04d}",
                drone_id=drone_id,
                sequence_index=sequence,
                source_path=root / drone_id / f"IMG_{sequence + 1:04d}.JPG",
                captured_at=now + timedelta(seconds=sequence * 3),
                width_px=4000,
                height_px=3000,
                latitude=10.7621 + drone_index * 0.00004,
                longitude=106.6812 + sequence * 0.00003,
                relative_altitude_m=10.0,
                telemetry_offset_ms=2450 if issue_codes else 35,
                camera_profile_id="dji-mini-4k",
                source_exists=True,
                issue_codes=issue_codes,
            )
            rows.append(row)
            if issue_codes:
                issues.append(
                    DataQualityIssue(
                        "telemetry_skew",
                        "Độ lệch thời gian telemetry lớn hơn 2 giây.",
                        "warning",
                        drone_id,
                        row.image_id,
                        row.source_path,
                    )
                )
        image_rows.append(
            DroneDataGroup(
                drone_id,
                drone_index,
                tuple(rows),
                len(rows),
                sum(bool(row.issue_codes) for row in rows),
            )
        )
    data = MissionDataWorkspace(
        mission,
        tuple(image_rows),
        (
            CameraProfile(
                "dji-mini-4k",
                "DJI Mini 4K FC7703",
                make="DJI",
                model="FC7703",
                image_width_px=4000,
                image_height_px=3000,
                focal_length_mm=4.49,
            ),
        ),
        tuple(issues),
    )
    overview = MissionOverview(
        mission,
        MissionDataStatus.READY,
        24,
        1.0,
        1.0,
        1,
        tuple(
            DroneCoverage(f"drone-0{index + 1}", index, 8, 8, 8, 8)
            for index in range(3)
        ),
        (),
    )

    class ScreenshotQuery:
        def list_missions(self) -> tuple[MissionSummary, ...]:
            return (
                MissionSummary(
                    mission.mission_id.value,
                    mission.name,
                    now,
                    24,
                    1.0,
                    MissionDataStatus.READY,
                    JobStatus.COMPLETED,
                ),
            )

        def get_overview(self, mission_id: str) -> MissionOverview | None:
            return overview if mission_id == mission.mission_id.value else None

    semantic_model = AnalysisModelOption(
        "segformer-b0-v72-loso",
        "7.2-loso",
        "segformer_b0",
        AnalysisTask.SEMANTIC,
        "evaluation_only_loso",
        "pytorch",
        ("weed",),
        (ModelArtifactOption("best_test_D1_seed_42", root / "best.pth", True),),
    )
    instance_model = AnalysisModelOption(
        "yolov8-maize-instance",
        "pending",
        "yolov8",
        AnalysisTask.MAIZE_INSTANCE,
        "awaiting_checkpoint_path",
        "ultralytics",
        ("maize2", "maize4", "maize6"),
        (),
    )
    config = AnalysisJobConfig(
        mission.mission_id.value,
        semantic_model.model_id,
        "best_test_D1_seed_42",
        root / "registry.json",
        (AnalysisInput("field-001", source),),
        root / "results",
    )
    result = AnalysisResult(
        artifact_dir,
        "0" * 64,
        (
            {
                "image_id": "field-001",
                "source_path": str(source),
                "width": width,
                "height": height,
                "weed_coverage_percent": float(mask.mean() * 100),
                "tile_count": 2,
            },
        ),
        {},
    )
    completed = AnalysisJob("job-semantic-003", config).start().complete(result)

    app = QApplication([])
    app.setStyle("Fusion")
    app.setFont(application_font())
    app.setStyleSheet(stylesheet())
    window = MainWindow(MissionWorkspaceViewModel(ScreenshotQuery()))
    window.resize(args.width, args.height)
    if args.view == "data":
        window.data_workspace.set_data(data)
        window.pages.setCurrentWidget(window.data_workspace)
        window.data_nav.setEnabled(True)
        window._set_nav(window.data_nav)
    else:
        window.analysis_workspace.set_workspace(
            mission.mission_id.value,
            (semantic_model,),
            (instance_model,),
            (completed,),
        )
        window.analysis_workspace.viewer.set_job(completed)
        window.analysis_workspace.viewer.layer_tabs.setCurrentIndex(3)
        window.pages.setCurrentWidget(window.analysis_workspace)
        window.analysis_nav.setEnabled(True)
        window._set_nav(window.analysis_nav)
    window.show()
    app.processEvents()
    QTest.qWait(100)
    if args.view == "analysis":
        window.analysis_workspace.viewer.fit_image()
    window.repaint()
    app.processEvents()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image = window.grab().toImage()
    if not image.save(str(args.output)):
        raise RuntimeError(f"failed to save screenshot: {args.output}")
    print(f"{args.output} {image.width()}x{image.height()} scale={args.scale:g}")
    window.close()
    app.quit()


if __name__ == "__main__":
    main()
