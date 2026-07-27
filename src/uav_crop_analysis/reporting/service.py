"""Build mission-wide report read models from persisted source-of-truth records."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path

from uav_crop_analysis.application import MissionDataRepository, MissionDataWorkspaceService
from uav_crop_analysis.domain import CameraProfile
from uav_crop_analysis.errors import ReportError
from uav_crop_analysis.geospatial import SpatialProductRepository
from uav_crop_analysis.jobs import AnalysisJob, AnalysisJobRepository, JobStatus
from uav_crop_analysis.reporting.models import (
    REPORT_SCHEMA_VERSION,
    REPORT_TEMPLATE_VERSION,
    MissionReport,
    ReportAnalysis,
    ReportCamera,
    ReportDroneSummary,
    ReportExport,
    ReportImageRecord,
    ReportSpatialProduct,
)
from uav_crop_analysis.reporting.ports import MissionReportExporter, ReportModelCatalog


@dataclass(frozen=True, slots=True)
class _ImageAnalysis:
    job_id: str
    model_id: str
    model_version: str | None
    weed_coverage_percent: float


class MissionReportService:
    def __init__(
        self,
        missions: MissionDataRepository,
        jobs: AnalysisJobRepository,
        products: SpatialProductRepository,
        catalog: ReportModelCatalog,
        exporter: MissionReportExporter,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._missions = missions
        self._jobs = jobs
        self._products = products
        self._catalog = catalog
        self._exporter = exporter
        self._now = now or (lambda: datetime.now(timezone.utc))

    def build(self, mission_id: str) -> MissionReport:
        workspace = MissionDataWorkspaceService(self._missions).get_data(mission_id)
        if workspace is None:
            raise ReportError(f"mission does not exist: {mission_id}")
        jobs = self._jobs.list_for_mission(mission_id)
        model_versions = self._model_versions(jobs)
        image_analyses = self._latest_image_analyses(jobs, model_versions)
        camera_by_id = {camera.profile_id: camera for camera in workspace.cameras}
        cameras = tuple(
            _camera_report(
                camera,
                workspace.mission.flight_profile.altitude_m,
            )
            for camera in workspace.cameras
        )
        image_issues = _issues_by_image(workspace.issues)
        lane_by_drone = {
            item.drone_id: item.lane_index for item in workspace.drones
        }
        images = tuple(
            _image_report(
                image,
                mission_id,
                lane_by_drone[image.drone_id],
                image_issues.get(image.image_id, ((), "valid"))[0],
                image_issues.get(image.image_id, ((), "valid"))[1],
                image_analyses.get(image.image_id),
                (
                    _estimated_gsd_cm_px(
                        camera_by_id[image.camera_profile_id],
                        image.relative_altitude_m
                        or workspace.mission.flight_profile.altitude_m,
                    )
                    if image.camera_profile_id is not None
                    and image.camera_profile_id in camera_by_id
                    else None
                ),
            )
            for drone in workspace.drones
            for image in drone.images
        )
        images_by_drone = {
            drone.drone_id: tuple(
                image for image in images if image.drone_id == drone.drone_id
            )
            for drone in workspace.drones
        }
        drones = tuple(
            _drone_report(drone, images_by_drone[drone.drone_id])
            for drone in workspace.drones
        )
        spatial = tuple(
            _spatial_report(product)
            for product in self._products.list_for_mission(mission_id)
        )
        mission = workspace.mission
        profile = mission.flight_profile
        report = MissionReport(
            schema_version=REPORT_SCHEMA_VERSION,
            template_version=REPORT_TEMPLATE_VERSION,
            generated_at=self._now(),
            mission_id=mission_id,
            mission_name=mission.name,
            mission_created_at=mission.created_at,
            drone_count=len(mission.assignments),
            altitude_m=profile.altitude_m,
            gimbal_pitch_deg=profile.gimbal_pitch_deg,
            forward_overlap=profile.forward_overlap,
            side_overlap=profile.side_overlap,
            capture_mode=profile.capture_mode.value,
            cameras=cameras,
            drones=drones,
            images=images,
            analyses=tuple(
                _analysis_report(job, model_versions.get(job.config.model_id))
                for job in jobs
            ),
            spatial_products=spatial,
            limitations=_limitations(cameras, jobs, spatial),
        )
        if report.drone_count != 3:
            raise ReportError("mission report requires exactly three drones")
        return report

    def export(self, mission_id: str, output_root: str | Path) -> ReportExport:
        return self._exporter.export(
            self.build(mission_id),
            Path(output_root).expanduser().resolve(),
        )

    def _model_versions(self, jobs: tuple[AnalysisJob, ...]) -> dict[str, str | None]:
        versions: dict[str, str | None] = {}
        for job in sorted(jobs, key=lambda item: item.updated_at, reverse=True):
            if job.config.model_id in versions:
                continue
            try:
                versions[job.config.model_id] = self._catalog.get(
                    job.config.model_id
                ).version
            except Exception:
                versions[job.config.model_id] = None
        return versions

    @staticmethod
    def _latest_image_analyses(
        jobs: tuple[AnalysisJob, ...],
        versions: dict[str, str | None],
    ) -> dict[str, _ImageAnalysis]:
        result: dict[str, _ImageAnalysis] = {}
        for job in jobs:
            if job.status is not JobStatus.COMPLETED or job.result is None:
                continue
            for summary in job.result.image_summaries:
                image_id = str(summary.get("image_id", ""))
                coverage = summary.get("weed_coverage_percent")
                if not image_id or image_id in result or not isinstance(coverage, (int, float)):
                    continue
                result[image_id] = _ImageAnalysis(
                    job_id=job.job_id,
                    model_id=job.config.model_id,
                    model_version=versions.get(job.config.model_id),
                    weed_coverage_percent=float(coverage),
                )
        return result


def _camera_report(camera: CameraProfile, altitude_m: float) -> ReportCamera:
    gsd = _estimated_gsd_cm_px(camera, altitude_m)
    return ReportCamera(
        profile_id=camera.profile_id,
        name=camera.name,
        make=camera.make,
        model=camera.model,
        image_width_px=camera.image_width_px,
        image_height_px=camera.image_height_px,
        horizontal_fov_deg=camera.horizontal_fov_deg,
        estimated_gsd_cm_px=gsd,
        gsd_method="altitude_horizontal_fov" if gsd is not None else "unavailable",
    )


def _estimated_gsd_cm_px(camera: CameraProfile, altitude_m: float) -> float | None:
    if camera.horizontal_fov_deg is None or camera.image_width_px is None:
        return None
    ground_width_m = 2.0 * altitude_m * math.tan(
        math.radians(camera.horizontal_fov_deg) / 2.0
    )
    return round(ground_width_m / camera.image_width_px * 100.0, 6)


def _issues_by_image(
    issues: tuple[object, ...],
) -> dict[str, tuple[tuple[str, ...], str]]:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for issue in issues:
        image_id = getattr(issue, "image_id", None)
        code = getattr(issue, "code", None)
        severity = str(getattr(issue, "severity", "warning"))
        if image_id and code:
            grouped.setdefault(str(image_id), []).append((str(code), severity))
    return {
        key: (
            tuple(sorted({code for code, _severity in values})),
            "error" if any(severity == "error" for _code, severity in values) else "warning",
        )
        for key, values in grouped.items()
    }


def _image_report(
    image: object,
    mission_id: str,
    lane_index: int,
    issue_codes: tuple[str, ...],
    quality_status: str,
    analysis: _ImageAnalysis | None,
    gsd_cm_px: float | None,
) -> ReportImageRecord:
    coverage = analysis.weed_coverage_percent if analysis else None
    width = int(getattr(image, "width_px"))
    height = int(getattr(image, "height_px"))
    weed_area = None
    if coverage is not None and gsd_cm_px is not None:
        pixel_area_m2 = (gsd_cm_px / 100.0) ** 2
        weed_area = round(width * height * pixel_area_m2 * coverage / 100.0, 6)
    return ReportImageRecord(
        mission_id=mission_id,
        drone_id=str(getattr(image, "drone_id")),
        lane_index=lane_index,
        image_id=str(getattr(image, "image_id")),
        sequence_index=int(getattr(image, "sequence_index")),
        captured_at=getattr(image, "captured_at"),
        source_path=Path(getattr(image, "source_path")),
        latitude=getattr(image, "latitude"),
        longitude=getattr(image, "longitude"),
        relative_altitude_m=getattr(image, "relative_altitude_m"),
        camera_profile_id=getattr(image, "camera_profile_id"),
        estimated_gsd_cm_px=gsd_cm_px,
        quality_status=quality_status,
        issue_codes=issue_codes,
        analysis_job_id=analysis.job_id if analysis else None,
        model_id=analysis.model_id if analysis else None,
        model_version=analysis.model_version if analysis else None,
        weed_coverage_percent=coverage,
        estimated_weed_area_m2=weed_area,
    )


def _drone_report(drone: object, images: tuple[ReportImageRecord, ...]) -> ReportDroneSummary:
    weed = [
        item.weed_coverage_percent
        for item in images
        if item.weed_coverage_percent is not None
    ]
    image_count = len(images)
    return ReportDroneSummary(
        drone_id=str(getattr(drone, "drone_id")),
        lane_index=int(getattr(drone, "lane_index")),
        image_count=image_count,
        valid_image_count=sum(item.quality_status == "valid" for item in images),
        issue_image_count=sum(item.quality_status != "valid" for item in images),
        analyzed_image_count=sum(item.analysis_job_id is not None for item in images),
        telemetry_count=int(getattr(drone, "telemetry_count")),
        gps_coverage=(
            sum(item.latitude is not None and item.longitude is not None for item in images)
            / image_count
            if image_count
            else 0.0
        ),
        altitude_coverage=(
            sum(item.relative_altitude_m is not None for item in images) / image_count
            if image_count
            else 0.0
        ),
        mean_weed_coverage_percent=(sum(weed) / len(weed) if weed else None),
    )


def _analysis_report(job: AnalysisJob, version: str | None) -> ReportAnalysis:
    return ReportAnalysis(
        job_id=job.job_id,
        status=job.status.value,
        model_id=job.config.model_id,
        model_version=version,
        artifact_role=job.config.artifact_role,
        image_count=len(job.config.inputs),
        weed_threshold=job.config.weed_threshold,
        updated_at=job.updated_at,
        manifest_sha256=(job.result.manifest_sha256 if job.result else None),
    )


def _spatial_report(product: object) -> ReportSpatialProduct:
    raster = getattr(product, "raster")
    return ReportSpatialProduct(
        product_id=str(getattr(product, "product_id")),
        kind=getattr(product, "kind").value,
        accuracy=getattr(product, "accuracy").value,
        path=Path(getattr(product, "path")),
        preview_path=Path(getattr(product, "preview_path")),
        crs=raster.crs if raster else None,
        resolution=raster.resolution if raster else None,
        bounds=raster.bounds if raster else None,
        source_product_id=getattr(product, "source_product_id"),
        source_job_id=getattr(product, "source_job_id"),
    )


def _limitations(
    cameras: tuple[ReportCamera, ...],
    jobs: tuple[AnalysisJob, ...],
    spatial: tuple[ReportSpatialProduct, ...],
) -> tuple[str, ...]:
    limitations = [
        "Weed là semantic coverage; báo cáo không đếm instance weed.",
        "Maize instance chưa có số liệu cho tới khi checkpoint instance được đăng ký.",
    ]
    if not cameras or any(camera.estimated_gsd_cm_px is None for camera in cameras):
        limitations.append(
            "Không thể ước tính GSD khi camera thiếu horizontal FOV hoặc chiều rộng ảnh."
        )
    else:
        limitations.append(
            "GSD và diện tích weed là giá trị ước tính từ độ cao ảnh/nhiệm vụ và horizontal FOV."
        )
    if not any(item.accuracy == "georeferenced" for item in spatial):
        limitations.append("Mission chưa có sản phẩm không gian georeferenced.")
    if not any(job.status is JobStatus.COMPLETED for job in jobs):
        limitations.append("Mission chưa có job AI hoàn thành để tổng hợp chỉ số theo ảnh.")
    return tuple(limitations)
