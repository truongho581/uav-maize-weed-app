"""Render deterministic Phase 5 screenshots without a real mission database."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--view", choices=("list", "overview"), default="overview")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)

    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from uav_crop_analysis.application import (
        DroneCoverage,
        JobSummary,
        MissionDataStatus,
        MissionOverview,
        MissionSummary,
    )
    from uav_crop_analysis.domain import SurveyMission
    from uav_crop_analysis.jobs import JobStatus
    from uav_crop_analysis.ui.shell import MainWindow
    from uav_crop_analysis.ui.tokens import application_font, stylesheet
    from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel

    now = datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc)
    mission = SurveyMission.create(
        mission_id="mission-2026-khu-a",
        name="Khảo sát ngô khu A",
        drone_ids=("drone-01", "drone-02", "drone-03"),
        created_at=now,
    )
    overview = MissionOverview(
        mission=mission,
        data_status=MissionDataStatus.INCOMPLETE,
        image_count=354,
        gps_coverage=0.97,
        altitude_coverage=0.99,
        camera_count=1,
        drones=(
            DroneCoverage("drone-01", 0, 120, 120, 120, 120),
            DroneCoverage("drone-02", 1, 118, 118, 114, 118),
            DroneCoverage("drone-03", 2, 116, 116, 110, 114),
        ),
        recent_jobs=(
            JobSummary(
                "job-semantic-003",
                JobStatus.RUNNING,
                0.64,
                "segformer-v72",
                now,
                None,
            ),
            JobSummary(
                "job-semantic-002",
                JobStatus.COMPLETED,
                1.0,
                "deeplabv3plus-v72",
                now,
                None,
            ),
            JobSummary(
                "job-semantic-001",
                JobStatus.FAILED,
                0.31,
                "attention-unet-v72",
                now,
                "Không đủ bộ nhớ thiết bị.",
            ),
        ),
    )
    summaries = (
        MissionSummary(
            mission.mission_id.value,
            mission.name,
            now,
            354,
            0.97,
            MissionDataStatus.INCOMPLETE,
            JobStatus.RUNNING,
        ),
        MissionSummary(
            "mission-2026-khu-b",
            "Khảo sát ngô khu B",
            now.replace(day=26),
            402,
            1.0,
            MissionDataStatus.READY,
            JobStatus.COMPLETED,
        ),
        MissionSummary(
            "mission-2026-khu-c",
            "Khảo sát ngô khu C",
            now.replace(day=25),
            0,
            0.0,
            MissionDataStatus.EMPTY,
            None,
        ),
    )

    class ScreenshotQuery:
        def list_missions(self) -> tuple[MissionSummary, ...]:
            return summaries

        def get_overview(self, mission_id: str) -> MissionOverview | None:
            return overview if mission_id == mission.mission_id.value else None

    app = QApplication([])
    app.setApplicationName("UAV Crop Analysis")
    app.setStyle("Fusion")
    app.setFont(application_font())
    app.setStyleSheet(stylesheet())
    window = MainWindow(MissionWorkspaceViewModel(ScreenshotQuery()))
    window.resize(args.width, args.height)
    if args.view == "overview":
        window.open_mission(mission.mission_id.value)
    window.show()
    app.processEvents()
    QTest.qWait(80)
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
