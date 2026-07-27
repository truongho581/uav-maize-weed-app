"""Atomic JSON, CSV, and self-contained HTML mission report export."""

from __future__ import annotations

import base64
import csv
from dataclasses import asdict
from datetime import datetime
from html import escape
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from uav_crop_analysis.errors import ReportError
from uav_crop_analysis.inference.registry import sha256_file
from uav_crop_analysis.reporting import MissionReport, ReportExport


IMAGE_CSV_FIELDS = (
    "mission_id",
    "drone_id",
    "lane_index",
    "image_id",
    "sequence_index",
    "captured_at",
    "source_path",
    "latitude",
    "longitude",
    "relative_altitude_m",
    "camera_profile_id",
    "estimated_gsd_cm_px",
    "quality_status",
    "issue_codes",
    "analysis_job_id",
    "model_id",
    "model_version",
    "weed_coverage_percent",
    "estimated_weed_area_m2",
    "maize_status",
    "maize_instance_count",
    "maize_density_plants_m2",
    "maize_canopy_area_m2",
)


class PortableMissionReportExporter:
    def export(self, report: MissionReport, output_root: Path) -> ReportExport:
        root = Path(output_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        name = _available_name(
            root,
            f"{_safe_name(report.mission_id)}-report-"
            f"{report.generated_at.strftime('%Y%m%dT%H%M%S')}",
        )
        final = root / name
        staging = root / f".{name}.{uuid4().hex}.tmp"
        staging.mkdir(parents=True)
        try:
            report_json = staging / "report.json"
            image_csv = staging / "images.csv"
            report_html = staging / "report.html"
            report_json.write_text(
                json.dumps(
                    mission_report_to_dict(report),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            _write_image_csv(report, image_csv)
            report_html.write_text(_render_html(report), encoding="utf-8")
            checksums = tuple(
                (path.name, sha256_file(path))
                for path in (report_json, image_csv, report_html)
            )
            manifest_json = staging / "manifest.json"
            manifest_json.write_text(
                json.dumps(
                    {
                        "schema_version": report.schema_version,
                        "template_version": report.template_version,
                        "mission_id": report.mission_id,
                        "generated_at": report.generated_at.isoformat(),
                        "files": [
                            {"path": path, "sha256": checksum}
                            for path, checksum in checksums
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            staging.replace(final)
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, ReportError):
                raise
            raise ReportError(f"cannot export mission report: {exc}") from exc
        return ReportExport(
            directory=final,
            report_json=final / report_json.name,
            image_csv=final / image_csv.name,
            report_html=final / report_html.name,
            manifest_json=final / manifest_json.name,
            checksums=checksums,
        )


def mission_report_to_dict(report: MissionReport) -> dict[str, Any]:
    payload = _normalize(asdict(report))
    if not isinstance(payload, dict):
        raise ReportError("mission report serialization failed")
    payload["summary"] = {
        "image_count": report.image_count,
        "valid_image_count": report.valid_image_count,
        "issue_image_count": report.issue_image_count,
        "analyzed_image_count": report.analyzed_image_count,
        "mean_weed_coverage_percent": report.mean_weed_coverage_percent,
    }
    return payload


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _write_image_csv(report: MissionReport, path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=IMAGE_CSV_FIELDS)
        writer.writeheader()
        for image in report.images:
            row = _normalize(asdict(image))
            row["issue_codes"] = "|".join(image.issue_codes)
            writer.writerow({field: row.get(field) for field in IMAGE_CSV_FIELDS})


def _render_html(report: MissionReport) -> str:
    heatmap = next(
        (
            item.preview_path
            for item in report.spatial_products
            if item.kind == "weed_heatmap" and item.preview_path.is_file()
        ),
        None,
    )
    heatmap_html = ""
    if heatmap is not None:
        suffix = heatmap.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        encoded = base64.b64encode(heatmap.read_bytes()).decode("ascii")
        heatmap_html = (
            '<section><h2>Heatmap cỏ dại</h2>'
            f'<img class="heatmap" alt="Heatmap cỏ dại" '
            f'src="data:{mime};base64,{encoded}"></section>'
        )
    camera_rows = "".join(
        "<tr>"
        f"<td>{escape(item.profile_id)}</td>"
        f"<td>{escape(item.name)}</td>"
        f"<td>{escape(_optional(item.model))}</td>"
        f"<td>{_number(item.estimated_gsd_cm_px, 4)}</td>"
        f"<td>{escape(item.gsd_method)}</td>"
        "</tr>"
        for item in report.cameras
    ) or '<tr><td colspan="5">Chưa có camera profile.</td></tr>'
    drone_rows = "".join(
        "<tr>"
        f"<td>{escape(item.drone_id)}</td><td>{item.lane_index + 1}</td>"
        f"<td>{item.image_count}</td><td>{item.valid_image_count}</td>"
        f"<td>{item.issue_image_count}</td><td>{item.analyzed_image_count}</td>"
        f"<td>{item.gps_coverage * 100:.0f}%</td>"
        f"<td>{_number(item.mean_weed_coverage_percent, 2)}</td>"
        "</tr>"
        for item in report.drones
    )
    analysis_rows = "".join(
        "<tr>"
        f"<td>{escape(item.job_id)}</td><td>{escape(item.status)}</td>"
        f"<td>{escape(item.model_id)}</td><td>{escape(_optional(item.model_version))}</td>"
        f"<td>{item.image_count}</td><td>{item.weed_threshold:.2f}</td>"
        "</tr>"
        for item in report.analyses
    ) or '<tr><td colspan="6">Chưa có job phân tích.</td></tr>'
    spatial_rows = "".join(
        "<tr>"
        f"<td>{escape(item.product_id)}</td><td>{escape(item.kind)}</td>"
        f"<td>{escape(item.accuracy)}</td><td>{escape(_optional(item.crs))}</td>"
        f"<td>{escape(_optional(item.resolution))}</td>"
        f"<td>{escape(_optional(item.source_job_id))}</td>"
        "</tr>"
        for item in report.spatial_products
    ) or '<tr><td colspan="6">Chưa có sản phẩm không gian.</td></tr>'
    image_rows = "".join(
        "<tr>"
        f"<td>{escape(item.drone_id)}</td><td>{escape(item.image_id)}</td>"
        f"<td>{escape(item.captured_at.isoformat())}</td>"
        f"<td>{escape(item.quality_status)}</td>"
        f"<td>{_number(item.weed_coverage_percent, 2)}</td>"
        f"<td>{escape(item.maize_status)}</td>"
        "</tr>"
        for item in report.images
    ) or '<tr><td colspan="6">Mission chưa có ảnh.</td></tr>'
    limitations = "".join(f"<li>{escape(item)}</li>" for item in report.limitations)
    mean_weed = (
        f"{report.mean_weed_coverage_percent:.2f}%"
        if report.mean_weed_coverage_percent is not None
        else "—"
    )
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(report.mission_name)} - UAV Crop Analysis</title>
<style>
body{{font-family:Arial,sans-serif;color:#1a211e;margin:0;background:#f4f6f5}}
header{{background:#18211d;color:#fff;padding:24px 5%}}main{{max-width:1180px;margin:auto;padding:24px 5%}}
h1{{margin:0 0 6px;font-size:28px}}h2{{font-size:18px;margin-top:28px;border-bottom:1px solid #d9dfdb;padding-bottom:8px}}
.muted{{color:#66716b}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#d9dfdb;border:1px solid #d9dfdb}}
.metric{{background:#fff;padding:14px}}.metric strong{{display:block;font-size:22px;margin-top:5px}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid #e1e5e2;text-align:left}}th{{background:#eef1ef}}
.heatmap{{display:block;max-width:100%;max-height:620px;border:1px solid #d9dfdb}}code{{font-family:monospace}}
@media(max-width:760px){{.metrics{{grid-template-columns:1fr 1fr}}table{{display:block;overflow-x:auto}}}}
</style></head><body>
<header><h1>{escape(report.mission_name)}</h1><div>{escape(report.mission_id)}</div>
<div class="muted">Schema {report.schema_version} · Template {escape(report.template_version)} · {escape(report.generated_at.isoformat())}</div></header>
<main><section class="metrics">
<div class="metric">Ảnh<strong>{report.image_count}</strong></div>
<div class="metric">Ảnh hợp lệ<strong>{report.valid_image_count}</strong></div>
<div class="metric">Đã phân tích<strong>{report.analyzed_image_count}</strong></div>
<div class="metric">Weed trung bình<strong>{mean_weed}</strong></div></section>
<section><h2>Cấu hình nhiệm vụ</h2><p>Ba drone · cao độ {report.altitude_m:g} m · gimbal {report.gimbal_pitch_deg:g}° · overlap dọc {report.forward_overlap * 100:.0f}% · ngang {report.side_overlap * 100:.0f}% · {escape(report.capture_mode)}</p></section>
<section><h2>Theo drone</h2><table><thead><tr><th>Drone</th><th>Làn</th><th>Ảnh</th><th>Hợp lệ</th><th>Có lỗi</th><th>Đã AI</th><th>GPS</th><th>Weed TB (%)</th></tr></thead><tbody>{drone_rows}</tbody></table></section>
<section><h2>Camera và GSD</h2><table><thead><tr><th>Profile</th><th>Tên</th><th>Model</th><th>GSD ước tính (cm/px)</th><th>Phương pháp</th></tr></thead><tbody>{camera_rows}</tbody></table></section>
{heatmap_html}
<section><h2>Sản phẩm không gian</h2><table><thead><tr><th>ID</th><th>Loại</th><th>Độ chính xác</th><th>CRS</th><th>Độ phân giải</th><th>Job nguồn</th></tr></thead><tbody>{spatial_rows}</tbody></table></section>
<section><h2>Phân tích AI</h2><table><thead><tr><th>Job</th><th>Trạng thái</th><th>Model</th><th>Phiên bản</th><th>Ảnh</th><th>Ngưỡng weed</th></tr></thead><tbody>{analysis_rows}</tbody></table></section>
<section><h2>Chi tiết ảnh</h2><table><thead><tr><th>Drone</th><th>Ảnh</th><th>Thời gian</th><th>Chất lượng</th><th>Weed (%)</th><th>Maize</th></tr></thead><tbody>{image_rows}</tbody></table></section>
<section><h2>Giới hạn kết quả</h2><ul>{limitations}</ul></section>
</main></body></html>"""


def _optional(value: object | None) -> str:
    return "—" if value is None else str(value)


def _number(value: float | None, digits: int) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _safe_name(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() or character in "-_." else "-"
        for character in value
    ).strip("-.")
    return normalized or "mission"


def _available_name(root: Path, base: str) -> str:
    if not (root / base).exists():
        return base
    suffix = 2
    while (root / f"{base}-{suffix}").exists():
        suffix += 1
    return f"{base}-{suffix}"
