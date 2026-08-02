from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from uav_crop_analysis.inference import (
    ImageInput,
    InstanceBatchPrediction,
    InstancePrediction,
    PredictionProvenance,
)
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    InstanceTilePipeline,
)
from uav_crop_analysis.jobs.pipeline import (
    _SourceInstance,
    _source_mask_iou,
    _translate_tile_instances,
)
from uav_crop_analysis.ui.result_layers import LayerMode, render_layer, result_entries


class _DuplicateTileSegmenter:
    def __init__(self) -> None:
        self.calls = 0
        self.provenance = PredictionProvenance(
            model_id="yolov8-test",
            model_version="1",
            artifact_role="best",
            artifact_sha256="a" * 64,
            runtime="ultralytics",
            device="cpu",
            preprocessing_fingerprint="b" * 64,
        )

    def predict(self, image: ImageInput) -> InstanceBatchPrediction:
        mask = np.zeros(image.size_hw, dtype=np.bool_)
        if self.calls == 0:
            mask[:, 4:] = True
            box = (4.0, 0.0, 8.0, 8.0)
            score = 0.9
        else:
            mask[:, :4] = True
            box = (0.0, 0.0, 4.0, 8.0)
            score = 0.8
        self.calls += 1
        return InstanceBatchPrediction(
            image_size_hw=image.size_hw,
            instances=(InstancePrediction(1, "maize4", score, box, mask),),
            provenance=self.provenance,
            latency_ms=1.0,
        )


def test_instance_pipeline_merges_overlap_and_exports_viewer_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (12, 8), (38, 88, 48)).save(source)
    config = AnalysisJobConfig(
        mission_id="mission-instance",
        model_id="yolov8-test",
        artifact_role="best",
        registry_path=tmp_path / "registry.json",
        inputs=(AnalysisInput("image-01", source),),
        output_root=tmp_path / "results",
        tile_size=8,
        overlap=4,
    )
    job = AnalysisJob("instance-job", config).start()

    result = InstanceTilePipeline(_DuplicateTileSegmenter()).run(
        job, lambda _stage, _progress, _detail: None, lambda: False
    )

    summary = result.image_summaries[0]
    assert summary["analysis_task"] == "maize_instance_segmentation"
    assert summary["maize_instance_count"] == 1
    assert summary["maize_counts"] == {"maize4": 1}
    labels = np.asarray(
        Image.open(result.artifact_dir / "image-01.maize_instances.png"), dtype=np.uint8
    )
    assert labels.shape == (8, 12)
    assert int((labels == 2).sum()) == 32
    records = json.loads(
        (result.artifact_dir / "image-01.maize_instances.json").read_text(encoding="utf-8")
    )
    assert len(records) == 1
    assert records[0]["class_name"] == "maize4"
    assert (result.artifact_dir / "image-01.maize_overlay.png").is_file()
    entry = result_entries(job.complete(result))[0]
    assert entry.maize_instance_count == 1
    assert not render_layer(entry, LayerMode.INSTANCE_MASK).isNull()
    assert not render_layer(entry, LayerMode.OVERLAY).isNull()


def test_translated_instances_store_only_the_exact_local_mask() -> None:
    mask = np.zeros((8, 8), dtype=np.bool_)
    mask[2:5, 3:7] = True
    prediction = InstancePrediction(1, "maize4", 0.9, (3.0, 2.0, 7.0, 5.0), mask)

    translated = _translate_tile_instances(
        (prediction,),
        x1=100,
        y1=200,
        valid_height=8,
        valid_width=8,
        source_size_hw=(3000, 4000),
    )[0]

    assert translated.mask_origin_xy == (103, 202)
    assert translated.mask.shape == (3, 4)
    assert translated.mask_pixels == 12
    assert translated.mask.all()


def test_local_mask_iou_matches_dense_full_image_iou() -> None:
    left_mask = np.array(((1, 1, 0), (0, 1, 1)), dtype=np.bool_)
    right_mask = np.array(((1, 0), (1, 1)), dtype=np.bool_)
    left = _source_instance(left_mask, (10, 20))
    right = _source_instance(right_mask, (11, 21))
    left_dense = np.zeros((30, 30), dtype=np.bool_)
    right_dense = np.zeros((30, 30), dtype=np.bool_)
    left_dense[20:22, 10:13] = left_mask
    right_dense[21:23, 11:13] = right_mask
    intersection = int(np.logical_and(left_dense, right_dense).sum())
    union = int(np.logical_or(left_dense, right_dense).sum())

    assert _source_mask_iou(left, right) == intersection / union


def _source_instance(
    mask: np.ndarray,
    origin: tuple[int, int],
) -> _SourceInstance:
    return _SourceInstance(
        class_index=1,
        class_name="maize4",
        score=0.9,
        box_xyxy=(0.0, 0.0, 1.0, 1.0),
        mask_origin_xy=origin,
        mask=np.ascontiguousarray(mask, dtype=np.bool_),
        mask_pixels=int(mask.sum()),
    )
