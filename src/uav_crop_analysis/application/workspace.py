"""Read models for the desktop shell and host-application integrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from uav_crop_analysis.application.ports import MissionDataRepository
from uav_crop_analysis.application.services import (
    CreateSurveyMission,
    CreateSurveyMissionCommand,
)
from uav_crop_analysis.domain import (
    CameraProfile,
    DroneId,
    FlightProfile,
    MissionId,
    SurveyMission,
)
from uav_crop_analysis.geospatial import SpatialProductKind
from uav_crop_analysis.jobs.models import AnalysisJob, JobStatus
from uav_crop_analysis.jobs.repository import AnalysisJobRepository


class MissionDataStatus(str, Enum):
    EMPTY = "empty"
    INCOMPLETE = "incomplete"
    READY = "ready"


class MissionWorkflowStatus(str, Enum):
    CREATED = "created"
    PLANNED_NO_MEDIA = "planned_no_media"
    MEDIA_NO_PLAN = "media_no_plan"
    PLANNED_WITH_MEDIA = "planned_with_media"
    ANALYZED_NO_HEATMAP = "analyzed_no_heatmap"
    COMPLETE = "complete"


class MissionPlanLookup(Protocol):
    def get(self, mission_id: str) -> object | None: ...


class SpatialProductLookup(Protocol):
    def list_for_mission(self, mission_id: str) -> tuple[object, ...]: ...


@dataclass(frozen=True, slots=True)
class JobSummary:
    job_id: str
    status: JobStatus
    progress: float
    model_id: str
    updated_at: datetime
    error_message: str | None


@dataclass(frozen=True, slots=True)
class DroneCoverage:
    drone_id: str
    lane_index: int
    image_count: int
    telemetry_count: int
    gps_image_count: int
    altitude_image_count: int

    @property
    def gps_coverage(self) -> float:
        return self.gps_image_count / self.image_count if self.image_count else 0.0

    @property
    def altitude_coverage(self) -> float:
        return self.altitude_image_count / self.image_count if self.image_count else 0.0


@dataclass(frozen=True, slots=True)
class MissionSummary:
    mission_id: str
    name: str
    created_at: datetime
    image_count: int
    gps_coverage: float
    data_status: MissionDataStatus
    latest_job_status: JobStatus | None
    drone_count: int = 0
    workflow_status: MissionWorkflowStatus = MissionWorkflowStatus.CREATED


@dataclass(frozen=True, slots=True)
class MissionOverview:
    mission: SurveyMission
    data_status: MissionDataStatus
    image_count: int
    gps_coverage: float
    altitude_coverage: float
    camera_count: int
    drones: tuple[DroneCoverage, ...]
    recent_jobs: tuple[JobSummary, ...]

    @property
    def can_analyze(self) -> bool:
        return self.image_count > 0


class MissionWorkspaceService:
    """Build compact read models without exposing SQLite details to the UI."""

    def __init__(
        self,
        missions: MissionDataRepository,
        jobs: AnalysisJobRepository,
        plans: MissionPlanLookup | None = None,
        spatial_products: SpatialProductLookup | None = None,
        *,
        recent_job_limit: int = 5,
    ) -> None:
        self._missions = missions
        self._jobs = jobs
        self._plans = plans
        self._spatial_products = spatial_products
        self._recent_job_limit = recent_job_limit

    def create_mission(
        self,
        *,
        mission_id: str,
        name: str,
        drone_ids: tuple[str, ...],
        flight_profile: FlightProfile,
        camera_profile: CameraProfile | None = None,
    ) -> SurveyMission:
        mission = CreateSurveyMission(self._missions).execute(
            CreateSurveyMissionCommand(
                mission_id=mission_id,
                name=name,
                drone_ids=drone_ids,
                flight_profile=flight_profile,
            )
        )
        if camera_profile is not None:
            self._missions.save_camera_profile(
                mission.mission_id,
                camera_profile,
                tuple(DroneId(value) for value in drone_ids),
            )
        return mission

    def list_saved_camera_profiles(self) -> tuple[CameraProfile, ...]:
        return self._missions.list_saved_camera_profiles()

    def list_missions(self) -> tuple[MissionSummary, ...]:
        return tuple(self._summary(mission) for mission in self._missions.list_missions())

    def get_overview(self, mission_id: str) -> MissionOverview | None:
        mission = self._missions.get(MissionId(mission_id))
        if mission is None:
            return None

        images = self._missions.list_image_assets(mission.mission_id)
        telemetry = self._missions.list_telemetry_samples(mission.mission_id)
        cameras = self._missions.list_camera_profiles(mission.mission_id)
        jobs = self._jobs.list_for_mission(mission_id)
        drones = tuple(
            DroneCoverage(
                drone_id=assignment.drone_id.value,
                lane_index=assignment.lane_index,
                image_count=sum(
                    image.drone_id == assignment.drone_id for image in images
                ),
                telemetry_count=sum(
                    sample.drone_id == assignment.drone_id for sample in telemetry
                ),
                gps_image_count=sum(
                    image.drone_id == assignment.drone_id and image.position is not None
                    for image in images
                ),
                altitude_image_count=sum(
                    image.drone_id == assignment.drone_id
                    and (
                        image.relative_altitude_m is not None
                        or image.absolute_altitude_m is not None
                    )
                    for image in images
                ),
            )
            for assignment in sorted(mission.assignments, key=lambda item: item.lane_index)
        )
        gps_count = sum(image.position is not None for image in images)
        altitude_count = sum(
            image.relative_altitude_m is not None or image.absolute_altitude_m is not None
            for image in images
        )
        return MissionOverview(
            mission=mission,
            data_status=_data_status(drones),
            image_count=len(images),
            gps_coverage=_coverage(gps_count, len(images)),
            altitude_coverage=_coverage(altitude_count, len(images)),
            camera_count=len(cameras),
            drones=drones,
            recent_jobs=tuple(_job_summary(job) for job in jobs[: self._recent_job_limit]),
        )

    def _summary(self, mission: SurveyMission) -> MissionSummary:
        images = self._missions.list_image_assets(mission.mission_id)
        image_counts = {
            assignment.drone_id.value: sum(
                image.drone_id == assignment.drone_id for image in images
            )
            for assignment in mission.assignments
        }
        gps_count = sum(image.position is not None for image in images)
        drones = tuple(
            DroneCoverage(
                drone_id=assignment.drone_id.value,
                lane_index=assignment.lane_index,
                image_count=image_counts[assignment.drone_id.value],
                telemetry_count=0,
                gps_image_count=sum(
                    image.drone_id == assignment.drone_id and image.position is not None
                    for image in images
                ),
                altitude_image_count=sum(
                    image.drone_id == assignment.drone_id
                    and (
                        image.relative_altitude_m is not None
                        or image.absolute_altitude_m is not None
                    )
                    for image in images
                ),
            )
            for assignment in mission.assignments
        )
        jobs = self._jobs.list_for_mission(mission.mission_id.value)
        return MissionSummary(
            mission_id=mission.mission_id.value,
            name=mission.name,
            created_at=mission.created_at,
            image_count=len(images),
            gps_coverage=_coverage(gps_count, len(images)),
            data_status=_data_status(drones),
            latest_job_status=jobs[0].status if jobs else None,
            drone_count=len(mission.assignments),
            workflow_status=_workflow_status(
                has_plan=self._has_plan(mission.mission_id.value),
                image_count=len(images),
                jobs=jobs,
                has_heatmap=self._has_heatmap(mission.mission_id.value),
            ),
        )

    def _has_plan(self, mission_id: str) -> bool:
        if self._plans is None:
            return False
        try:
            return self._plans.get(mission_id) is not None
        except Exception:
            return False

    def _has_heatmap(self, mission_id: str) -> bool:
        if self._spatial_products is None:
            return False
        try:
            products = self._spatial_products.list_for_mission(mission_id)
        except Exception:
            return False
        return any(
            getattr(product, "kind", None) is SpatialProductKind.WEED_HEATMAP
            for product in products
        )


def _coverage(available: int, total: int) -> float:
    return available / total if total else 0.0


def _data_status(drones: tuple[DroneCoverage, ...]) -> MissionDataStatus:
    total_images = sum(drone.image_count for drone in drones)
    if total_images == 0:
        return MissionDataStatus.EMPTY
    if any(drone.image_count == 0 for drone in drones):
        return MissionDataStatus.INCOMPLETE
    if any(
        drone.gps_image_count < drone.image_count
        or drone.altitude_image_count < drone.image_count
        for drone in drones
    ):
        return MissionDataStatus.INCOMPLETE
    return MissionDataStatus.READY


def _job_summary(job: AnalysisJob) -> JobSummary:
    return JobSummary(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        model_id=job.config.model_id,
        updated_at=job.updated_at,
        error_message=job.error.message if job.error else None,
    )


def _workflow_status(
    *,
    has_plan: bool,
    image_count: int,
    jobs: tuple[AnalysisJob, ...],
    has_heatmap: bool,
) -> MissionWorkflowStatus:
    if has_heatmap:
        return MissionWorkflowStatus.COMPLETE
    if any(job.status is JobStatus.COMPLETED for job in jobs):
        return MissionWorkflowStatus.ANALYZED_NO_HEATMAP
    if image_count > 0 and has_plan:
        return MissionWorkflowStatus.PLANNED_WITH_MEDIA
    if image_count > 0:
        return MissionWorkflowStatus.MEDIA_NO_PLAN
    if has_plan:
        return MissionWorkflowStatus.PLANNED_NO_MEDIA
    return MissionWorkflowStatus.CREATED
