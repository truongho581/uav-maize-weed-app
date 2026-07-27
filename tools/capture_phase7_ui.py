"""Render deterministic Phase 7 spatial-workspace screenshots."""

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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    import numpy as np
    from PIL import Image
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from uav_crop_analysis.application import (
        AnalysisModelOption,
        AnalysisTask,
        ModelArtifactOption,
    )
    from uav_crop_analysis.geospatial import (
        GeoRasterMetadata,
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
    from uav_crop_analysis.ui.shell import MainWindow
    from uav_crop_analysis.ui.tokens import application_font, stylesheet
    from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel

    now = datetime(2026, 7, 27, 11, 0, tzinfo=timezone.utc)
    root = args.output.parent / ".phase7-fixtures"
    root.mkdir(parents=True, exist_ok=True)
    image_height, image_width = 620, 1100
    y, x = np.indices((image_height, image_width))
    field = np.empty((image_height, image_width, 3), dtype=np.uint8)
    field[..., 0] = 47 + ((x // 85) % 3) * 8
    field[..., 1] = 105 + ((y // 50) % 2) * 24
    field[..., 2] = 42 + ((x + y) % 24)
    weed = ((x - 420) ** 2 + (y - 250) ** 2 < 105**2) | (
        (x - 810) ** 2 + (y - 410) ** 2 < 72**2
    )
    field[weed] = (188, 62, 48)
    orthomosaic_preview = root / "orthomosaic-preview.png"
    heatmap_preview = root / "weed-heatmap-preview.png"
    Image.fromarray(field).save(orthomosaic_preview)
    heatmap = field.astype(np.float32)
    heatmap[weed] = heatmap[weed] * 0.35 + np.array((238, 196, 67)) * 0.65
    Image.fromarray(heatmap.clip(0, 255).astype(np.uint8)).save(heatmap_preview)
    orthomosaic_path = root / "orthomosaic.tif"
    probability_path = root / "weed-probability.tif"
    orthomosaic_path.write_bytes(b"fixture")
    probability_path.write_bytes(b"fixture")
    raster = GeoRasterMetadata(
        crs="EPSG:32648",
        transform=(0.02, 0.0, 500000.0, 0.0, -0.02, 1200000.0),
        width=1100,
        height=620,
        bounds=(500000.0, 1199987.6, 500022.0, 1200000.0),
        resolution=(0.02, 0.02),
    )
    orthomosaic = SpatialProduct(
        "orthomosaic-demo",
        "mission-2026-khu-a",
        SpatialProductKind.ORTHOMOSAIC,
        SpatialAccuracy.GEOREFERENCED,
        orthomosaic_path,
        orthomosaic_preview,
        now,
        raster,
        provenance={"engine": "NodeODM", "task_id": "task-20260727-01"},
    )
    heatmap_product = SpatialProduct(
        "heatmap-demo",
        "mission-2026-khu-a",
        SpatialProductKind.WEED_HEATMAP,
        SpatialAccuracy.GEOREFERENCED,
        probability_path,
        heatmap_preview,
        now,
        raster,
        orthomosaic.product_id,
        "job-semantic-004",
        {"model_id": "segformer-b0-v72-loso", "weed_threshold": 0.5},
    )
    checkpoint = root / "best.pth"
    checkpoint.write_bytes(b"checkpoint")
    model = AnalysisModelOption(
        "segformer-b0-v72-loso",
        "7.2-loso",
        "segformer_b0",
        AnalysisTask.SEMANTIC,
        "evaluation_only_loso",
        "pytorch",
        ("weed",),
        (ModelArtifactOption("best_test_D1_seed_42", checkpoint, True),),
    )
    job_config = AnalysisJobConfig(
        "mission-2026-khu-a",
        model.model_id,
        "best_test_D1_seed_42",
        root / "registry.json",
        (AnalysisInput("orthomosaic-demo", orthomosaic_path),),
        root / "results",
    )
    job = AnalysisJob("job-semantic-004", job_config).start().complete(
        AnalysisResult(
            root / "artifacts",
            "a" * 64,
            ({"image_id": "orthomosaic-demo", "weed_coverage_percent": 7.4},),
            {},
        )
    )
    workspace = SpatialWorkspace(
        "mission-2026-khu-a",
        360,
        360,
        360,
        (heatmap_product, orthomosaic),
        True,
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
    window.spatial_workspace.set_workspace(
        workspace,
        (model,),
        ((orthomosaic.product_id, (job,)),),
    )
    window.spatial_workspace.product_table.selectRow(1)
    window.pages.setCurrentWidget(window.spatial_workspace)
    window.spatial_nav.setEnabled(True)
    window._set_nav(window.spatial_nav)
    window.show()
    app.processEvents()
    QTest.qWait(100)
    window.spatial_workspace.fit_image()
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
