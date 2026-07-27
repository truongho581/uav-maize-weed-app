"""Stable exception taxonomy shared by public package boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class UAVCropAnalysisError(Exception):
    """Base class for errors callers may handle without parsing messages."""

    code = "uav_crop_analysis_error"

    def __init__(
        self,
        message: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = dict(context or {})


class DomainValidationError(UAVCropAnalysisError, ValueError):
    code = "domain_validation_error"


class MissionAlreadyExistsError(UAVCropAnalysisError):
    code = "mission_already_exists"


class MissionNotFoundError(UAVCropAnalysisError):
    code = "mission_not_found"


class ConfigurationError(UAVCropAnalysisError):
    code = "configuration_error"


class ModelManifestError(UAVCropAnalysisError, ValueError):
    code = "model_manifest_error"


class ModelUnavailableError(UAVCropAnalysisError):
    code = "model_unavailable"


class CheckpointIntegrityError(UAVCropAnalysisError):
    code = "checkpoint_integrity_error"


class InferenceInputError(UAVCropAnalysisError, ValueError):
    code = "inference_input_error"


class InferenceRuntimeError(UAVCropAnalysisError):
    code = "inference_runtime_error"


class JobStateError(UAVCropAnalysisError, ValueError):
    code = "job_state_error"


class JobNotFoundError(UAVCropAnalysisError):
    code = "job_not_found"


class PipelineExecutionError(UAVCropAnalysisError):
    code = "pipeline_execution_error"


class PipelineCancelledError(UAVCropAnalysisError):
    code = "pipeline_cancelled"


class GeospatialError(UAVCropAnalysisError):
    code = "geospatial_error"


class ReportError(UAVCropAnalysisError):
    code = "report_error"


class DependencyUnavailableError(UAVCropAnalysisError, ImportError):
    code = "dependency_unavailable"


class ImportDataError(UAVCropAnalysisError):
    code = "import_data_error"


class IntegrationError(UAVCropAnalysisError):
    code = "integration_error"


class ApiRequestError(UAVCropAnalysisError, ValueError):
    code = "api_request_error"


class PersistenceError(UAVCropAnalysisError):
    code = "persistence_error"


class MigrationError(PersistenceError):
    code = "migration_error"
