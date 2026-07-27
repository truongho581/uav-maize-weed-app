from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from uav_crop_analysis.errors import InferenceRuntimeError, PipelineCancelledError
from uav_crop_analysis.inference import (
    ImageInput,
    PredictionProvenance,
    SemanticPrediction,
)
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    JobStage,
    SemanticTilePipeline,
)


PROVENANCE = PredictionProvenance(
    model_id="threshold-semantic",
    model_version="1",
    artifact_role="unit",
    artifact_sha256="a" * 64,
    runtime="unit",
    device="cpu",
    preprocessing_fingerprint="b" * 64,
)


class ThresholdSegmenter:
    def __init__(self, fail_after: int | None = None) -> None:
        self.calls = 0
        self.fail_after = fail_after

    def predict(self, image: ImageInput) -> SemanticPrediction:
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise InferenceRuntimeError("simulated model failure")
        weed = image.pixels[..., 0].astype(np.float32) / 255.0
        crop = np.zeros_like(weed)
        background = 1.0 - weed
        probabilities = np.ascontiguousarray(
            np.stack((background, crop, weed)), dtype=np.float32
        )
        class_map = np.ascontiguousarray(probabilities.argmax(axis=0), dtype=np.int32)
        return SemanticPrediction(
            class_names=("background", "crop", "weed"),
            class_map=class_map,
            probabilities=probabilities,
            target_masks={"weed": np.ascontiguousarray(class_map == 2)},
            provenance=PROVENANCE,
            latency_ms=1.0,
        )


def _started_job(tmp_path: Path, image: np.ndarray, job_id: str) -> AnalysisJob:
    image_path = tmp_path / f"{job_id}.png"
    Image.fromarray(image, mode="RGB").save(image_path)
    config = AnalysisJobConfig(
        mission_id="mission-pipeline",
        model_id="threshold-semantic",
        artifact_role="unit",
        registry_path=tmp_path / "registry.json",
        inputs=(AnalysisInput("image-1", image_path),),
        output_root=tmp_path / "results",
        tile_size=16,
        overlap=4,
    )
    return AnalysisJob(job_id, config).start()


def test_pipeline_merges_probability_and_exports_atomic_artifacts(tmp_path: Path) -> None:
    image = np.zeros((20, 24, 3), dtype=np.uint8)
    image[:, 12:, 0] = 255
    job = _started_job(tmp_path, image, "job-pipeline")
    events: list[tuple[JobStage, float]] = []

    result = SemanticTilePipeline(ThresholdSegmenter()).run(
        job,
        lambda stage, progress, _detail: events.append((stage, progress)),
        lambda: False,
    )

    mask = np.asarray(Image.open(result.artifact_dir / "image-1.weed_mask.png")) > 0
    probability = np.load(result.artifact_dir / "image-1.weed_probability.npy")
    np.testing.assert_array_equal(mask, image[..., 0] > 127)
    np.testing.assert_allclose(probability, image[..., 0] / 255.0, atol=1e-6)
    assert (result.artifact_dir / "manifest.json").is_file()
    assert (result.artifact_dir / "COMPLETED.json").is_file()
    assert result.image_summaries[0]["weed_coverage_percent"] == 50.0
    assert [stage for stage, _ in events][-3:] == [
        JobStage.MERGE,
        JobStage.METRICS,
        JobStage.EXPORT,
    ]
    assert all(left <= right for left, right in zip(
        [value for _, value in events], [value for _, value in events][1:]
    ))


def test_cancelled_pipeline_does_not_publish_completed_artifact(tmp_path: Path) -> None:
    job = _started_job(tmp_path, np.zeros((20, 20, 3), dtype=np.uint8), "job-cancel")

    with pytest.raises(PipelineCancelledError):
        SemanticTilePipeline(ThresholdSegmenter()).run(
            job,
            lambda _stage, _progress, _detail: None,
            lambda: True,
        )

    assert not (job.config.output_root / job.job_id / "attempt-0001").exists()


def test_model_failure_removes_staging_directory(tmp_path: Path) -> None:
    job = _started_job(tmp_path, np.zeros((20, 20, 3), dtype=np.uint8), "job-failure")

    with pytest.raises(InferenceRuntimeError):
        SemanticTilePipeline(ThresholdSegmenter(fail_after=1)).run(
            job,
            lambda _stage, _progress, _detail: None,
            lambda: False,
        )

    job_root = job.config.output_root / job.job_id
    assert not (job_root / "attempt-0001").exists()
    assert not tuple(job_root.glob(".attempt-*"))
