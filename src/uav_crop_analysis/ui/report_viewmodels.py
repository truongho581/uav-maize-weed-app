"""Framework-independent state for mission reporting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from uav_crop_analysis.reporting import MissionReport, MissionReportService, ReportExport


@dataclass(frozen=True, slots=True)
class ReportWorkspaceState:
    mission_id: str | None = None
    report: MissionReport | None = None
    export: ReportExport | None = None
    error_message: str | None = None


class ReportWorkspaceViewModel:
    def __init__(self, service: MissionReportService) -> None:
        self._service = service
        self.state = ReportWorkspaceState()

    def load(self, mission_id: str) -> ReportWorkspaceState:
        try:
            report = self._service.build(mission_id)
            self.state = ReportWorkspaceState(
                mission_id=mission_id,
                report=report,
                export=self.state.export if self.state.mission_id == mission_id else None,
            )
        except Exception as exc:
            self.state = ReportWorkspaceState(
                mission_id=mission_id,
                error_message=str(exc) or type(exc).__name__,
            )
        return self.state

    def export(self, output_root: Path) -> ReportExport:
        if self.state.mission_id is None:
            raise ValueError("Chưa chọn nhiệm vụ để xuất báo cáo.")
        exported = self._service.export(self.state.mission_id, output_root)
        self.state = ReportWorkspaceState(
            mission_id=self.state.mission_id,
            report=self.state.report,
            export=exported,
        )
        return exported
