from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from uav_crop_analysis.application import (
    AnalysisModelOption,
    AnalysisTask,
    ModelArtifactOption,
    ModelTestRequest,
    ModelTestService,
)
from uav_crop_analysis.application.model_test import _sample_indices
from uav_crop_analysis.ui.views import ModelTestWorkspacePage


class _Catalog:
    def list_models(
        self,
        _task: AnalysisTask | None = None,
    ) -> tuple[AnalysisModelOption, ...]:
        return ()

    def get(self, _model_id: str) -> AnalysisModelOption:
        raise AssertionError("not used")

    def ensure_artifact(self, _model_id: str, _artifact_role: str) -> None:
        return None


def _model(tmp_path: Path, task: AnalysisTask) -> AnalysisModelOption:
    checkpoint = tmp_path / f"{task.value}.pth"
    checkpoint.write_bytes(b"checkpoint")
    return AnalysisModelOption(
        model_id=f"model-{task.value}",
        version="7.2",
        family="segformer_b0" if task is AnalysisTask.SEMANTIC else "yolov8s_seg",
        task=task,
        status="production_default",
        runtime="pytorch" if task is AnalysisTask.SEMANTIC else "ultralytics",
        target_classes=("crop", "weed") if task is AnalysisTask.SEMANTIC else ("maize2",),
        artifacts=(ModelArtifactOption("best", checkpoint, True),),
    )


def test_video_sampling_covers_first_and_last_frames() -> None:
    assert _sample_indices(100, 4) == (0, 33, 66, 99)
    assert _sample_indices(3, 12) == (0, 1, 2)
    assert _sample_indices(1, 12) == (0,)


def test_model_test_accepts_an_independent_image(tmp_path: Path) -> None:
    source = tmp_path / "field.jpg"
    Image.new("RGB", (32, 24), (40, 120, 60)).save(source)
    service = ModelTestService(_Catalog(), tmp_path / "registry.json", tmp_path / "tests")

    inputs, media_kind = service._prepare_inputs(  # noqa: SLF001
        source,
        "model-test-fixture",
        lambda _value, _detail: None,
    )

    assert media_kind == "image"
    assert len(inputs) == 1
    assert inputs[0].source_path == source.resolve()


def test_model_test_page_emits_request_without_a_mission(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    page = ModelTestWorkspacePage()
    qtbot.addWidget(page)
    page.set_models(
        (_model(tmp_path, AnalysisTask.SEMANTIC),),
        (_model(tmp_path, AnalysisTask.MAIZE_INSTANCE),),
    )
    source = tmp_path / "field.png"
    Image.new("RGB", (32, 32), (60, 130, 45)).save(source)
    page.set_source(source)

    assert page.run_button.isEnabled()
    with qtbot.waitSignal(page.testRequested, timeout=1000) as signal:
        qtbot.mouseClick(page.run_button, Qt.MouseButton.LeftButton)

    request = signal.args[0]
    assert isinstance(request, ModelTestRequest)
    assert request.source_path == source.resolve()
    assert request.model_id.startswith("model-semantic")
