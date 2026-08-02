from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, cast

import numpy as np
from PIL import Image
import pytest

onnx = pytest.importorskip("onnx")
from onnx import TensorProto, helper, numpy_helper  # noqa: E402

from uav_crop_analysis.adapters import SQLiteAnalysisJobRepository  # noqa: E402
from uav_crop_analysis.inference import ModelRegistry, SegmenterFactory  # noqa: E402
from uav_crop_analysis.jobs import (  # noqa: E402
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    AnalysisJobService,
    AnalysisResult,
    JobEventType,
    JobStatus,
    SemanticTilePipeline,
)
from uav_crop_analysis.jobs.worker import classify_worker_error  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_threshold_onnx(path: Path, size: int = 16) -> None:
    images = helper.make_tensor_value_info(
        "images", TensorProto.FLOAT, [1, 3, size, size]
    )
    logits = helper.make_tensor_value_info(
        "logits", TensorProto.FLOAT, [1, 3, size, size]
    )
    initializers = [
        numpy_helper.from_array(np.asarray([0], dtype=np.int64), name="red_index"),
        numpy_helper.from_array(np.asarray([10.0], dtype=np.float32), name="ten"),
        numpy_helper.from_array(np.asarray([-10.0], dtype=np.float32), name="minus_ten"),
        numpy_helper.from_array(np.asarray([0.0], dtype=np.float32), name="zero"),
    ]
    nodes = [
        helper.make_node("Gather", ["images", "red_index"], ["red"], axis=1),
        helper.make_node("Mul", ["red", "ten"], ["weed"]),
        helper.make_node("Mul", ["red", "minus_ten"], ["negative_red"]),
        helper.make_node("Add", ["negative_red", "ten"], ["background"]),
        helper.make_node("Mul", ["red", "zero"], ["crop"]),
        helper.make_node("Concat", ["background", "crop", "weed"], ["logits"], axis=1),
    ]
    graph = helper.make_graph(nodes, "threshold-semantic", [images], [logits], initializers)
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 17)],
        producer_name="uav-crop-analysis-tests",
    )
    onnx.checker.check_model(model)
    onnx.save(model, path)


def _write_registry(tmp_path: Path) -> Path:
    model_path = tmp_path / "threshold.onnx"
    _write_threshold_onnx(model_path)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact_root": ".",
                "models": [
                    {
                        "id": "threshold-semantic",
                        "version": "1",
                        "family": "threshold",
                        "task": "semantic_segmentation",
                        "status": "test",
                        "class_names": ["background", "crop", "weed"],
                        "target_classes": ["crop", "weed"],
                        "input_size": [16, 16],
                        "dataset_version": "unit",
                        "runtime": {
                            "kind": "onnxruntime",
                            "output_adapter": "semantic_logits",
                        },
                        "preprocessing": {
                            "color_space": "rgb",
                            "resize_mode": "stretch",
                            "interpolation": "bilinear",
                            "value_scale": 0.00392156862745098,
                            "mean": [0.0, 0.0, 0.0],
                            "std": [1.0, 1.0, 1.0],
                        },
                        "artifacts": [
                            {
                                "role": "unit",
                                "path": model_path.name,
                                "sha256": _sha256(model_path),
                                "format": "onnx",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return registry_path


def _config(
    tmp_path: Path,
    registry_path: Path,
    image_path: Path,
    output_name: str,
) -> AnalysisJobConfig:
    return AnalysisJobConfig(
        mission_id="mission-worker",
        model_id="threshold-semantic",
        artifact_role="unit",
        registry_path=registry_path,
        inputs=(AnalysisInput("image-1", image_path),),
        output_root=tmp_path / output_name,
        tile_size=16,
        overlap=4,
    )


def test_worker_process_matches_single_process_pipeline(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    image = np.zeros((20, 24, 3), dtype=np.uint8)
    image[:, 12:, 0] = 255
    image_path = tmp_path / "image.png"
    Image.fromarray(image, mode="RGB").save(image_path)

    direct_config = _config(tmp_path, registry_path, image_path, "direct")
    direct_job = AnalysisJob("job-direct", direct_config).start()
    registry = ModelRegistry.from_file(registry_path)
    segmenter = SegmenterFactory(registry).load_semantic(
        "threshold-semantic", "unit"
    )
    direct_result = SemanticTilePipeline(segmenter).run(
        direct_job,
        lambda _stage, _progress, _detail: None,
        lambda: False,
    )

    repository = SQLiteAnalysisJobRepository(tmp_path / "app.db")
    service = AnalysisJobService(repository)
    submitted = service.submit(
        _config(tmp_path, registry_path, image_path, "worker"),
        "job-worker",
    )
    service.start(submitted.job_id)
    completed = service.wait(submitted.job_id, timeout=30)

    assert completed.status is JobStatus.COMPLETED
    assert completed.result is not None
    direct_probability = np.load(
        direct_result.artifact_dir / "image-1.weed_probability.npy"
    )
    worker_probability = np.load(
        completed.result.artifact_dir / "image-1.weed_probability.npy"
    )
    np.testing.assert_allclose(worker_probability, direct_probability, atol=1e-6)
    assert repository.list_events(submitted.job_id)[-1].status is JobStatus.COMPLETED


def test_process_cancel_then_retry_uses_new_attempt_directory(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    image_path = tmp_path / "cancel.png"
    Image.fromarray(np.zeros((128, 128, 3), dtype=np.uint8), mode="RGB").save(image_path)
    repository = SQLiteAnalysisJobRepository(tmp_path / "cancel.db")
    service = AnalysisJobService(repository)
    job = service.submit(
        _config(tmp_path, registry_path, image_path, "cancel-results"),
        "job-cancel-process",
    )
    service.start(job.job_id)
    service.cancel(job.job_id)

    cancelled = service.wait(job.job_id, timeout=30)

    assert cancelled.status is JobStatus.CANCELLED
    assert not (cancelled.config.output_root / job.job_id / "attempt-0001").exists()
    queued = service.retry(job.job_id, start=False)
    assert queued.status is JobStatus.QUEUED
    service.start(job.job_id)
    completed = service.wait(job.job_id, timeout=30)
    assert completed.status is JobStatus.COMPLETED
    assert completed.attempt == 2
    assert completed.result is not None
    assert completed.result.artifact_dir.name == "attempt-0002"


def test_worker_returns_structured_file_and_memory_errors(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    repository = SQLiteAnalysisJobRepository(tmp_path / "failure.db")
    service = AnalysisJobService(repository)
    missing_path = tmp_path / "missing.png"
    job = service.submit(
        _config(tmp_path, registry_path, missing_path, "failure-results"),
        "job-file-error",
    )
    service.start(job.job_id)

    failed = service.wait(job.job_id, timeout=30)
    invalid_model_config = AnalysisJobConfig(
        mission_id="mission-worker",
        model_id="missing-model",
        artifact_role="unit",
        registry_path=registry_path,
        inputs=(AnalysisInput("image-1", missing_path),),
        output_root=tmp_path / "model-failure-results",
        tile_size=16,
        overlap=4,
    )
    model_job = service.submit(invalid_model_config, "job-model-error")
    service.start(model_job.job_id)
    model_failed = service.wait(model_job.job_id, timeout=30)
    out_of_memory = classify_worker_error(MemoryError("simulated out of memory"))

    assert failed.status is JobStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "pipeline_execution_error"
    assert model_failed.status is JobStatus.FAILED
    assert model_failed.error is not None
    assert model_failed.error.code == "model_manifest_error"
    assert out_of_memory["code"] == "job_out_of_memory"
    assert out_of_memory["retryable"] is True


def test_many_image_job_keeps_parent_polling_and_coalesces_progress(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    inputs = []
    for index in range(18):
        image_path = tmp_path / f"stress-{index:02d}.png"
        image = np.zeros((20, 20, 3), dtype=np.uint8)
        image[:, index % 20 :, 0] = 255
        Image.fromarray(image, mode="RGB").save(image_path)
        inputs.append(AnalysisInput(f"image-{index:02d}", image_path))
    config = AnalysisJobConfig(
        mission_id="mission-stress",
        model_id="threshold-semantic",
        artifact_role="unit",
        registry_path=registry_path,
        inputs=tuple(inputs),
        output_root=tmp_path / "stress-results",
        tile_size=16,
        overlap=4,
    )
    repository = SQLiteAnalysisJobRepository(tmp_path / "stress.db")
    service = AnalysisJobService(repository)
    job = service.submit(config, "job-stress")
    started = time.perf_counter()
    service.start(job.job_id)
    start_returned_ms = (time.perf_counter() - started) * 1000
    parent_ticks = 0
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        current = service.poll(job.job_id)
        parent_ticks += 1
        if current.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
            break
        time.sleep(0.002)
    completed = service.wait(job.job_id, timeout=30)
    progress_events = [
        event
        for event in repository.list_events(job.job_id)
        if event.event_type.value == "progress"
    ]

    assert completed.status is JobStatus.COMPLETED
    assert start_returned_ms < 1000
    assert parent_ticks > 1
    assert completed.result is not None
    assert len(completed.result.image_summaries) == 18
    assert len(progress_events) < 18 * 4


def test_dispatcher_respects_worker_capacity(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    image_path = tmp_path / "queue.png"
    Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8), mode="RGB").save(image_path)
    repository = SQLiteAnalysisJobRepository(tmp_path / "queue.db")
    service = AnalysisJobService(repository, max_workers=1)
    config = _config(tmp_path, registry_path, image_path, "queue-results")
    first = service.submit(config, "job-queue-1")
    second = service.submit(config, "job-queue-2")

    dispatched = service.dispatch_queued()

    assert [job.job_id for job in dispatched] == [first.job_id]
    queued_second = repository.get(second.job_id)
    assert queued_second is not None
    assert queued_second.status is JobStatus.QUEUED
    assert service.wait(first.job_id, timeout=30).status is JobStatus.COMPLETED
    assert [job.job_id for job in service.dispatch_queued()] == [second.job_id]
    assert service.wait(second.job_id, timeout=30).status is JobStatus.COMPLETED


def test_dispatcher_retires_completed_handle_before_starting_next_job(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    image_path = tmp_path / "retire.png"
    Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8), mode="RGB").save(image_path)

    class CompletedHandle:
        def __init__(self) -> None:
            self.closed = False

        def close(self, timeout: float = 1.0) -> None:
            del timeout
            self.closed = True

    class PendingHandle:
        def close(self, timeout: float = 1.0) -> None:
            del timeout

    class FakeWorker:
        def start(self, _job: AnalysisJob) -> PendingHandle:
            return PendingHandle()

    repository = SQLiteAnalysisJobRepository(tmp_path / "retire.db")
    service = AnalysisJobService(repository, worker=cast(Any, FakeWorker()), max_workers=1)
    config = _config(tmp_path, registry_path, image_path, "retire-results")
    first = service.submit(config, "job-retire-1")
    second = service.submit(config, "job-retire-2")
    completed = first.start().complete(
        AnalysisResult(tmp_path / "artifacts", "a" * 64, (), {})
    )
    repository.save(completed, completed.event(JobEventType.COMPLETED, "completed"))
    stale_handle = CompletedHandle()
    service._handles[first.job_id] = cast(Any, stale_handle)

    dispatched = service.dispatch_queued()

    assert stale_handle.closed
    assert [job.job_id for job in dispatched] == [second.job_id]
    running_second = repository.get(second.job_id)
    assert running_second is not None
    assert running_second.status is JobStatus.RUNNING
