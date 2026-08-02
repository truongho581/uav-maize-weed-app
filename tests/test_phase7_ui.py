from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem, QTabWidget
from pytestqt.qtbot import QtBot

from uav_crop_analysis.application import (
    AnalysisModelOption,
    AnalysisRequest,
    AnalysisTask,
    ModelArtifactOption,
)
from uav_crop_analysis.geospatial import (
    GeoRasterMetadata,
    ProgressCallback,
    SpatialAccuracy,
    SpatialProduct,
    SpatialProductKind,
    SpatialWorkspace,
)
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    AnalysisResult,
)
from uav_crop_analysis.ui.spatial_controller import SpatialTaskController
from uav_crop_analysis.ui.spatial_regions import extract_weed_regions
from uav_crop_analysis.ui.views import SpatialWorkspacePage
from uav_crop_analysis.ui.views.map_overlay import build_field_map_html, build_leaflet_html


NOW = datetime(2026, 7, 27, 11, 0, tzinfo=timezone.utc)


def _model(tmp_path: Path) -> AnalysisModelOption:
    checkpoint = tmp_path / "semantic.ckpt"
    checkpoint.write_bytes(b"checkpoint")
    return AnalysisModelOption(
        model_id="semantic-v72",
        version="72",
        family="segformer",
        task=AnalysisTask.SEMANTIC,
        status="deployment_ready",
        runtime="pytorch",
        target_classes=("weed",),
        artifacts=(ModelArtifactOption("best", checkpoint, True),),
    )


def _products(tmp_path: Path) -> tuple[SpatialProduct, SpatialProduct]:
    preview = tmp_path / "preview.png"
    ortho_preview = tmp_path / "orthomosaic.png"
    Image.new("RGB", (160, 90), (50, 130, 70)).save(preview)
    Image.new("RGB", (160, 90), (40, 110, 65)).save(ortho_preview)
    orthomosaic = tmp_path / "orthomosaic.tif"
    orthomosaic.write_bytes(b"test")
    metadata = GeoRasterMetadata(
        crs="EPSG:32648",
        transform=(0.02, 0.0, 500_000, 0.0, -0.02, 1_200_000),
        width=160,
        height=90,
        bounds=(500_000, 1_199_998.2, 500_003.2, 1_200_000),
        resolution=(0.02, 0.02),
    )
    return (
        SpatialProduct(
            product_id="preview-ui",
            mission_id="mission-ui-spatial",
            kind=SpatialProductKind.PREVIEW_MOSAIC,
            accuracy=SpatialAccuracy.PREVIEW_ONLY,
            path=preview,
            preview_path=preview,
            created_at=NOW,
            provenance={"layout": "lane_sequence_contact_sheet"},
        ),
        SpatialProduct(
            product_id="orthomosaic-ui",
            mission_id="mission-ui-spatial",
            kind=SpatialProductKind.ORTHOMOSAIC,
            accuracy=SpatialAccuracy.GEOREFERENCED,
            path=orthomosaic,
            preview_path=ortho_preview,
            created_at=NOW,
            raster=metadata,
            provenance={"engine": "NodeODM (Docker local)", "task_id": "task-1"},
        ),
    )


def _completed_job(tmp_path: Path, orthomosaic: Path) -> AnalysisJob:
    config = AnalysisJobConfig(
        mission_id="mission-ui-spatial",
        model_id="semantic-v72",
        artifact_role="best",
        registry_path=tmp_path / "registry.json",
        inputs=(AnalysisInput("orthomosaic-ui", orthomosaic),),
        output_root=tmp_path / "results",
    )
    result = AnalysisResult(
        artifact_dir=tmp_path / "artifacts",
        manifest_sha256="a" * 64,
        image_summaries=({"image_id": "orthomosaic-ui"},),
        provenance={},
    )
    return AnalysisJob("job-ui-spatial", config).start().complete(result)


def test_spatial_workspace_distinguishes_preview_and_georeferenced_product(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    preview, orthomosaic = _products(tmp_path)
    job = _completed_job(tmp_path, orthomosaic.path)
    workspace = SpatialWorkspace(
        mission_id="mission-ui-spatial",
        image_count=30,
        geotagged_image_count=30,
        altitude_image_count=30,
        products=(preview, orthomosaic),
        orthomosaic_engine_configured=True,
    )
    page = SpatialWorkspacePage()
    qtbot.addWidget(page)
    page.resize(1200, 760)
    page.set_workspace(
        workspace,
        (_model(tmp_path),),
        ((orthomosaic.product_id, (job,)),),
    )

    page.product_table.selectRow(0)
    assert page.accuracy_value.text() == "Ảnh xem nhanh, không có tọa độ"
    assert not page.run_button.isEnabled()
    assert not page.export_button.isEnabled()

    page.product_table.selectRow(1)
    assert page.accuracy_value.text() == "Đã định vị địa lý"
    assert page.crs_value.text() == "EPSG:32648"
    assert page.run_button.isEnabled()
    assert page.export_button.isEnabled()
    assert page.nodeodm_button.isEnabled()
    assert not page._pixmap_item.pixmap().isNull()
    assert page.map_preview.open_button.isEnabled()
    page.show()
    qtbot.mouseClick(page.map_preview.open_button, Qt.MouseButton.LeftButton)
    assert page._map_dialog is not None
    assert page._map_dialog.isVisible()
    page._map_dialog.close()


def test_region_panel_rolls_closed_and_releases_space_to_viewer(
    qtbot: QtBot,
) -> None:
    page = SpatialWorkspacePage()
    qtbot.addWidget(page)
    page.resize(1200, 760)
    page.show()
    qtbot.wait(50)
    page._set_region_expanded(True)

    expanded_sizes = page.center_splitter.sizes()
    page._toggle_region_panel()
    qtbot.waitUntil(lambda: not page.region_table.isVisible(), timeout=1000)
    collapsed_sizes = page.center_splitter.sizes()

    assert collapsed_sizes[1] == 42
    assert collapsed_sizes[0] > expanded_sizes[0]

    page._toggle_region_panel()
    qtbot.waitUntil(lambda: page.center_splitter.sizes()[1] >= 120, timeout=1000)
    assert page.region_table.isVisible()


def test_field_map_is_a_separate_panel_below_inspector(
    qtbot: QtBot,
) -> None:
    page = SpatialWorkspacePage()
    qtbot.addWidget(page)
    page.resize(1440, 900)
    page.show()
    qtbot.wait(50)

    assert not page.inspector_panel.isAncestorOf(page.map_preview)
    assert page.field_map_panel.parentWidget() is page.right_column
    assert (
        page.field_map_panel.geometry().top()
        - page.inspector_panel.geometry().bottom()
        - 1
        == 8
    )
    assert (
        page.right_column.contentsRect().bottom()
        - page.field_map_panel.geometry().bottom()
        <= 1
    )


def test_fallback_field_map_draws_footprint_on_satellite_imagery(tmp_path: Path) -> None:
    _, orthomosaic = _products(tmp_path)

    html = build_leaflet_html(orthomosaic, interactive=True)
    preview_html = build_leaflet_html(orthomosaic, interactive=False)

    assert "World_Imagery" in html
    assert "L.polygon" in html
    assert "L.circleMarker" in html
    assert "L.imageOverlay" in html
    assert "L.control.layers" in html
    assert "Ranh giới ảnh ghép" in html
    assert QUrl.fromLocalFile(str(orthomosaic.preview_path.resolve())).toString() in html
    assert "font-size: 11px" in html
    assert "font-size: 8px" in preview_html


def test_google_field_map_uses_hybrid_imagery_and_polygon(tmp_path: Path) -> None:
    _, orthomosaic = _products(tmp_path)

    html = build_field_map_html(
        orthomosaic,
        interactive=True,
        google_api_key="unit-test-key",
    )

    assert "maps.googleapis.com/maps/api/js" in html
    assert "mapTypeId: 'hybrid'" in html
    assert "new google.maps.Polygon" in html
    assert "new google.maps.Circle" in html
    assert "new google.maps.GroundOverlay" in html
    assert "Ranh giới ảnh ghép" in html


def test_spatial_workspace_emits_semantic_analysis_and_heatmap_requests(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    _, orthomosaic = _products(tmp_path)
    job = _completed_job(tmp_path, orthomosaic.path)
    page = SpatialWorkspacePage()
    qtbot.addWidget(page)
    page.set_workspace(
        SpatialWorkspace(
            "mission-ui-spatial",
            3,
            3,
            3,
            (orthomosaic,),
            False,
        ),
        (_model(tmp_path),),
        ((orthomosaic.product_id, (job,)),),
    )

    with qtbot.waitSignal(page.analyzeRequested, timeout=1000) as analysis_signal:
        qtbot.mouseClick(page.run_button, Qt.MouseButton.LeftButton)
    product_id, request = analysis_signal.args
    assert product_id == "orthomosaic-ui"
    assert isinstance(request, AnalysisRequest)
    assert request.model_id == "semantic-v72"
    assert request.weed_threshold == 0.5

    with qtbot.waitSignal(page.heatmapRequested, timeout=1000) as heatmap_signal:
        qtbot.mouseClick(page.export_button, Qt.MouseButton.LeftButton)
    assert heatmap_signal.args == ["orthomosaic-ui", "job-ui-spatial"]


def test_spatial_viewer_measures_distance_and_area_above_map_layers(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    _, orthomosaic = _products(tmp_path)
    page = SpatialWorkspacePage()
    qtbot.addWidget(page)
    page.resize(1200, 760)
    page.show()
    page.set_workspace(
        SpatialWorkspace("mission-ui-spatial", 3, 3, 3, (orthomosaic,), False),
        (_model(tmp_path),),
        (),
    )
    viewport = page.view.viewport()
    center = viewport.rect().center()

    distance_button = next(
        button
        for button in page.tool_group.buttons()
        if button.property("viewerTool") == "distance"
    )
    qtbot.mouseClick(distance_button, Qt.MouseButton.LeftButton)
    assert page.view.tool == "distance"
    assert "hai điểm" in page.coordinate_value.text()
    qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=center)
    qtbot.mouseClick(
        viewport,
        Qt.MouseButton.LeftButton,
        pos=center + QPoint(40, 20),
    )
    assert page.coordinate_value.text().startswith("Khoảng cách")
    lines = [item for item in page._scene.items() if isinstance(item, QGraphicsLineItem)]
    assert len(lines) == 1
    assert lines[0].zValue() > page._overlay_item.zValue()

    area_button = next(
        button for button in page.tool_group.buttons() if button.property("viewerTool") == "area"
    )
    qtbot.mouseClick(area_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=center)
    qtbot.mouseClick(
        viewport,
        Qt.MouseButton.LeftButton,
        pos=center + QPoint(45, 10),
    )
    qtbot.mouseDClick(
        viewport,
        Qt.MouseButton.LeftButton,
        pos=center + QPoint(15, 45),
    )
    assert page.coordinate_value.text().startswith("Diện tích")
    polygons = [item for item in page._scene.items() if isinstance(item, QGraphicsPolygonItem)]
    assert len(polygons) == 1
    assert polygons[0].zValue() > page._region_item.zValue()


def test_nodeodm_run_is_available_without_endpoint_configuration(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    page = SpatialWorkspacePage()
    qtbot.addWidget(page)
    page.set_workspace(
        SpatialWorkspace(
            "mission-ui-spatial",
            3,
            3,
            3,
            (),
            True,
            "NodeODM (Docker local)",
            "http://127.0.0.1:3000",
        ),
        (_model(tmp_path),),
        (),
    )

    assert page.nodeodm_button.isEnabled()
    assert "tự kiểm tra Docker" in page.nodeodm_button.toolTip()


def test_semantic_mask_provides_georeferenced_weed_regions(tmp_path: Path) -> None:
    _, orthomosaic = _products(tmp_path)
    artifact_dir = tmp_path / "region-artifacts"
    artifact_dir.mkdir()
    mask = Image.new("L", (160, 90), 0)
    for x in range(10, 20):
        for y in range(15, 25):
            mask.putpixel((x, y), 255)
    mask.save(artifact_dir / "orthomosaic-ui.weed_mask.png")
    config = AnalysisJobConfig(
        mission_id="mission-ui-spatial",
        model_id="semantic-v72",
        artifact_role="best",
        registry_path=tmp_path / "registry.json",
        inputs=(AnalysisInput("orthomosaic-ui", orthomosaic.path),),
        output_root=tmp_path / "results",
    )
    result = AnalysisResult(
        artifact_dir=artifact_dir,
        manifest_sha256="b" * 64,
        image_summaries=(
            {
                "image_id": "orthomosaic-ui",
                "source_path": str(orthomosaic.path),
                "weed_pixels": 100,
                "weed_coverage_percent": 100 / (160 * 90) * 100,
            },
        ),
        provenance={},
    )
    job = AnalysisJob("job-regions", config).start().complete(result)

    regions, weed_pixels, coverage = extract_weed_regions(orthomosaic, (job,), min_area_m2=0.0)

    assert len(regions) == 1
    assert weed_pixels == 100
    assert coverage is not None
    assert regions[0].area_m2 == 0.04
    assert regions[0].centroid_map is not None


def test_spatial_controller_runs_action_off_ui_thread(qtbot: QtBot) -> None:
    controller = SpatialTaskController()
    progress_values: list[tuple[float, str]] = []
    controller.progress.connect(lambda value, status: progress_values.append((value, status)))

    def action(progress: ProgressCallback) -> str:
        progress(0.5, "processing")
        return "done"

    with qtbot.waitSignal(controller.completed, timeout=2000) as signal:
        assert controller.start("test", action)

    assert signal.args == ["test", "done"]
    assert progress_values == [(0.5, "processing")]
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=1000)


def test_spatial_inspector_shows_layers_and_information_together(qtbot: QtBot) -> None:
    page = SpatialWorkspacePage()
    qtbot.addWidget(page)

    assert not page.inspector_panel.findChildren(QTabWidget)
    assert page.map_layer_check.parentWidget() is not None
    assert page.accuracy_value.parentWidget() is not None
    assert page.region_area_value.parentWidget() is not None
