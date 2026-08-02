from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

from PIL import Image
import pytest

from uav_crop_analysis.adapters import (
    PortableMissionReportExporter,
    SQLiteAnalysisJobRepository,
    SQLiteMissionRepository,
    SQLiteSpatialProductRepository,
)
from uav_crop_analysis.application import (
    AnalysisModelOption,
    AnalysisTask,
    ModelArtifactOption,
)
from uav_crop_analysis.domain import (
    CameraProfile,
    DroneId,
    GeoPoint,
    ImageAsset,
    SurveyMission,
)
from uav_crop_analysis.errors import ReportError
from uav_crop_analysis.geospatial import (
    GeoRasterMetadata,
    SpatialAccuracy,
    SpatialProduct,
    SpatialProductKind,
)
from uav_crop_analysis.inference.registry import sha256_file
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    AnalysisResult,
    JobEventType,
)
from uav_crop_analysis.reporting import MissionReportService


NOW = datetime(2026, 7, 27, 13, 0, tzinfo=timezone.utc)


class _Catalog:
    def get(self, model_id: str) -> AnalysisModelOption:
        return AnalysisModelOption(
            model_id=model_id,
            version="7.2-maizemask-weedsgalore-seed42",
            family="segformer_b0",
            task=AnalysisTask.SEMANTIC,
            status="deployment_ready",
            runtime="pytorch",
            target_classes=("crop", "weed"),
            artifacts=(ModelArtifactOption("best", Path("model.pth"), True),),
        )


def _report_service(tmp_path: Path) -> tuple[MissionReportService, str]:
    database = tmp_path / "ứng dụng.db"
    missions = SQLiteMissionRepository(database)
    jobs = SQLiteAnalysisJobRepository(database)
    products = SQLiteSpatialProductRepository(database)
    mission = SurveyMission.create(
        "mission-khu-vực-a",
        "Khảo sát ngô khu vực A",
        ("drone-01", "drone-02", "drone-03"),
        created_at=NOW,
    )
    camera = CameraProfile(
        profile_id="camera-dji",
        name="DJI Mini 4K",
        make="DJI",
        model="FC7703",
        image_width_px=4000,
        image_height_px=3000,
        horizontal_fov_deg=82.0,
    )
    assets = []
    for lane, assignment in enumerate(mission.assignments):
        for sequence in range(2):
            if lane == 0 and sequence == 0:
                source = Path(r"C:\Dữ liệu UAV\ảnh 01.jpg")
                payload = b"windows-path"
            else:
                source = (
                    tmp_path
                    / "Dữ liệu ảnh"
                    / assignment.drone_id.value
                    / f"ảnh {sequence + 1}.jpg"
                )
                source.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (40, 30), (40 + lane * 30, 120, 60)).save(source)
                payload = source.read_bytes()
            assets.append(
                ImageAsset(
                    asset_id=f"{assignment.drone_id.value}-{sequence + 1:03d}",
                    mission_id=mission.mission_id,
                    drone_id=DroneId(assignment.drone_id.value),
                    source_path=source,
                    sha256=hashlib.sha256(
                        payload + f"{lane}-{sequence}".encode()
                    ).hexdigest(),
                    size_bytes=len(payload),
                    captured_at=NOW + timedelta(seconds=lane * 10 + sequence),
                    width_px=4000,
                    height_px=3000,
                    sequence_index=sequence,
                    position=(
                        None
                        if lane == 1 and sequence == 1
                        else GeoPoint(10.75 + lane * 0.0001, 106.67 + sequence * 0.0001)
                    ),
                    relative_altitude_m=10.0,
                    telemetry_offset_ms=2501 if lane == 2 and sequence == 0 else None,
                    camera_profile_id=camera.profile_id,
                )
            )
    missions.save_bundle(mission, (camera,), tuple(assets), ())

    artifact_dir = tmp_path / "kết quả" / "artifacts"
    artifact_dir.mkdir(parents=True)
    config = AnalysisJobConfig(
        mission_id=mission.mission_id.value,
        model_id="segformer-v72",
        artifact_role="best",
        registry_path=tmp_path / "model registry.json",
        inputs=tuple(AnalysisInput(asset.asset_id, asset.source_path) for asset in assets),
        output_root=tmp_path / "kết quả",
        weed_threshold=0.55,
    )
    summaries = tuple(
        {
            "image_id": asset.asset_id,
            "source_path": str(asset.source_path),
            "width": asset.width_px,
            "height": asset.height_px,
            "weed_coverage_percent": float(10 + index),
            "class_coverage_percent": {
                "background": 60.0 - index,
                "crop": 30.0,
                "weed": float(10 + index),
            },
            "class_pixels": {
                "background": 7200 - index * 120,
                "crop": 3600,
                "weed": 1200 + index * 120,
            },
            "tile_count": 2,
        }
        for index, asset in enumerate(assets)
    )
    result = AnalysisResult(
        artifact_dir=artifact_dir,
        manifest_sha256="a" * 64,
        image_summaries=summaries,
        provenance={"runtime": "test"},
    )
    completed = AnalysisJob("job-report", config).start().complete(result)
    jobs.add(completed, completed.event(JobEventType.COMPLETED))

    orthomosaic_preview = tmp_path / "ảnh ghép.png"
    Image.new("RGB", (120, 80), (80, 110, 70)).save(orthomosaic_preview)
    orthomosaic = tmp_path / "orthomosaic.tif"
    orthomosaic.write_bytes(b"orthomosaic-geotiff-fixture")
    products.add(
        SpatialProduct(
            product_id="orthomosaic-report",
            mission_id=mission.mission_id.value,
            kind=SpatialProductKind.ORTHOMOSAIC,
            accuracy=SpatialAccuracy.GEOREFERENCED,
            path=orthomosaic,
            preview_path=orthomosaic_preview,
            created_at=NOW,
            raster=GeoRasterMetadata(
                crs="EPSG:32648",
                transform=(0.02, 0.0, 500000.0, 0.0, -0.02, 1200000.0),
                width=120,
                height=80,
                bounds=(500000.0, 1199998.4, 500002.4, 1200000.0),
                resolution=(0.02, 0.02),
            ),
            provenance={"engine": "nodeodm"},
        )
    )
    preview = tmp_path / "heatmap cỏ dại.png"
    Image.new("RGB", (120, 80), (45, 130, 70)).save(preview)
    heatmap = tmp_path / "weed probability.tif"
    heatmap.write_bytes(b"geotiff-fixture")
    products.add(
        SpatialProduct(
            product_id="heatmap-report",
            mission_id=mission.mission_id.value,
            kind=SpatialProductKind.WEED_HEATMAP,
            accuracy=SpatialAccuracy.GEOREFERENCED,
            path=heatmap,
            preview_path=preview,
            created_at=NOW,
            raster=GeoRasterMetadata(
                crs="EPSG:32648",
                transform=(0.02, 0.0, 500000.0, 0.0, -0.02, 1200000.0),
                width=120,
                height=80,
                bounds=(500000.0, 1199998.4, 500002.4, 1200000.0),
                resolution=(0.02, 0.02),
            ),
            source_product_id="orthomosaic-report",
            source_job_id=completed.job_id,
            provenance={"model_id": "segformer-v72"},
        )
    )
    service = MissionReportService(
        missions,
        jobs,
        products,
        _Catalog(),
        PortableMissionReportExporter(),
        now=lambda: NOW,
    )
    return service, mission.mission_id.value


def test_report_contract_aggregates_mission_drone_ai_and_spatial_data(
    tmp_path: Path,
) -> None:
    service, mission_id = _report_service(tmp_path)

    report = service.build(mission_id)

    expected_gsd = 2 * 10 * math.tan(math.radians(82) / 2) / 4000 * 100
    assert report.schema_version == 1
    assert report.template_version == "1.0"
    assert report.mission_name == "Khảo sát ngô khu vực A"
    assert report.drone_count == 3
    assert report.image_count == 6
    assert report.analyzed_image_count == 6
    assert report.issue_image_count == 3
    assert report.mean_weed_coverage_percent == pytest.approx(12.5)
    assert report.mean_crop_coverage_percent == pytest.approx(30.0)
    assert report.cameras[0].estimated_gsd_cm_px == pytest.approx(expected_gsd)
    assert report.cameras[0].gsd_method == "altitude_horizontal_fov"
    assert report.images[0].model_version == "7.2-maizemask-weedsgalore-seed42"
    assert report.images[0].estimated_weed_area_m2 is not None
    assert report.images[0].maize_instance_count is None
    assert report.images[0].maize_status == "unavailable_instance_checkpoint"
    assert report.drones[1].gps_coverage == 0.5
    assert report.drones[2].issue_image_count == 1
    assert next(
        item for item in report.images if item.image_id == "drone-03-001"
    ).quality_status == "warning"
    assert report.spatial_products[0].crs == "EPSG:32648"
    assert any("cây ngô" in item.lower() for item in report.limitations)


def test_report_supports_single_drone_mission(tmp_path: Path) -> None:
    database = tmp_path / "single-drone.db"
    missions = SQLiteMissionRepository(database)
    mission = SurveyMission.create("mission-single", "Một drone", ("drone-01",))
    missions.add(mission)
    service = MissionReportService(
        missions,
        SQLiteAnalysisJobRepository(database),
        SQLiteSpatialProductRepository(database),
        _Catalog(),
        PortableMissionReportExporter(),
        now=lambda: NOW,
    )

    report = service.build(mission.mission_id.value)
    exported = service.export(mission.mission_id.value, tmp_path / "reports")

    assert report.drone_count == 1
    assert [drone.drone_id for drone in report.drones] == ["drone-01"]
    assert "1 drone" in exported.report_html.read_text(encoding="utf-8")


def test_portable_export_is_versioned_unicode_safe_and_self_contained(
    tmp_path: Path,
) -> None:
    service, mission_id = _report_service(tmp_path)
    output_root = tmp_path / "Báo cáo xuất"

    exported = service.export(mission_id, output_root)
    second_export = service.export(mission_id, output_root)

    assert exported.directory.is_dir()
    assert second_export.directory != exported.directory
    assert second_export.directory.is_dir()
    assert all(
        path.is_file()
        for path in (
            exported.report_json,
            exported.image_csv,
            exported.report_html,
            exported.manifest_json,
        )
    )
    payload = json.loads(exported.report_json.read_text(encoding="utf-8"))
    assert set(payload) == {
        "schema_version",
        "template_version",
        "generated_at",
        "mission_id",
        "mission_name",
        "mission_created_at",
        "drone_count",
        "altitude_m",
        "gimbal_pitch_deg",
        "forward_overlap",
        "side_overlap",
        "capture_mode",
        "cameras",
        "drones",
        "images",
        "analyses",
        "spatial_products",
        "limitations",
        "summary",
    }
    assert payload["schema_version"] == 1
    assert payload["summary"]["analyzed_image_count"] == 6
    assert payload["summary"]["mean_crop_coverage_percent"] == pytest.approx(30.0)
    with exported.image_csv.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert rows[0]["mission_id"] == mission_id
    assert rows[0]["source_path"] == r"C:\Dữ liệu UAV\ảnh 01.jpg"
    assert rows[0]["maize_status"] == "unavailable_instance_checkpoint"
    html = exported.report_html.read_text(encoding="utf-8")
    assert "Khảo sát ngô khu vực A" in html
    assert "data:image/png;base64," in html
    assert "Ảnh ghép GeoTIFF" in html
    assert "Heatmap cỏ dại" in html
    assert (exported.directory / "maps" / "orthomosaic.tif").is_file()
    assert (exported.directory / "maps" / "weed-heatmap.tif").is_file()
    assert "https://" not in html
    manifest = json.loads(exported.manifest_json.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    for item in manifest["files"]:
        assert sha256_file(exported.directory / item["path"]) == item["sha256"]


def test_report_rejects_unknown_mission(tmp_path: Path) -> None:
    service, _ = _report_service(tmp_path)

    with pytest.raises(ReportError, match="does not exist"):
        service.build("missing-mission")
