"""Ports used by report generation and export."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from uav_crop_analysis.application import AnalysisModelOption
from uav_crop_analysis.reporting.models import MissionReport, ReportExport


class ReportModelCatalog(Protocol):
    def get(self, model_id: str) -> AnalysisModelOption: ...


class MissionReportExporter(Protocol):
    def export(self, report: MissionReport, output_root: Path) -> ReportExport: ...
