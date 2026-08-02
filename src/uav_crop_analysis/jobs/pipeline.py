"""Semantic tile pipeline with probability blending and atomic artifact export."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, UnidentifiedImageError

from uav_crop_analysis.errors import PipelineCancelledError, PipelineExecutionError
from uav_crop_analysis.inference import (
    ImageInput,
    InstancePrediction,
    InstanceSegmenter,
    PredictionProvenance,
    SemanticSegmenter,
)
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
        expected_class_names: tuple[str, ...] | None = None
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
                crop_probability_acc = np.zeros((height, width), dtype=np.float32)
                weed_probability_acc = np.zeros((height, width), dtype=np.float32)
                weight_acc = np.zeros((height, width), dtype=np.float32)
                class_map = np.zeros((height, width), dtype=np.int32)
                class_weight = np.full((height, width), -1.0, dtype=np.float32)
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
                    if not {"crop", "weed"} <= set(prediction.class_names):
                        raise PipelineExecutionError(
                            "semantic model must provide crop and weed classes"
                        )
                    if expected_provenance is None:
                        expected_provenance = prediction.provenance
                        expected_class_names = prediction.class_names
                    elif prediction.provenance != expected_provenance:
                        raise PipelineExecutionError("model provenance changed during a job")
                    elif prediction.class_names != expected_class_names:
                        raise PipelineExecutionError("semantic class map changed during a job")
                    crop_index = prediction.class_names.index("crop")
                    weed_index = prediction.class_names.index("weed")
                    crop_probability = prediction.probabilities[crop_index]
                    weed_probability = prediction.probabilities[weed_index]
                    crop_probability_acc[y1:y2, x1:x2] += (
                        crop_probability[:valid_height, :valid_width]
                        * kernel[:valid_height, :valid_width]
                    )
                    weed_probability_acc[y1:y2, x1:x2] += (
                        weed_probability[:valid_height, :valid_width]
                        * kernel[:valid_height, :valid_width]
                    )
                    weight_acc[y1:y2, x1:x2] += kernel[:valid_height, :valid_width]
                    tile_weight = kernel[:valid_height, :valid_width]
                    target_weight = class_weight[y1:y2, x1:x2]
                    replace = tile_weight > target_weight
                    target_map = class_map[y1:y2, x1:x2]
                    target_map[replace] = prediction.class_map[:valid_height, :valid_width][replace]
                    target_weight[replace] = tile_weight[replace]
                    latency_ms += prediction.latency_ms
                    completed_tiles += 1
                    phase_progress = 0.05 + 0.70 * completed_tiles / max(total_tiles, 1)
                    progress(
                        JobStage.TILE_INFERENCE,
                        phase_progress,
                        f"processed tile {completed_tiles}/{total_tiles}",
                    )

                if expected_class_names is None:
                    raise PipelineExecutionError("semantic model class map is unavailable")
                crop_index = expected_class_names.index("crop")
                crop_probability = crop_probability_acc / np.maximum(
                    weight_acc, np.float32(1e-7)
                )
                weed_probability = weed_probability_acc / np.maximum(
                    weight_acc, np.float32(1e-7)
                )
                crop_probability = np.ascontiguousarray(crop_probability, dtype=np.float32)
                weed_probability = np.ascontiguousarray(weed_probability, dtype=np.float32)
                weed_mask = np.ascontiguousarray(
                    weed_probability >= config.weed_threshold
                )
                crop_mask = np.ascontiguousarray(
                    (class_map == crop_index) & ~weed_mask
                )
                semantic_map = np.zeros((height, width), dtype=np.uint8)
                semantic_map[crop_mask] = 1
                semantic_map[weed_mask] = 2
                crop_probability_path = staging / f"{item.image_id}.crop_probability.npy"
                crop_mask_path = staging / f"{item.image_id}.crop_mask.png"
                weed_probability_path = staging / f"{item.image_id}.weed_probability.npy"
                weed_mask_path = staging / f"{item.image_id}.weed_mask.png"
                semantic_map_path = staging / f"{item.image_id}.semantic_classes.png"
                np.save(crop_probability_path, crop_probability, allow_pickle=False)
                np.save(weed_probability_path, weed_probability, allow_pickle=False)
                Image.fromarray(crop_mask.astype(np.uint8) * 255, mode="L").save(
                    crop_mask_path
                )
                Image.fromarray(weed_mask.astype(np.uint8) * 255, mode="L").save(
                    weed_mask_path
                )
                Image.fromarray(semantic_map, mode="L").save(semantic_map_path)
                crop_pixels = int(crop_mask.sum())
                weed_pixels = int(weed_mask.sum())
                class_pixels = {
                    "background": int((semantic_map == 0).sum()),
                    "crop": crop_pixels,
                    "weed": weed_pixels,
                }
                class_coverage = {
                    name: round(100.0 * pixels / semantic_map.size, 6)
                    for name, pixels in class_pixels.items()
                }
                summary = {
                    "analysis_task": "semantic_segmentation",
                    "image_id": item.image_id,
                    "source_path": str(item.source_path),
                    "height": height,
                    "width": width,
                    "tile_count": len(windows),
                    "crop_pixels": crop_pixels,
                    "crop_coverage_percent": round(
                        100.0 * crop_pixels / semantic_map.size, 6
                    ),
                    "weed_pixels": weed_pixels,
                    "weed_coverage_percent": round(
                        100.0 * weed_pixels / semantic_map.size, 6
                    ),
                    "class_pixels": class_pixels,
                    "class_coverage_percent": class_coverage,
                    "inference_latency_ms": round(latency_ms, 3),
                }
                summaries.append(summary)
                artifact_records.extend(
                    [
                        artifact_record(crop_probability_path, staging),
                        artifact_record(crop_mask_path, staging),
                        artifact_record(weed_probability_path, staging),
                        artifact_record(weed_mask_path, staging),
                        artifact_record(semantic_map_path, staging),
                    ]
                )

            self._check_cancel(is_cancelled)
            progress(JobStage.MERGE, 0.80, "merged overlapping tile probabilities")
            progress(JobStage.METRICS, 0.90, "computed crop and weed coverage metrics")
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


@dataclass(frozen=True, slots=True)
class _SourceInstance:
    class_index: int
    class_name: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    mask_origin_xy: tuple[int, int]
    mask: NDArray[np.bool_]
    mask_pixels: int


class InstanceTilePipeline:
    """Run YOLOv8-seg on overlapping tiles and merge duplicate maize detections."""

    def __init__(self, segmenter: InstanceSegmenter, *, merge_iou_threshold: float = 0.70) -> None:
        if not 0.0 < merge_iou_threshold <= 1.0:
            raise ValueError("merge_iou_threshold must be in (0, 1]")
        self.segmenter = segmenter
        self.merge_iou_threshold = merge_iou_threshold

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
        image_shapes = _validate_input_images(config.inputs, config.tile_size, config.overlap, is_cancelled)
        job_root, staging, final = _prepare_attempt_directories(job)
        del job_root
        total_tiles = sum(
            len(tile_windows(height, width, config.tile_size, config.overlap))
            for height, width in image_shapes.values()
        )
        completed_tiles = 0
        summaries: list[dict[str, Any]] = []
        artifact_records: list[dict[str, Any]] = []
        expected_provenance: PredictionProvenance | None = None
        try:
            for item in config.inputs:
                self._check_cancel(is_cancelled)
                image_rgb = _load_image_rgb(item.source_path, item.image_id)
                height, width = image_shapes[item.image_id]
                windows = tile_windows(height, width, config.tile_size, config.overlap)
                candidates: list[_SourceInstance] = []
                latency_ms = 0.0
                for x1, y1, x2, y2 in windows:
                    self._check_cancel(is_cancelled)
                    tile = np.zeros((config.tile_size, config.tile_size, 3), dtype=np.uint8)
                    valid_height = y2 - y1
                    valid_width = x2 - x1
                    tile[:valid_height, :valid_width] = image_rgb[y1:y2, x1:x2]
                    prediction = self.segmenter.predict(ImageInput(tile))
                    if expected_provenance is None:
                        expected_provenance = prediction.provenance
                    elif prediction.provenance != expected_provenance:
                        raise PipelineExecutionError("model provenance changed during a job")
                    candidates.extend(
                        _translate_tile_instances(
                            prediction.instances,
                            x1=x1,
                            y1=y1,
                            valid_height=valid_height,
                            valid_width=valid_width,
                            source_size_hw=(height, width),
                        )
                    )
                    latency_ms += prediction.latency_ms
                    completed_tiles += 1
                    progress(
                        JobStage.TILE_INFERENCE,
                        0.05 + 0.65 * completed_tiles / max(total_tiles, 1),
                        f"processed maize tile {completed_tiles}/{total_tiles}",
                    )

                self._check_cancel(is_cancelled)
                kept = _suppress_duplicate_instances(candidates, self.merge_iou_threshold)
                label_map = _instance_label_map(kept, (height, width))
                mask_path = staging / f"{item.image_id}.maize_instances.png"
                json_path = staging / f"{item.image_id}.maize_instances.json"
                overlay_path = staging / f"{item.image_id}.maize_overlay.png"
                Image.fromarray(label_map, mode="L").save(mask_path)
                json_path.write_text(
                    json.dumps(_instance_records(kept), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                Image.fromarray(_instance_overlay(image_rgb, kept), mode="RGB").save(overlay_path)
                counts: dict[str, int] = {}
                for instance in kept:
                    counts[instance.class_name] = counts.get(instance.class_name, 0) + 1
                canopy_pixels_by_class = {
                    instance.class_name: int((label_map == instance.class_index + 1).sum())
                    for instance in kept
                }
                canopy_pixels = int((label_map > 0).sum())
                summary = {
                    "analysis_task": "maize_instance_segmentation",
                    "image_id": item.image_id,
                    "source_path": str(item.source_path),
                    "height": height,
                    "width": width,
                    "tile_count": len(windows),
                    "maize_instance_count": len(kept),
                    "maize_counts": dict(sorted(counts.items())),
                    "maize_canopy_pixels": canopy_pixels,
                    "maize_canopy_pixels_by_class": dict(sorted(canopy_pixels_by_class.items())),
                    "maize_canopy_coverage_percent": round(
                        100.0 * canopy_pixels / label_map.size, 6
                    ),
                    "inference_latency_ms": round(latency_ms, 3),
                }
                summaries.append(summary)
                artifact_records.extend(
                    [
                        artifact_record(mask_path, staging),
                        artifact_record(json_path, staging),
                        artifact_record(overlay_path, staging),
                    ]
                )

            self._check_cancel(is_cancelled)
            progress(JobStage.MERGE, 0.78, "merged duplicate maize detections")
            progress(JobStage.METRICS, 0.88, "counted maize instances by stage")
            if expected_provenance is None:
                raise PipelineExecutionError("pipeline produced no predictions")
            provenance = asdict(expected_provenance)
            summary_path = staging / "summary.json"
            summary_path.write_text(
                json.dumps({"analysis_task": "maize_instance_segmentation", "images": summaries}, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            artifact_records.append(artifact_record(summary_path, staging))
            progress(JobStage.EXPORT, 0.96, "writing maize instance artifact manifest")
            manifest_path = staging / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "job_id": job.job_id,
                        "attempt": job.attempt,
                        "mission_id": config.mission_id,
                        "model_id": config.model_id,
                        "artifact_role": config.artifact_role,
                        "analysis_task": "maize_instance_segmentation",
                        "tile_size": config.tile_size,
                        "overlap": config.overlap,
                        "duplicate_merge_iou": self.merge_iou_threshold,
                        "duplicate_merge_strategy": "exact_local_mask_iou",
                        "provenance": provenance,
                        "artifacts": artifact_records,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            manifest_sha256 = sha256_file(manifest_path)
            (staging / "COMPLETED.json").write_text(
                json.dumps(
                    {"manifest": "manifest.json", "manifest_sha256": manifest_sha256},
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            self._check_cancel(is_cancelled)
            os.replace(staging, final)
            return AnalysisResult(final, manifest_sha256, tuple(summaries), provenance)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _check_cancel(is_cancelled: CancelCheck) -> None:
        if is_cancelled():
            raise PipelineCancelledError("analysis job was cancelled")


def _validate_input_images(
    inputs: tuple[Any, ...], tile_size: int, overlap: int, is_cancelled: CancelCheck
) -> dict[str, tuple[int, int]]:
    shapes: dict[str, tuple[int, int]] = {}
    for item in inputs:
        if is_cancelled():
            raise PipelineCancelledError("analysis job was cancelled")
        try:
            with Image.open(item.source_path) as image:
                width, height = image.size
                image.verify()
        except (OSError, UnidentifiedImageError) as exc:
            raise PipelineExecutionError(
                f"cannot read analysis image: {item.source_path}",
                context={"image_id": item.image_id, "path": str(item.source_path)},
            ) from exc
        shapes[item.image_id] = (height, width)
        tile_windows(height, width, tile_size, overlap)
    return shapes


def _prepare_attempt_directories(job: AnalysisJob) -> tuple[Path, Path, Path]:
    job_root = job.config.output_root / job.job_id
    job_root.mkdir(parents=True, exist_ok=True)
    cleanup_staging_artifacts(job_root)
    staging = Path(tempfile.mkdtemp(prefix=f".attempt-{job.attempt:04d}-", dir=job_root))
    final = job_root / f"attempt-{job.attempt:04d}"
    if final.exists():
        shutil.rmtree(staging, ignore_errors=True)
        raise PipelineExecutionError(f"artifact attempt already exists: {final}")
    return job_root, staging, final


def _load_image_rgb(path: Path, image_id: str) -> NDArray[np.uint8]:
    try:
        with Image.open(path) as source_image:
            return np.asarray(source_image.convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as exc:
        raise PipelineExecutionError(
            f"cannot decode analysis image: {path}", context={"image_id": image_id}
        ) from exc


def _translate_tile_instances(
    instances: tuple[InstancePrediction, ...],
    *,
    x1: int,
    y1: int,
    valid_height: int,
    valid_width: int,
    source_size_hw: tuple[int, int],
) -> tuple[_SourceInstance, ...]:
    height, width = source_size_hw
    translated: list[_SourceInstance] = []
    for instance in instances:
        local = instance.mask[:valid_height, :valid_width]
        if not local.any():
            continue
        active_rows = np.flatnonzero(local.any(axis=1))
        active_columns = np.flatnonzero(local.any(axis=0))
        local_y1 = int(active_rows[0])
        local_y2 = int(active_rows[-1]) + 1
        local_x1 = int(active_columns[0])
        local_x2 = int(active_columns[-1]) + 1
        cropped_mask = np.ascontiguousarray(
            local[local_y1:local_y2, local_x1:local_x2],
            dtype=np.bool_,
        )
        bx1, by1, bx2, by2 = instance.box_xyxy
        translated.append(
            _SourceInstance(
                class_index=instance.class_index,
                class_name=instance.class_name,
                score=instance.score,
                box_xyxy=(
                    max(0.0, min(float(width), bx1 + x1)),
                    max(0.0, min(float(height), by1 + y1)),
                    max(0.0, min(float(width), bx2 + x1)),
                    max(0.0, min(float(height), by2 + y1)),
                ),
                mask_origin_xy=(x1 + local_x1, y1 + local_y1),
                mask=cropped_mask,
                mask_pixels=int(cropped_mask.sum()),
            )
        )
    return tuple(translated)


def _suppress_duplicate_instances(
    candidates: list[_SourceInstance], threshold: float
) -> tuple[_SourceInstance, ...]:
    retained: list[_SourceInstance] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        duplicate = any(
            candidate.class_index == existing.class_index
            and _source_mask_iou(candidate, existing) >= threshold
            for existing in retained
        )
        if not duplicate:
            retained.append(candidate)
    return tuple(retained)


def _source_mask_iou(left: _SourceInstance, right: _SourceInstance) -> float:
    left_x, left_y = left.mask_origin_xy
    right_x, right_y = right.mask_origin_xy
    left_height, left_width = left.mask.shape
    right_height, right_width = right.mask.shape
    intersection_x1 = max(left_x, right_x)
    intersection_y1 = max(left_y, right_y)
    intersection_x2 = min(left_x + left_width, right_x + right_width)
    intersection_y2 = min(left_y + left_height, right_y + right_height)
    if intersection_x1 >= intersection_x2 or intersection_y1 >= intersection_y2:
        return 0.0
    left_region = left.mask[
        intersection_y1 - left_y : intersection_y2 - left_y,
        intersection_x1 - left_x : intersection_x2 - left_x,
    ]
    right_region = right.mask[
        intersection_y1 - right_y : intersection_y2 - right_y,
        intersection_x1 - right_x : intersection_x2 - right_x,
    ]
    intersection = int(np.logical_and(left_region, right_region).sum())
    union = left.mask_pixels + right.mask_pixels - intersection
    return intersection / union if union else 0.0


def _instance_label_map(
    instances: tuple[_SourceInstance, ...], size_hw: tuple[int, int]
) -> NDArray[np.uint8]:
    labels = np.zeros(size_hw, dtype=np.uint8)
    for instance in reversed(instances):
        x, y = instance.mask_origin_xy
        height, width = instance.mask.shape
        region = labels[y : y + height, x : x + width]
        region[instance.mask] = instance.class_index + 1
    return labels


def _instance_records(instances: tuple[_SourceInstance, ...]) -> list[dict[str, Any]]:
    return [
        {
            "class_index": instance.class_index,
            "class_name": instance.class_name,
            "score": round(instance.score, 6),
            "box_xyxy": [round(value, 3) for value in instance.box_xyxy],
            "mask_pixels": instance.mask_pixels,
        }
        for instance in instances
    ]


def _instance_overlay(
    image_rgb: NDArray[np.uint8], instances: tuple[_SourceInstance, ...]
) -> NDArray[np.uint8]:
    colors = ((62, 163, 94), (60, 128, 207), (222, 154, 49))
    overlay = image_rgb.astype(np.float32).copy()
    for instance in instances:
        mask_color = np.asarray(
            colors[instance.class_index % len(colors)], dtype=np.float32
        )
        x, y = instance.mask_origin_xy
        height, width = instance.mask.shape
        region = overlay[y : y + height, x : x + width]
        region[instance.mask] = region[instance.mask] * 0.48 + mask_color * 0.52
    rendered = np.ascontiguousarray(overlay.clip(0, 255), dtype=np.uint8)
    canvas = Image.fromarray(rendered, mode="RGB")
    draw = ImageDraw.Draw(canvas)
    for instance in instances:
        outline_color = colors[instance.class_index % len(colors)]
        draw.rectangle(instance.box_xyxy, outline=outline_color, width=2)
    return np.asarray(canvas, dtype=np.uint8)

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
