"""Model registry adapter for Analysis workspace catalog ports."""

from __future__ import annotations

from pathlib import Path

from uav_crop_analysis.application.analysis_workspace import (
    AnalysisModelOption,
    AnalysisTask,
    ModelArtifactOption,
)
from uav_crop_analysis.inference.registry import ModelRegistry, ModelTask


TASK_MAP = {
    AnalysisTask.SEMANTIC: ModelTask.SEMANTIC,
    AnalysisTask.MAIZE_INSTANCE: ModelTask.MAIZE_INSTANCE,
}


class RegistryModelCatalog:
    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = Path(registry_path).expanduser().resolve()

    def list_models(
        self, task: AnalysisTask | None = None
    ) -> tuple[AnalysisModelOption, ...]:
        registry = ModelRegistry.from_file(self.registry_path)
        registry_task = TASK_MAP[task] if task is not None else None
        options = tuple(
            _option(registry, manifest.model_id)
            for manifest in registry.list_models(registry_task)
        )
        return tuple(
            sorted(
                options,
                key=lambda item: (
                    not item.available,
                    "winner" not in item.status,
                    item.model_id,
                ),
            )
        )

    def get(self, model_id: str) -> AnalysisModelOption:
        registry = ModelRegistry.from_file(self.registry_path)
        return _option(registry, model_id)

    def ensure_artifact(self, model_id: str, artifact_role: str) -> None:
        ModelRegistry.from_file(self.registry_path).resolve(model_id, artifact_role)


def _option(registry: ModelRegistry, model_id: str) -> AnalysisModelOption:
    manifest = registry.get(model_id)
    artifacts = tuple(
        ModelArtifactOption(
            role=artifact.role,
            path=(registry.artifact_root / artifact.path).resolve(),
            available=(registry.artifact_root / artifact.path).resolve().is_file(),
        )
        for artifact in manifest.artifacts
    )
    return AnalysisModelOption(
        model_id=manifest.model_id,
        version=manifest.version,
        family=manifest.family,
        task=AnalysisTask(manifest.task.value),
        status=manifest.status,
        runtime=manifest.runtime.value,
        target_classes=manifest.target_classes,
        artifacts=artifacts,
    )
