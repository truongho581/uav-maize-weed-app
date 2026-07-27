"""Background mission import orchestration for the desktop UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from uav_crop_analysis.adapters import load_mission_manifest
from uav_crop_analysis.application import ImportMissionData, ImportReport


class _ImportWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: ImportMissionData, manifest_path: Path) -> None:
        super().__init__()
        self._service = service
        self._manifest_path = manifest_path

    @Slot()
    def run(self) -> None:
        try:
            request = load_mission_manifest(self._manifest_path)
            self.completed.emit(self._service.execute(request))
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)


class MissionImportController(QObject):
    busyChanged = Signal(bool)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: ImportMissionData, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._thread: QThread | None = None
        self._worker: _ImportWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def start(self, manifest_path: str | Path) -> bool:
        if self.is_busy:
            return False
        thread = QThread(self)
        worker = _ImportWorker(
            self._service,
            Path(manifest_path).expanduser().resolve(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._complete)
        worker.failed.connect(self._fail)
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

    @Slot(object)
    def _complete(self, report: object) -> None:
        if isinstance(report, ImportReport):
            self.completed.emit(report)
        else:
            self.failed.emit("Import worker returned an invalid report")

    @Slot(str)
    def _fail(self, message: str) -> None:
        self.failed.emit(message)

    @Slot()
    def _clear(self) -> None:
        self._thread = None
        self._worker = None
        self.busyChanged.emit(False)

    def shutdown(self) -> None:
        thread = self._thread
        if thread is None:
            return
        thread.quit()
        thread.wait()
