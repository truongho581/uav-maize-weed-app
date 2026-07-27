"""Semantic tile pipeline with probability blending and atomic artifact export."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

from uav_crop_analysis.errors import PipelineCancelledError, PipelineExecutionError
from uav_crop_analysis.inference import ImageInput, PredictionProvenance, SemanticSegmenter
from uav_crop_analysis.jobs.models import (
    AnalysisJob,
    AnalysisResult,
    JobStage,
)


ProgressCallback = Callable[[JobStage, float, str], None]
CancelCheck = Callable[[], bool]


class SemanticTilePipeline:
    def __init__(self, segmenter: SemanticSegmenter) -> None:
        self.segmenter = segmenter

    def run(
        self,
        job: AnalysisJob,
        progress: ProgressCallback,
        is_cancelled: CancelCheck,
    ) -> AnalysisResult:
        config = job.config
        if job.attempt < 1:
            raise PipelineExecutionError("job must be started before pipeline execution")
        progress(JobStage.PREPARE, 0.01, "validating input images")
        image_shapes: dict[str, tuple[int, int]] = {}
        tile_counts: dict[str, int] = {}
        for item in config.inputs:
            self._check_cancel(is_cancelled)
            try:
                with Image.open(item.source_path) as image:
                    width, height = image.size
                    image.verify()
            except (OSError, UnidentifiedImageError) as exc:
                raise PipelineExecutionError(
                    f"cannot read analysis image: {item.source_path}",
                    context={"image_id": item.image_id, "path": str(item.source_path)},
                ) from exc
            image_shapes[item.image_id] = (height, width)
            tile_counts[item.image_id] = len(
                tile_windows(height, width, config.tile_size, config.overlap)
            )

        job_root = config.output_root / job.job_id
        job_root.mkdir(parents=True, exist_ok=True)
        cleanup_staging_artifacts(job_root)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".attempt-{job.attempt:04d}-",
                dir=job_root,
            )
        )
        final = job_root / f"attempt-{job.attempt:04d}"
        if final.exists():
            shutil.rmtree(staging, ignore_errors=True)
            raise PipelineExecutionError(f"artifact attempt already exists: {final}")

        total_tiles = sum(tile_counts.values())
        completed_tiles = 0
        summaries: list[dict[str, Any]] = []
        artifact_records: list[dict[str, Any]] = []
        expected_provenance: PredictionProvenance | None = None
        try:
            for item in config.inputs:
                self._check_cancel(is_cancelled)
                try:
                    with Image.open(item.source_path) as source_image:
                        image_rgb = np.asarray(source_image.convert("RGB"), dtype=np.uint8)
                except (OSError, UnidentifiedImageError) as exc:
                    raise PipelineExecutionError(
                        f"cannot decode analysis image: {item.source_path}",
                        context={"image_id": item.image_id},
                    ) from exc
                height, width = image_shapes[item.image_id]
                probability_acc = np.zeros((height, width), dtype=np.float32)
                weight_acc = np.zeros((height, width), dtype=np.float32)
                kernel = blend_weight_kernel(config.tile_size)
                latency_ms = 0.0
                windows = tile_windows(height, width, config.tile_size, config.overlap)
                for x1, y1, x2, y2 in windows:
                    self._check_cancel(is_cancelled)
                    tile = np.zeros((config.tile_size, config.tile_size, 3), dtype=np.uint8)
                    valid_height = y2 - y1
                    valid_width = x2 - x1
                    tile[:valid_height, :valid_width] = image_rgb[y1:y2, x1:x2]
                    prediction = self.segmenter.predict(ImageInput(tile))
                    if "weed" not in prediction.class_names:
                        raise PipelineExecutionError("semantic model has no weed class")
                    if expected_provenance is None:
                        expected_provenance = prediction.provenance
                    elif prediction.provenance != expected_provenance:
                        raise PipelineExecutionError("model provenance changed during a job")
                    weed_index = prediction.class_names.index("weed")
                    weed_probability = prediction.probabilities[weed_index]
                    probability_acc[y1:y2, x1:x2] += (
                        weed_probability[:valid_height, :valid_width]
                        * kernel[:valid_height, :valid_width]
                    )
                    weight_acc[y1:y2, x1:x2] += kernel[:valid_height, :valid_width]
                    latency_ms += prediction.latency_ms
                    completed_tiles += 1
                    phase_progress = 0.05 + 0.70 * completed_tiles / max(total_tiles, 1)
                    progress(
                        JobStage.TILE_INFERENCE,
                        phase_progress,
                        f"processed tile {completed_tiles}/{total_tiles}",
                    )

                probability = probability_acc / np.maximum(weight_acc, np.float32(1e-7))
                probability = np.ascontiguousarray(probability, dtype=np.float32)
                mask = np.ascontiguousarray(probability >= config.weed_threshold)
                probability_path = staging / f"{item.image_id}.weed_probability.npy"
                mask_path = staging / f"{item.image_id}.weed_mask.png"
                np.save(probability_path, probability, allow_pickle=False)
                Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(mask_path)
                weed_pixels = int(mask.sum())
                summary = {
                    "image_id": item.image_id,
                    "source_path": str(item.source_path),
                    "height": height,
                    "width": width,
                    "tile_count": len(windows),
                    "weed_pixels": weed_pixels,
                    "weed_coverage_percent": round(100.0 * weed_pixels / mask.size, 6),
                    "inference_latency_ms": round(latency_ms, 3),
                }
                summaries.append(summary)
                artifact_records.extend(
                    [
                        artifact_record(probability_path, staging),
                        artifact_record(mask_path, staging),
                    ]
                )

            self._check_cancel(is_cancelled)
            progress(JobStage.MERGE, 0.80, "merged overlapping tile probabilities")
            progress(JobStage.METRICS, 0.90, "computed weed coverage metrics")
            if expected_provenance is None:
                raise PipelineExecutionError("pipeline produced no predictions")
            provenance = asdict(expected_provenance)
            summary_path = staging / "summary.json"
            summary_path.write_text(
                json.dumps({"images": summaries}, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            artifact_records.append(artifact_record(summary_path, staging))
            self._check_cancel(is_cancelled)
            progress(JobStage.EXPORT, 0.96, "writing artifact manifest")
            manifest_path = staging / "manifest.json"
            manifest = {
                "schema_version": 1,
                "job_id": job.job_id,
                "attempt": job.attempt,
                "mission_id": config.mission_id,
                "model_id": config.model_id,
                "artifact_role": config.artifact_role,
                "tile_size": config.tile_size,
                "overlap": config.overlap,
                "weed_threshold": config.weed_threshold,
                "provenance": provenance,
                "artifacts": artifact_records,
            }
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            manifest_sha256 = sha256_file(manifest_path)
            completion_path = staging / "COMPLETED.json"
            completion_path.write_text(
                json.dumps(
                    {"manifest": "manifest.json", "manifest_sha256": manifest_sha256},
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            self._check_cancel(is_cancelled)
            os.replace(staging, final)
            return AnalysisResult(
                artifact_dir=final,
                manifest_sha256=manifest_sha256,
                image_summaries=tuple(summaries),
                provenance=provenance,
            )
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _check_cancel(is_cancelled: CancelCheck) -> None:
        if is_cancelled():
            raise PipelineCancelledError("analysis job was cancelled")

def tile_windows(
    height: int,
    width: int,
    tile_size: int,
    overlap: int,
) -> tuple[tuple[int, int, int, int], ...]:
    stride = tile_size - overlap

    def starts(length: int) -> list[int]:
        if length <= tile_size:
            return [0]
        result = list(range(0, length - tile_size + 1, stride))
        last = length - tile_size
        if result[-1] != last:
            result.append(last)
        return result

    return tuple(
        (x, y, min(x + tile_size, width), min(y + tile_size, height))
        for y in starts(height)
        for x in starts(width)
    )


def blend_weight_kernel(size: int) -> NDArray[np.float32]:
    axis = np.minimum(np.arange(size) + 1, np.arange(size, 0, -1)).astype(np.float32)
    axis /= axis.max()
    axis = np.maximum(axis, np.float32(0.05))
    return np.ascontiguousarray(np.outer(axis, axis), dtype=np.float32)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def cleanup_staging_artifacts(job_root: Path) -> None:
    """Remove hidden, never-published attempt directories after interruption."""
    if not job_root.is_dir():
        return
    for path in job_root.glob(".attempt-*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
