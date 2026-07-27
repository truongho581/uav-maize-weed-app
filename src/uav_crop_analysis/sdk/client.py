"""Public Python SDK facade over framework-neutral application services."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from uav_crop_analysis import __version__
from uav_crop_analysis.adapters import load_mission_manifest
from uav_crop_analysis.application import (
    AnalysisRequest,
    CreateSurveyMission,
    CreateSurveyMissionCommand,
)
from uav_crop_analysis.bootstrap import ApplicationRuntime, build_runtime
from uav_crop_analysis.domain import FlightProfile, MissionId
from uav_crop_analysis.errors import JobNotFoundError, MissionNotFoundError
from uav_crop_analysis.jobs import AnalysisJob
from uav_crop_analysis.integrations import (
    QGroundControlLogReader,
    QGroundControlPlanReader,
    QgcPlan,
    TelemetryLogImport,
)
from uav_crop_analysis.reporting import MissionReport, ReportExport
from uav_crop_analysis.sdk.models import (
    API_VERSION,
    SDK_SCHEMA_VERSION,
    Capabilities,
    CreateMissionRequest,
    DroneAssignmentView,
    ImportMissionView,
    JobView,
    MissionView,
    SpatialResultView,
    SubmitAnalysisRequest,
)


class UavCropAnalysis:
    """Stable SDK facade. Construction and all methods are independent of Qt."""

    version = __version__
    schema_version = SDK_SCHEMA_VERSION

    def __init__(self, runtime: ApplicationRuntime, *, owns_runtime: bool = False) -> None:
        self.runtime = runtime
        self._owns_runtime = owns_runtime

    @classmethod
    def open(
        cls,
        database_path: str | Path | None = None,
        *,
        registry_path: str | Path | None = None,
        nodeodm_url: str | None = None,
    ) -> UavCropAnalysis:
        return cls(
            build_runtime(
                database_path,
                registry_path=registry_path,
                nodeodm_url=nodeodm_url,
            ),
            owns_runtime=True,
        )

    def close(self) -> None:
        if self._owns_runtime:
            self.runtime.shutdown()
            self._owns_runtime = False

    def __enter__(self) -> UavCropAnalysis:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def capabilities(self) -> Capabilities:
        mavsdk_available = importlib.util.find_spec("mavsdk") is not None
        return Capabilities(
            sdk_schema_version=SDK_SCHEMA_VERSION,
            api_versions=(API_VERSION,),
            mission_management=True,
            analysis_jobs=True,
            report_export=True,
            geospatial_results=True,
            qgroundcontrol_plan_import=True,
            qgroundcontrol_log_import=True,
            mavsdk_available=mavsdk_available,
            drone_telemetry_read=mavsdk_available,
            drone_mission_read=mavsdk_available,
            drone_commands_enabled=False,
            nodeodm_configured=self.runtime.spatial_workspace.nodeodm_configured,
        )

    def create_mission(self, request: CreateMissionRequest) -> MissionView:
        mission = CreateSurveyMission(self.runtime.missions).execute(
            CreateSurveyMissionCommand(
                mission_id=request.mission_id,
                name=request.name,
                drone_ids=request.drone_ids,
                flight_profile=FlightProfile(
                    altitude_m=request.altitude_m,
                    gimbal_pitch_deg=request.gimbal_pitch_deg,
                    forward_overlap=request.forward_overlap,
                    side_overlap=request.side_overlap,
                ),
            )
        )
        return self._mission_view(mission.mission_id.value)

    def import_manifest(self, manifest_path: str | Path) -> ImportMissionView:
        report = self.runtime.mission_import.execute(
            load_mission_manifest(Path(manifest_path))
        )
        return ImportMissionView(
            mission_id=report.mission_id,
            persisted=report.persisted,
            image_count=len(report.images),
            telemetry_count=len(report.telemetry_samples),
            issue_count=len(report.issues),
            error_count=sum(issue.severity.value == "error" for issue in report.issues),
        )

    def list_missions(self) -> tuple[MissionView, ...]:
        return tuple(
            self._mission_view(summary.mission_id)
            for summary in self.runtime.mission_workspace.list_missions()
        )

    def get_mission(self, mission_id: str) -> MissionView:
        return self._mission_view(mission_id)

    def list_jobs(self, mission_id: str) -> tuple[JobView, ...]:
        self._require_mission(mission_id)
        return tuple(
            _job_view(job)
            for job in self.runtime.analysis_workspace.refresh_jobs(mission_id)
        )

    def get_job(self, job_id: str, *, poll: bool = True) -> JobView:
        job = self.runtime.jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(f"analysis job does not exist: {job_id}")
        if poll and job.status.value in {"running", "cancel_requested"}:
            job = self.runtime.job_service.poll(job_id)
        return _job_view(job)

    def submit_analysis(self, request: SubmitAnalysisRequest) -> JobView:
        job = self.runtime.analysis_workspace.submit(
            AnalysisRequest(
                mission_id=request.mission_id,
                model_id=request.model_id,
                artifact_role=request.artifact_role,
                device=request.device,
                tile_size=request.tile_size,
                overlap=request.overlap,
                weed_threshold=request.weed_threshold,
                selected_image_ids=request.selected_image_ids,
            ),
            auto_start=request.auto_start,
        )
        return _job_view(job)

    def cancel_job(self, job_id: str) -> JobView:
        return _job_view(self.runtime.analysis_workspace.cancel(job_id))

    def build_report(self, mission_id: str) -> MissionReport:
        self._require_mission(mission_id)
        return self.runtime.report_workspace.build(mission_id)

    def export_report(self, mission_id: str, output_root: str | Path) -> ReportExport:
        self._require_mission(mission_id)
        return self.runtime.report_workspace.export(mission_id, output_root)

    def list_results(self, mission_id: str) -> tuple[SpatialResultView, ...]:
        self._require_mission(mission_id)
        return tuple(
            SpatialResultView(
                product_id=item.product_id,
                mission_id=item.mission_id,
                kind=item.kind.value,
                accuracy=item.accuracy.value,
                path=item.path,
                preview_path=item.preview_path,
                created_at=item.created_at,
                crs=item.raster.crs if item.raster else None,
                source_product_id=item.source_product_id,
                source_job_id=item.source_job_id,
            )
            for item in self.runtime.spatial_products.list_for_mission(mission_id)
        )

    def inspect_qgc_plan(self, source_path: str | Path) -> QgcPlan:
        return QGroundControlPlanReader().read(source_path)

    def read_qgc_log(
        self,
        source_path: str | Path,
        *,
        mission_id: str,
        system_to_drone: dict[int, str],
    ) -> TelemetryLogImport:
        self._require_mission(mission_id)
        return QGroundControlLogReader().read(
            source_path,
            mission_id=mission_id,
            system_to_drone=system_to_drone,
        )

    def _mission_view(self, mission_id: str) -> MissionView:
        overview = self.runtime.mission_workspace.get_overview(mission_id)
        if overview is None:
            raise MissionNotFoundError(f"mission does not exist: {mission_id}")
        mission = overview.mission
        profile = mission.flight_profile
        return MissionView(
            mission_id=mission.mission_id.value,
            name=mission.name,
            created_at=mission.created_at,
            drones=tuple(
                DroneAssignmentView(item.drone_id.value, item.lane_index)
                for item in sorted(mission.assignments, key=lambda value: value.lane_index)
            ),
            altitude_m=profile.altitude_m,
            gimbal_pitch_deg=profile.gimbal_pitch_deg,
            forward_overlap=profile.forward_overlap,
            side_overlap=profile.side_overlap,
            capture_mode=profile.capture_mode.value,
            image_count=overview.image_count,
            gps_coverage=overview.gps_coverage,
            data_status=overview.data_status.value,
        )

    def _require_mission(self, mission_id: str) -> None:
        if self.runtime.missions.get(MissionId(mission_id)) is None:
            raise MissionNotFoundError(f"mission does not exist: {mission_id}")


def _job_view(job: AnalysisJob) -> JobView:
    return JobView(
        job_id=job.job_id,
        mission_id=job.config.mission_id,
        status=job.status.value,
        stage=job.stage.value,
        progress=job.progress,
        attempt=job.attempt,
        model_id=job.config.model_id,
        artifact_role=job.config.artifact_role,
        image_count=len(job.config.inputs),
        created_at=job.created_at,
        updated_at=job.updated_at,
        error_code=job.error.code if job.error else None,
        error_message=job.error.message if job.error else None,
        artifact_dir=job.result.artifact_dir if job.result else None,
        result_manifest_sha256=job.result.manifest_sha256 if job.result else None,
    )
