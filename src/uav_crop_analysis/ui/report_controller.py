"""Background controller for portable report export."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _ReportWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self._action = action

    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(self._action())
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)


class ReportExportController(QObject):
    busyChanged = Signal(bool)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _ReportWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def start(self, action: Callable[[], object]) -> bool:
        if self.is_busy:
            return False
        thread = QThread(self)
        worker = _ReportWorker(action)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
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
