from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame
from pytestqt.qtbot import QtBot

from uav_crop_analysis.reporting import (
    MissionReport,
    ReportAnalysis,
    ReportCamera,
    ReportDroneSummary,
    ReportExport,
    ReportImageRecord,
    ReportSpatialProduct,
)
from uav_crop_analysis.ui.report_controller import ReportExportController
from uav_crop_analysis.ui.views import ReportWorkspacePage


NOW = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)


def _report(tmp_path: Path) -> MissionReport:
    preview = tmp_path / "heatmap.png"
    Image.new("RGB", (180, 100), (48, 125, 68)).save(preview)
    orthomosaic_preview = tmp_path / "orthomosaic.png"
    Image.new("RGB", (180, 100), (94, 112, 72)).save(orthomosaic_preview)
    images = tuple(
        ReportImageRecord(
            mission_id="mission-report-ui",
            drone_id=f"drone-0{index // 2 + 1}",
            lane_index=index // 2,
            image_id=f"image-{index + 1:03d}",
            sequence_index=index % 2,
            captured_at=NOW,
            source_path=tmp_path / f"ảnh {index + 1}.jpg",
            latitude=10.75,
            longitude=106.67,
            relative_altitude_m=10.0,
            camera_profile_id="dji-mini-4k",
            estimated_gsd_cm_px=0.43,
            quality_status="valid" if index != 3 else "issue",
            issue_codes=() if index != 3 else ("missing_gps",),
            analysis_job_id="job-report-ui",
            model_id="segformer-v72",
            model_version="7.2-maizemask-weedsgalore-seed42",
            weed_coverage_percent=float(5 + index),
            estimated_weed_area_m2=1.2,
            class_coverage_percent={"background": 60.0, "crop": 33.0, "weed": 7.0},
        )
        for index in range(6)
    )
    drones = tuple(
        ReportDroneSummary(
            drone_id=f"drone-0{lane + 1}",
            lane_index=lane,
            image_count=2,
            valid_image_count=1 if lane == 1 else 2,
            issue_image_count=1 if lane == 1 else 0,
            analyzed_image_count=2,
            telemetry_count=2,
            gps_coverage=0.5 if lane == 1 else 1.0,
            altitude_coverage=1.0,
            mean_weed_coverage_percent=6.0 + lane * 2,
        )
        for lane in range(3)
    )
    return MissionReport(
        schema_version=1,
        template_version="1.0",
        generated_at=NOW,
        mission_id="mission-report-ui",
        mission_name="Khảo sát ngô khu A",
        mission_created_at=NOW,
        drone_count=3,
        altitude_m=10.0,
        gimbal_pitch_deg=-90.0,
        forward_overlap=0.75,
        side_overlap=0.65,
        capture_mode="stop_and_capture",
        cameras=(
            ReportCamera(
                "dji-mini-4k",
                "DJI Mini 4K",
                "DJI",
                "FC7703",
                4000,
                3000,
                82.0,
                0.43,
                "altitude_horizontal_fov",
            ),
        ),
        drones=drones,
        images=images,
        analyses=(
            ReportAnalysis(
                "job-report-ui",
                "completed",
                "segformer-v72",
                "7.2-maizemask-weedsgalore-seed42",
                "best",
                6,
                0.5,
                NOW,
                "a" * 64,
            ),
        ),
        spatial_products=(
            ReportSpatialProduct(
                "orthomosaic-ui",
                "orthomosaic",
                "georeferenced",
                tmp_path / "orthomosaic.tif",
                orthomosaic_preview,
                "EPSG:32648",
                (0.02, 0.02),
                (500000.0, 1199990.0, 500010.0, 1200000.0),
                None,
                None,
            ),
            ReportSpatialProduct(
                "heatmap-ui",
                "weed_heatmap",
                "georeferenced",
                tmp_path / "weed.tif",
                preview,
                "EPSG:32648",
                (0.02, 0.02),
                (500000.0, 1199990.0, 500010.0, 1200000.0),
                "orthomosaic-ui",
                "job-report-ui",
            ),
        ),
        limitations=(
            "Weed là semantic coverage; không đếm instance weed.",
            "Maize chờ checkpoint instance.",
        ),
    )


def test_report_workspace_renders_dashboard_and_emits_export(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    page = ReportWorkspacePage()
    qtbot.addWidget(page)
    page.resize(1200, 760)
    page.set_report(_report(tmp_path))

    assert page.title.text() == "Khảo sát ngô khu A"
    assert page.image_value.text() == "6"
    assert page.valid_value.text() == "5"
    assert page.analyzed_value.text() == "6"
    assert page.crop_value.text() == "33,00%"
    assert page.weed_value.text() == "7,50%"
    assert page.drone_model.rowCount() == 3
    assert page.image_model.rowCount() == 6
    assert page.analysis_model.rowCount() == 1
    assert "EPSG:32648" in page.spatial_value.text()
    assert page.orthomosaic_preview.pixmap() is not None
    assert page.heatmap_preview.pixmap() is not None
    assert page.inspector_scroll.widget().objectName() == "InspectorPanel"
    assert not page.findChildren(QFrame, "ReportCard")

    with qtbot.waitSignal(page.exportRequested, timeout=1000) as signal:
        qtbot.mouseClick(page.export_button, Qt.MouseButton.LeftButton)
    assert signal.args == ["mission-report-ui"]


def test_report_workspace_opens_generated_html(qtbot: QtBot, tmp_path: Path) -> None:
    page = ReportWorkspacePage()
    qtbot.addWidget(page)
    page.set_report(_report(tmp_path))
    exported = ReportExport(
        directory=tmp_path,
        report_json=tmp_path / "report.json",
        image_csv=tmp_path / "images.csv",
        report_html=tmp_path / "report.html",
        manifest_json=tmp_path / "manifest.json",
        checksums=(),
    )
    page.set_export(exported)

    assert page.open_button.isEnabled()
    with qtbot.waitSignal(page.openReportRequested, timeout=1000) as signal:
        qtbot.mouseClick(page.open_button, Qt.MouseButton.LeftButton)
    assert signal.args == [str(exported.report_html)]


def test_report_export_controller_runs_off_ui_thread(qtbot: QtBot) -> None:
    controller = ReportExportController()

    with qtbot.waitSignal(controller.completed, timeout=2000) as signal:
        assert controller.start(lambda: "exported")

    assert signal.args == ["exported"]
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=1000)
