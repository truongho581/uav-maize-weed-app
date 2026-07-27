"""Single-operation background controller for geospatial work."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from uav_crop_analysis.geospatial import ProgressCallback


SpatialAction = Callable[[ProgressCallback], object]


class _SpatialWorker(QObject):
    completed = Signal(str, object)
    failed = Signal(str, str)
    progress = Signal(float, str)

    def __init__(self, operation: str, action: SpatialAction) -> None:
        super().__init__()
        self._operation = operation
        self._action = action

    @Slot()
    def run(self) -> None:
        try:
            value = self._action(self.progress.emit)
            self.completed.emit(self._operation, value)
        except Exception as exc:
            self.failed.emit(self._operation, str(exc) or type(exc).__name__)


class SpatialTaskController(QObject):
    busyChanged = Signal(bool)
    completed = Signal(str, object)
    failed = Signal(str, str)
    progress = Signal(float, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _SpatialWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def start(self, operation: str, action: SpatialAction) -> bool:
        if self.is_busy:
            return False
        thread = QThread(self)
        worker = _SpatialWorker(operation, action)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.completed.connect(self.completed)
        worker.failed.connect(self.failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear)
        self._thread = thread
        self._worker = worker
        self.busyChanged.emit(True)
        thread.start()
        return True

    @Slot()
    def _clear(self) -> None:
        self._thread = None
        self._worker = None
        self.busyChanged.emit(False)

    def shutdown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
