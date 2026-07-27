"""Render deterministic Phase 8 report-workspace screenshots."""

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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    import numpy as np
    from PIL import Image
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from uav_crop_analysis.reporting import (
        MissionReport,
        ReportAnalysis,
        ReportCamera,
        ReportDroneSummary,
        ReportImageRecord,
        ReportSpatialProduct,
    )
    from uav_crop_analysis.ui.shell import MainWindow
    from uav_crop_analysis.ui.tokens import application_font, stylesheet
    from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel

    now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
    root = args.output.parent / ".phase8-fixtures"
    root.mkdir(parents=True, exist_ok=True)
    height, width = 500, 900
    y, x = np.indices((height, width))
    field = np.empty((height, width, 3), dtype=np.uint8)
    field[..., 0] = 44 + ((x // 80) % 2) * 10
    field[..., 1] = 102 + ((y // 48) % 2) * 25
    field[..., 2] = 40 + ((x + y) % 22)
    risk = ((x - 350) ** 2 + (y - 210) ** 2 < 88**2) | (
        (x - 680) ** 2 + (y - 340) ** 2 < 62**2
    )
    field[risk] = (225, 183, 59)
    preview = root / "weed-heatmap-preview.png"
    Image.fromarray(field).save(preview)
    images = tuple(
        ReportImageRecord(
            mission_id="mission-2026-khu-a",
            drone_id=f"drone-0{index // 6 + 1}",
            lane_index=index // 6,
            image_id=f"image-{index + 1:04d}",
            sequence_index=index % 6,
            captured_at=now + timedelta(seconds=index * 3),
            source_path=root / f"drone-0{index // 6 + 1}" / f"IMG_{index + 1:04d}.JPG",
            latitude=None if index == 9 else 10.7621 + index * 0.00002,
            longitude=None if index == 9 else 106.6812 + index * 0.00002,
            relative_altitude_m=10.0,
            camera_profile_id="dji-mini-4k",
            estimated_gsd_cm_px=0.4347,
            quality_status="issue" if index == 9 else "valid",
            issue_codes=("missing_gps",) if index == 9 else (),
            analysis_job_id="job-semantic-004",
            model_id="segformer-b0-v72-loso",
            model_version="7.2-loso",
            weed_coverage_percent=4.2 + index * 0.35,
            estimated_weed_area_m2=1.4 + index * 0.1,
        )
        for index in range(18)
    )
    drones = tuple(
        ReportDroneSummary(
            drone_id=f"drone-0{lane + 1}",
            lane_index=lane,
            image_count=6,
            valid_image_count=5 if lane == 1 else 6,
            issue_image_count=1 if lane == 1 else 0,
            analyzed_image_count=6,
            telemetry_count=6,
            gps_coverage=5 / 6 if lane == 1 else 1.0,
            altitude_coverage=1.0,
            mean_weed_coverage_percent=5.1 + lane * 2.1,
        )
        for lane in range(3)
    )
    report = MissionReport(
        schema_version=1,
        template_version="1.0",
        generated_at=now,
        mission_id="mission-2026-khu-a",
        mission_name="Khảo sát ngô khu A",
        mission_created_at=now,
        drone_count=3,
        altitude_m=10.0,
        gimbal_pitch_deg=-90.0,
        forward_overlap=0.75,
        side_overlap=0.65,
        capture_mode="stop_and_capture",
        cameras=(
            ReportCamera(
                "dji-mini-4k",
                "DJI Mini 4K FC7703",
                "DJI",
                "FC7703",
                4000,
                3000,
                82.0,
                0.4347,
                "altitude_horizontal_fov",
            ),
        ),
        drones=drones,
        images=images,
        analyses=(
            ReportAnalysis(
                "job-semantic-004",
                "completed",
                "segformer-b0-v72-loso",
                "7.2-loso",
                "best_test_D1_seed_42",
                18,
                0.5,
                now,
                "a" * 64,
            ),
        ),
        spatial_products=(
            ReportSpatialProduct(
                "heatmap-2026-khu-a",
                "weed_heatmap",
                "georeferenced",
                root / "weed-probability.tif",
                preview,
                "EPSG:32648",
                (0.02, 0.02),
                (500000.0, 1199980.0, 500030.0, 1200000.0),
                "orthomosaic-2026-khu-a",
                "job-semantic-004",
            ),
        ),
        limitations=(
            "Weed là semantic coverage; báo cáo không đếm instance weed.",
            "Maize instance chưa có số liệu cho tới khi checkpoint được đăng ký.",
            "GSD và diện tích weed là giá trị ước tính từ độ cao và HFOV.",
        ),
    )

    class EmptyQuery:
        def list_missions(self) -> tuple[object, ...]:
            return ()

        def get_overview(self, mission_id: str) -> None:
            return None

    app = QApplication([])
    app.setStyle("Fusion")
    app.setFont(application_font())
    app.setStyleSheet(stylesheet())
    window = MainWindow(MissionWorkspaceViewModel(EmptyQuery()))  # type: ignore[arg-type]
    window.resize(args.width, args.height)
    window.report_workspace.set_report(report)
    window.pages.setCurrentWidget(window.report_workspace)
    window.report_nav.setEnabled(True)
    window._set_nav(window.report_nav)
    window.show()
    app.processEvents()
    QTest.qWait(100)
    window.repaint()
    app.processEvents()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image = window.grab().toImage()
    if not image.save(str(args.output)):
        raise RuntimeError(f"failed to save screenshot: {args.output}")
    print(f"{args.output} {image.width()}x{image.height()}")
    window.close()
    app.quit()


if __name__ == "__main__":
    main()
