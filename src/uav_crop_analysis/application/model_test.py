"""Independent image and video checks for registered analysis models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from uav_crop_analysis.application.analysis_workspace import (
    AnalysisModelCatalog,
    AnalysisModelOption,
    AnalysisTask,
)
from uav_crop_analysis.errors import InferenceInputError
from uav_crop_analysis.inference import ModelRegistry, ModelTask, SegmenterFactory
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    InstanceTilePipeline,
    JobStage,
    SemanticTilePipeline,
)


ProgressCallback = Callable[[float, str], None]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


@dataclass(frozen=True, slots=True)
class ModelTestRequest:
    source_path: Path
    model_id: str
    artifact_role: str
    device: str = "cpu"
    tile_size: int = 640
    overlap: int = 64
    weed_threshold: float = 0.5


@dataclass(frozen=True, slots=True)
class ModelTestResult:
    job: AnalysisJob
    source_path: Path
    media_kind: str
    frame_count: int


class ModelTestService:
    """Run an ephemeral model check without requiring mission data."""

    def __init__(
        self,
        catalog: AnalysisModelCatalog,
        registry_path: str | Path,
        output_root: str | Path,
    ) -> None:
        self._catalog = catalog
        self.registry_path = Path(registry_path).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()

    def list_models(
        self,
        task: AnalysisTask | None = None,
    ) -> tuple[AnalysisModelOption, ...]:
        return self._catalog.list_models(task)

    def run(
        self,
        request: ModelTestRequest,
        progress: ProgressCallback,
    ) -> ModelTestResult:
        source = Path(request.source_path).expanduser().resolve()
        if not source.is_file():
            raise InferenceInputError(f"Tệp kiểm tra không tồn tại: {source}")
        self._catalog.ensure_artifact(request.model_id, request.artifact_role)
        test_id = f"model-test-{uuid4().hex}"
        progress(0.01, "Đang chuẩn bị dữ liệu kiểm tra...")
        inputs, media_kind = self._prepare_inputs(source, test_id, progress)
        config = AnalysisJobConfig(
            mission_id="model-test",
            model_id=request.model_id,
            artifact_role=request.artifact_role,
            registry_path=self.registry_path,
            inputs=inputs,
            output_root=self.output_root / "results",
            device=request.device,
            tile_size=request.tile_size,
            overlap=request.overlap,
            weed_threshold=request.weed_threshold,
        )
        job = AnalysisJob(test_id, config).start()
        registry = ModelRegistry.from_file(self.registry_path)
        manifest = registry.get(request.model_id)
        factory = SegmenterFactory(registry)
        pipeline: SemanticTilePipeline | InstanceTilePipeline
        if manifest.task is ModelTask.SEMANTIC:
            pipeline = SemanticTilePipeline(
                factory.load_semantic(
                    request.model_id,
                    request.artifact_role,
                    device=request.device,
                )
            )
        elif manifest.task is ModelTask.MAIZE_INSTANCE:
            pipeline = InstanceTilePipeline(
                factory.load_instance(
                    request.model_id,
                    request.artifact_role,
                    device=request.device,
                )
            )
        else:
            raise InferenceInputError(f"Loại mô hình chưa được hỗ trợ: {manifest.task.value}")

        def pipeline_progress(stage: JobStage, value: float, detail: str) -> None:
            progress(0.08 + value * 0.91, detail or stage.value)

        result = pipeline.run(job, pipeline_progress, lambda: False)
        progress(1.0, "Đã hoàn tất kiểm tra mô hình.")
        return ModelTestResult(
            job.complete(result),
            source,
            media_kind,
            len(inputs),
        )

    def _prepare_inputs(
        self,
        source: Path,
        test_id: str,
        progress: ProgressCallback,
    ) -> tuple[tuple[AnalysisInput, ...], str]:
        suffix = source.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return (AnalysisInput("image-0001", source),), "image"
        if suffix not in VIDEO_SUFFIXES:
            raise InferenceInputError(
                "Định dạng chưa hỗ trợ. Hãy chọn ảnh JPG, PNG, TIFF hoặc video MP4, MOV, AVI."
            )
        return self._extract_video_frames(source, test_id, progress), "video"

    def _extract_video_frames(
        self,
        source: Path,
        test_id: str,
        progress: ProgressCallback,
        *,
        maximum_frames: int = 12,
    ) -> tuple[AnalysisInput, ...]:
        import cv2

        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise InferenceInputError(f"Không thể đọc video: {source.name}")
        try:
            frame_total = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 0)
            if frame_total > 0:
                indices = _sample_indices(frame_total, maximum_frames)
            else:
                indices = tuple(range(maximum_frames))
            frame_dir = self.output_root / "sources" / test_id
            frame_dir.mkdir(parents=True, exist_ok=True)
            inputs: list[AnalysisInput] = []
            for position, frame_index in enumerate(indices):
                if frame_total > 0:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                success, frame = capture.read()
                if not success:
                    break
                image_id = f"frame-{position + 1:04d}"
                destination = frame_dir / f"{image_id}.jpg"
                if not cv2.imwrite(str(destination), frame):
                    raise InferenceInputError(f"Không thể lưu khung video: {destination.name}")
                inputs.append(AnalysisInput(image_id, destination))
                progress(
                    0.01 + 0.06 * (position + 1) / len(indices),
                    f"Đã lấy {position + 1}/{len(indices)} khung video",
                )
                if frame_total <= 0:
                    for _ in range(29):
                        if not capture.grab():
                            break
        finally:
            capture.release()
        if not inputs:
            raise InferenceInputError(f"Video không có khung hình đọc được: {source.name}")
        return tuple(inputs)


def _sample_indices(frame_total: int, maximum_frames: int) -> tuple[int, ...]:
    count = min(maximum_frames, frame_total)
    if count <= 1:
        return (0,)
    return tuple(
        round(index * (frame_total - 1) / (count - 1))
        for index in range(count)
    )
