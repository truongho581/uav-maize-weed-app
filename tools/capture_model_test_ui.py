"""Render the independent model-check workspace with a real semantic result."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_OPENGL", "software")

    import torch
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from uav_crop_analysis.adapters import RegistryModelCatalog
    from uav_crop_analysis.application import (
        AnalysisTask,
        ModelTestRequest,
        ModelTestService,
    )
    from uav_crop_analysis.ui.shell import MainWindow
    from uav_crop_analysis.ui.tokens import application_font, stylesheet
    from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel

    project_root = Path(__file__).resolve().parents[1]
    registry = project_root / "models/model_inventory.json"
    catalog = RegistryModelCatalog(registry)
    service = ModelTestService(
        catalog,
        registry,
        args.output.parent / ".model-test-fixtures",
    )
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    result = service.run(
        ModelTestRequest(
            args.source,
            "segformer-b0-v72-maizemask-weedsgalore",
            "best_joint_seed_42",
            device=device,
        ),
        lambda _value, _detail: None,
    )

    class EmptyQuery:
        def list_missions(self) -> tuple[object, ...]:
            return ()

        def get_overview(self, _mission_id: str) -> None:
            return None

    app = QApplication([])
    app.setStyle("Fusion")
    app.setFont(application_font())
    app.setStyleSheet(stylesheet())
    window = MainWindow(
        MissionWorkspaceViewModel(EmptyQuery()),  # type: ignore[arg-type]
        model_test_service=service,
    )
    page = window.model_test_workspace
    page.set_models(
        catalog.list_models(AnalysisTask.SEMANTIC),
        catalog.list_models(AnalysisTask.MAIZE_INSTANCE),
    )
    page.set_source(args.source)
    page.set_result(result)
    window.pages.setCurrentWidget(page)
    window._set_nav(window.model_test_nav)
    window.resize(args.width, args.height)
    window.show()
    app.processEvents()
    QTest.qWait(300)
    page.viewer.fit_image()
    window.repaint()
    app.processEvents()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image = window.grab().toImage()
    if not image.save(str(args.output)):
        raise RuntimeError(f"failed to save screenshot: {args.output}")
    print(f"{args.output} {image.width()}x{image.height()}")
    window.close()
    app.quit()


if __name__ == "__main__":
    main()
