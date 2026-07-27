from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import pytest
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import from_origin

from uav_crop_analysis.adapters import (
    LanePreviewMosaicBuilder,
    NodeOdmOrthomosaicEngine,
    RasterioGeoRaster,
    SQLiteMissionRepository,
    SQLiteSpatialProductRepository,
)
from uav_crop_analysis.application import AnalysisRequest
from uav_crop_analysis.domain import DroneId, GeoPoint, ImageAsset, SurveyMission
from uav_crop_analysis.errors import GeospatialError
from uav_crop_analysis.geospatial import (
    SpatialAccuracy,
    SpatialProductKind,
    SpatialWorkspaceService,
)
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    AnalysisResult,
)


NOW = datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)


def _mission_data(
    root: Path,
) -> tuple[SQLiteMissionRepository, SurveyMission, tuple[ImageAsset, ...]]:
    mission = SurveyMission.create(
        "mission-spatial",
        "Khảo sát không gian",
        ("drone-01", "drone-02", "drone-03"),
        created_at=NOW,
    )
    assets = []
    for lane, assignment in enumerate(mission.assignments):
        path = root / assignment.drone_id.value / "image-001.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 48), (40 + lane * 60, 130, 70)).save(path)
        assets.append(
            ImageAsset(
                asset_id=f"{assignment.drone_id.value}-001",
                mission_id=mission.mission_id,
                drone_id=DroneId(assignment.drone_id.value),
                source_path=path,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                size_bytes=path.stat().st_size,
                captured_at=NOW,
                width_px=64,
                height_px=48,
                sequence_index=0,
                position=GeoPoint(10.75 + lane * 0.00001, 106.67),
                relative_altitude_m=10.0,
            )
        )
    repository = SQLiteMissionRepository(root / "app.db")
    repository.save_bundle(mission, (), tuple(assets), ())
    return repository, mission, tuple(assets)


def _write_geotiff(path: Path, *, georeferenced: bool = True) -> None:
    transform = from_origin(500_000, 1_200_000, 0.02, 0.02)
    profile: dict[str, Any] = {
        "driver": "GTiff",
        "height": 48,
        "width": 64,
        "count": 3,
        "dtype": "uint8",
        "transform": transform if georeferenced else rasterio.Affine.identity(),
    }
    if georeferenced:
        profile["crs"] = "EPSG:32648"
    data = np.zeros((3, 48, 64), dtype=np.uint8)
    data[0] = 50
    data[1] = 130
    data[2] = 70
    with rasterio.open(path, "w", **profile) as target:
        target.write(data)


class _FakeAnalysis:
    def __init__(self) -> None:
        self.jobs: tuple[AnalysisJob, ...] = ()
        self.submitted: tuple[AnalysisInput, ...] = ()

    def submit_inputs(
        self,
        request: AnalysisRequest,
        inputs: tuple[AnalysisInput, ...],
    ) -> AnalysisJob:
        self.submitted = inputs
        return _completed_job(
            inputs[0].source_path,
            Path("results"),
            image_id=inputs[0].image_id,
        )

    def list_jobs(self, mission_id: str) -> tuple[AnalysisJob, ...]:
        return tuple(job for job in self.jobs if job.config.mission_id == mission_id)


def _completed_job(
    orthomosaic: Path,
    artifact_dir: Path,
    *,
    image_id: str,
) -> AnalysisJob:
    config = AnalysisJobConfig(
        mission_id="mission-spatial",
        model_id="semantic-v72",
        artifact_role="best",
        registry_path=Path("registry.json"),
        inputs=(AnalysisInput(image_id, orthomosaic),),
        output_root=artifact_dir.parent,
        weed_threshold=0.55,
    )
    result = AnalysisResult(
        artifact_dir=artifact_dir,
        manifest_sha256="a" * 64,
        image_summaries=(
            {
                "image_id": image_id,
                "weed_coverage_percent": 25.0,
            },
        ),
        provenance={"runtime": "test"},
    )
    return AnalysisJob("job-spatial", config).start().complete(result)


def _service(
    root: Path,
    *,
    analysis: _FakeAnalysis | None = None,
) -> tuple[SpatialWorkspaceService, SurveyMission]:
    missions, mission, _ = _mission_data(root)
    service = SpatialWorkspaceService(
        missions,
        SQLiteSpatialProductRepository(root / "app.db"),
        RasterioGeoRaster(),
        LanePreviewMosaicBuilder(),
        root / "spatial",
        analysis=analysis,  # type: ignore[arg-type]
    )
    return service, mission


def test_rasterio_adapter_reads_crs_transform_and_rejects_plain_raster(
    tmp_path: Path,
) -> None:
    raster = RasterioGeoRaster()
    valid = tmp_path / "orthomosaic.tif"
    invalid = tmp_path / "plain.tif"
    _write_geotiff(valid)
    with pytest.warns(NotGeoreferencedWarning):
        _write_geotiff(invalid, georeferenced=False)

    metadata = raster.inspect(valid)

    assert metadata.crs == "EPSG:32648"
    assert metadata.resolution == pytest.approx((0.02, 0.02))
    assert metadata.transform == pytest.approx((0.02, 0.0, 500_000, 0.0, -0.02, 1_200_000))
    with pytest.raises(GeospatialError, match="coordinate reference|identity"):
        raster.inspect(invalid)


def test_preview_is_explicitly_non_georeferenced_and_persisted(tmp_path: Path) -> None:
    service, mission = _service(tmp_path)

    product = service.build_preview(mission.mission_id.value)
    workspace = service.get_workspace(mission.mission_id.value)

    assert product.kind is SpatialProductKind.PREVIEW_MOSAIC
    assert product.accuracy is SpatialAccuracy.PREVIEW_ONLY
    assert product.raster is None
    assert product.preview_path.is_file()
    assert workspace is not None
    assert workspace.products == (product,)
    assert workspace.geospatial_ready


def test_imported_orthomosaic_is_managed_with_raster_metadata(tmp_path: Path) -> None:
    service, mission = _service(tmp_path)
    source = tmp_path / "source.tif"
    _write_geotiff(source)

    product = service.import_orthomosaic(mission.mission_id.value, source)

    assert product.kind is SpatialProductKind.ORTHOMOSAIC
    assert product.accuracy is SpatialAccuracy.GEOREFERENCED
    assert product.raster is not None
    assert product.raster.crs == "EPSG:32648"
    assert product.path != source.resolve()
    assert product.path.is_file()
    assert product.preview_path.is_file()
    assert product.provenance["engine"] == "external_import"


def test_submit_and_export_heatmap_preserve_orthomosaic_grid(tmp_path: Path) -> None:
    analysis = _FakeAnalysis()
    service, mission = _service(tmp_path, analysis=analysis)
    source = tmp_path / "source.tif"
    _write_geotiff(source)
    orthomosaic = service.import_orthomosaic(mission.mission_id.value, source)
    request = AnalysisRequest(
        mission_id=mission.mission_id.value,
        model_id="semantic-v72",
        artifact_role="best",
    )

    submitted = service.submit_orthomosaic_analysis(orthomosaic.product_id, request)
    assert analysis.submitted[0].source_path == orthomosaic.path

    image_id = submitted.config.inputs[0].image_id
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    probability = np.linspace(0, 1, 48 * 64, dtype=np.float32).reshape(48, 64)
    np.save(artifact_dir / f"{image_id}.weed_probability.npy", probability)
    Image.fromarray((probability >= 0.55).astype(np.uint8) * 255).save(
        artifact_dir / f"{image_id}.weed_mask.png"
    )
    analysis.jobs = (
        _completed_job(orthomosaic.path, artifact_dir, image_id=image_id),
    )

    heatmap = service.export_weed_heatmap(orthomosaic.product_id, "job-spatial")

    assert heatmap.kind is SpatialProductKind.WEED_HEATMAP
    assert heatmap.source_product_id == orthomosaic.product_id
    assert heatmap.source_job_id == "job-spatial"
    assert heatmap.raster is not None and orthomosaic.raster is not None
    assert heatmap.raster.crs == orthomosaic.raster.crs
    assert heatmap.raster.transform == orthomosaic.raster.transform
    assert heatmap.raster.width == orthomosaic.raster.width
    assert heatmap.raster.height == orthomosaic.raster.height
    assert heatmap.preview_path.is_file()
    mask_path = Path(str(heatmap.provenance["mask_geotiff"]))
    quality_path = Path(str(heatmap.provenance["quality_geotiff"]))
    geojson_path = Path(str(heatmap.provenance["risk_geojson"]))
    with rasterio.open(mask_path) as mask_dataset:
        assert mask_dataset.crs.to_string() == "EPSG:32648"
        assert mask_dataset.transform == from_origin(500_000, 1_200_000, 0.02, 0.02)
    with rasterio.open(quality_path) as quality_dataset:
        assert np.all(quality_dataset.read(1) == 1)
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    assert geojson["type"] == "FeatureCollection"
    assert geojson["uav_crop_analysis"]["coordinates"] == "EPSG:4326"
    assert geojson["features"][0]["properties"]["class"] == "weed"
    assert geojson["features"][0]["properties"]["threshold"] == 0.55


def test_nodeodm_adapter_reports_progress_and_locates_orthophoto(tmp_path: Path) -> None:
    _, _, assets = _mission_data(tmp_path)
    calls: list[tuple[float, str]] = []

    class Task:
        uuid = "task-123"

        def wait_for_completion(self, status_callback: Any) -> None:
            status_callback(type("Info", (), {"progress": 60, "status": "running"})())

        def download_assets(self, destination: str) -> str:
            root = Path(destination) / "task-123"
            root.mkdir(parents=True)
            _write_geotiff(root / "odm_orthophoto.tif")
            return str(root)

    class Node:
        def create_task(self, files: list[str], options: object, **kwargs: Any) -> Task:
            kwargs["progress_callback"](20)
            assert len(files) == 3
            return Task()

    engine = NodeOdmOrthomosaicEngine(
        "http://localhost:3000?token=secret",
        node_factory=lambda url, timeout: Node(),
    )

    output, provenance = engine.create(
        "mission-spatial",
        tuple(asset.source_path for asset in assets),
        tmp_path / "odm-output",
        progress=lambda value, status: calls.append((value, status)),
    )

    assert output.name == "odm_orthophoto.tif"
    assert calls == [(0.2, "upload"), (0.6, "running"), (1.0, "downloaded")]
    assert provenance["task_id"] == "task-123"
    assert provenance["node_url"] == "http://localhost:3000"
    assert "secret" not in str(provenance)


def test_nodeodm_provenance_removes_basic_auth_credentials() -> None:
    engine = NodeOdmOrthomosaicEngine("https://user:password@example.test:443/api")

    assert engine.public_node_url == "https://example.test:443/api"
