from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
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
from uav_crop_analysis.ui.views import SpatialWorkspacePage


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
            provenance={"engine": "NodeODM", "task_id": "task-1"},
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
        nodeodm_configured=True,
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
    assert "KHÔNG GEOREFERENCE" in page.accuracy_value.text()
    assert not page.run_button.isEnabled()
    assert not page.export_button.isEnabled()

    page.product_table.selectRow(1)
    assert page.accuracy_value.text() == "Có georeference"
    assert page.crs_value.text() == "EPSG:32648"
    assert page.run_button.isEnabled()
    assert page.export_button.isEnabled()
    assert page.nodeodm_button.isEnabled()
    assert not page._pixmap_item.pixmap().isNull()


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


def test_spatial_controller_runs_action_off_ui_thread(qtbot: QtBot) -> None:
    controller = SpatialTaskController()
    progress_values: list[tuple[float, str]] = []
    controller.progress.connect(
        lambda value, status: progress_values.append((value, status))
    )

    def action(progress: ProgressCallback) -> str:
        progress(0.5, "processing")
        return "done"

    with qtbot.waitSignal(controller.completed, timeout=2000) as signal:
        assert controller.start("test", action)

    assert signal.args == ["test", "done"]
    assert progress_values == [(0.5, "processing")]
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=1000)
