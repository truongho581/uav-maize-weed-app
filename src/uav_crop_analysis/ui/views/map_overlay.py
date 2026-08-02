"""Satellite field-map preview and dialog for georeferenced spatial products."""

from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from PySide6.QtCore import QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from rasterio.warp import transform

from uav_crop_analysis.geospatial import SpatialProduct
from uav_crop_analysis.ui.icons import configure_icon_button


_LEAFLET_VERSION = "1.9.4"
_LEAFLET_CSS = f"https://unpkg.com/leaflet@{_LEAFLET_VERSION}/dist/leaflet.css"
_LEAFLET_JS = f"https://unpkg.com/leaflet@{_LEAFLET_VERSION}/dist/leaflet.js"
_ESRI_SATELLITE_TILES = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
_ESRI_ATTRIBUTION = "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"
_GOOGLE_KEY_SETTING = "maps/google_api_key"
_GOOGLE_KEY_ENV = "UAV_CROP_GOOGLE_MAPS_API_KEY"


class OrthomosaicMapPreview(QWidget):
    """Small satellite field map that opens the full map when clicked."""

    openRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MapPreviewPanel")
        self.setMinimumHeight(168)
        self.setMaximumHeight(190)
        self._orthomosaic: SpatialProduct | None = None
        self._heatmap: SpatialProduct | None = None
        self.web_view = _map_view(self)
        self.open_button = QPushButton(self)
        self.open_button.setObjectName("MapPreviewButton")
        self.open_button.setToolTip("Mở bản đồ thực địa")
        self.open_button.setAccessibleName("Mở bản đồ thực địa lớn")
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_button.clicked.connect(self.openRequested)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_view)
        self.clear()

    def clear(self, message: str = "Chọn ảnh ghép đã định vị địa lý") -> None:
        self._orthomosaic = None
        self._heatmap = None
        self.web_view.setHtml(_placeholder_html(message))
        self.open_button.setEnabled(False)

    def set_products(
        self,
        orthomosaic: SpatialProduct | None,
        heatmap: SpatialProduct | None = None,
    ) -> None:
        if orthomosaic is None or orthomosaic.raster is None:
            self.clear()
            return
        self._orthomosaic = orthomosaic
        self._heatmap = heatmap
        try:
            html = build_field_map_html(orthomosaic, heatmap, interactive=False)
        except (OSError, ValueError, RuntimeError) as exc:
            self.clear(str(exc) or "Không thể định vị ảnh ghép")
            return
        self.web_view.setHtml(html, _base_url(orthomosaic.preview_path))
        self.open_button.setEnabled(True)

    def reload(self) -> None:
        self.set_products(self._orthomosaic, self._heatmap)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.open_button.setGeometry(self.rect())
        self.open_button.raise_()


class OrthomosaicMapDialog(QDialog):
    """Large interactive satellite map with field and analysis layers."""

    providerChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bản đồ thực địa")
        self.setMinimumSize(900, 620)
        self.resize(1120, 760)
        self._orthomosaic: SpatialProduct | None = None
        self._heatmap: SpatialProduct | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top_bar = QFrame()
        top_bar.setObjectName("MapTopBar")
        heading = QHBoxLayout(top_bar)
        heading.setContentsMargins(12, 6, 12, 6)
        heading.setSpacing(8)
        self.back_button = QPushButton()
        configure_icon_button(self.back_button, "arrow-left", "Quay lại")
        self.back_button.clicked.connect(self.close)
        heading.addWidget(self.back_button)
        title = QLabel("Bản đồ thực địa")
        title.setObjectName("PanelTitle")
        heading.addWidget(title)
        self.summary = QLabel()
        self.summary.setObjectName("MutedLabel")
        heading.addWidget(self.summary, 1)
        self.provider_button = QPushButton()
        configure_icon_button(
            self.provider_button,
            "settings-2",
            "Cấu hình Google Maps",
        )
        heading.addWidget(self.provider_button)
        self.fullscreen_button = QPushButton()
        configure_icon_button(self.fullscreen_button, "maximize-2", "Toàn màn hình")
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        heading.addWidget(self.fullscreen_button)
        self.close_button = QPushButton()
        configure_icon_button(self.close_button, "x", "Đóng bản đồ thực địa")
        self.close_button.clicked.connect(self.close)
        heading.addWidget(self.close_button)
        layout.addWidget(top_bar)
        self.web_view = _map_view(self)
        layout.addWidget(self.web_view, 1)

        self.provider_dialog = _MapProviderSettingsDialog(self)
        self.provider_button.clicked.connect(self.provider_dialog.open_for_edit)
        self.provider_dialog.saved.connect(self._provider_changed)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_button.setToolTip("Toàn màn hình")
        else:
            self.showFullScreen()
            self.fullscreen_button.setToolTip("Thoát toàn màn hình")

    def set_products(
        self,
        orthomosaic: SpatialProduct,
        heatmap: SpatialProduct | None = None,
    ) -> None:
        self._orthomosaic = orthomosaic
        self._heatmap = heatmap
        provider = "Google Maps Hybrid" if _google_maps_api_key() else "Esri World Imagery"
        self.summary.setText(f"{orthomosaic.path.name} · nền vệ tinh {provider}")
        self.web_view.setHtml(
            build_field_map_html(orthomosaic, heatmap, interactive=True),
            _base_url(orthomosaic.preview_path),
        )

    def _provider_changed(self) -> None:
        if self._orthomosaic is not None:
            self.set_products(self._orthomosaic, self._heatmap)
        self.providerChanged.emit()


class _MapProviderSettingsDialog(QDialog):
    saved = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Google Maps")
        self.setMinimumWidth(480)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setClearButtonEnabled(True)
        self.api_key.setPlaceholderText("Google Maps JavaScript API key")
        self.api_key.setAccessibleName("Google Maps API key")
        help_label = QLabel(
            '<a href="https://developers.google.com/maps/documentation/javascript/get-api-key">'
            "Tạo và giới hạn API key trong Google Cloud</a>"
        )
        help_label.setOpenExternalLinks(True)
        help_label.setObjectName("MutedLabel")
        note = QLabel(
            "Khi để trống, ứng dụng dùng ảnh vệ tinh Esri. API key được lưu trong "
            "thiết lập người dùng của máy này."
        )
        note.setWordWrap(True)
        note.setObjectName("MutedLabel")
        layout = QFormLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addRow("API key", self.api_key)
        layout.addRow("", help_label)
        layout.addRow("", note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button is not None:
            save_button.setText("Lưu")
        if cancel_button is not None:
            cancel_button.setText("Hủy")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def open_for_edit(self) -> None:
        self.api_key.setText(_stored_google_maps_api_key())
        self.open()

    def _save(self) -> None:
        settings = QSettings()
        key = self.api_key.text().strip()
        if key:
            settings.setValue(_GOOGLE_KEY_SETTING, key)
        else:
            settings.remove(_GOOGLE_KEY_SETTING)
        settings.sync()
        self.accept()
        self.saved.emit()


def build_field_map_html(
    orthomosaic: SpatialProduct,
    heatmap: SpatialProduct | None = None,
    *,
    interactive: bool,
    google_api_key: str | None = None,
) -> str:
    """Build a satellite field map with the true raster footprint in WGS84."""
    footprint = _raster_footprint(orthomosaic)
    key = _google_maps_api_key() if google_api_key is None else google_api_key.strip()
    if key:
        return _build_google_map_html(orthomosaic, heatmap, footprint, interactive, key)
    return _build_esri_map_html(orthomosaic, heatmap, footprint, interactive)


def build_leaflet_html(
    orthomosaic: SpatialProduct,
    heatmap: SpatialProduct | None = None,
    *,
    interactive: bool,
) -> str:
    """Compatibility wrapper for callers that explicitly require the fallback map."""
    return build_field_map_html(
        orthomosaic,
        heatmap,
        interactive=interactive,
        google_api_key="",
    )


def _build_esri_map_html(
    orthomosaic: SpatialProduct,
    heatmap: SpatialProduct | None,
    footprint: list[list[float]],
    interactive: bool,
) -> str:
    map_options = {
        "zoomControl": interactive,
        "attributionControl": True,
        "dragging": interactive,
        "scrollWheelZoom": interactive,
        "doubleClickZoom": interactive,
        "boxZoom": interactive,
        "keyboard": interactive,
        "zoomSnap": 0.25,
        "zoomDelta": 0.25,
    }
    center = _footprint_center(footprint)
    bounds = _footprint_bounds(footprint)
    layers = _leaflet_analysis_layers(orthomosaic, heatmap, bounds, interactive)
    max_zoom = 18
    attribution_style = (
        "font-size: 11px; line-height: 14px; padding: 0 4px;"
        if interactive
        else "font-size: 8px; line-height: 10px; padding: 0 2px;"
    )
    fallback = "Không tải được nền ảnh vệ tinh. Kiểm tra kết nối Internet."
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="{_LEAFLET_CSS}"
        onerror="document.getElementById('loading').textContent={json.dumps(fallback)}">
  <style>
    html, body, #map {{ width: 100%; height: 100%; margin: 0; background: #202622; }}
    #loading {{ position: absolute; inset: 0; display: grid; place-items: center;
      color: #d9e0dc; font: 13px sans-serif; text-align: center; padding: 18px; }}
    #map {{ position: absolute; inset: 0; }}
    .leaflet-control-layers {{ font: 13px sans-serif; border: 1px solid #d9dfdb;
      border-radius: 6px; box-shadow: 0 2px 8px #0003; padding: 5px; }}
    .leaflet-control-layers label {{ display: flex; align-items: center; gap: 8px;
      min-height: 28px; color: #1a211e; }}
    .leaflet-control-layers input {{ width: 16px; height: 16px; accent-color: #16724a; }}
    .leaflet-control-zoom a {{ color: #1a211e; border-color: #d9dfdb; }}
    .leaflet-control-attribution {{ color: #4f5b55; background: #fffffff0 !important;
      {attribution_style} }}
  </style>
</head>
<body>
  <div id="loading">Đang tải ảnh vệ tinh…</div>
  <div id="map"></div>
  <script src="{_LEAFLET_JS}"
          onerror="document.getElementById('loading').textContent={json.dumps(fallback)}"></script>
  <script>
    const map = L.map('map', {json.dumps(map_options)});
    L.tileLayer({json.dumps(_ESRI_SATELLITE_TILES)}, {{
      maxNativeZoom: 20,
      maxZoom: 22,
      attribution: {json.dumps(_ESRI_ATTRIBUTION)}
    }}).addTo(map);
    const footprint = L.polygon({json.dumps(footprint)}, {{
      color: '#19D37E', weight: 3, fillColor: '#19D37E', fillOpacity: 0.16
    }}).addTo(map);
    const centerPoint = L.circleMarker({json.dumps(center)}, {{
      radius: 5, color: '#FFFFFF', weight: 2, fillColor: '#E7473C', fillOpacity: 1
    }}).addTo(map);
    {layers}
    map.fitBounds(footprint.getBounds(), {{padding: [18, 18]}});
    if (map.getZoom() > {max_zoom}) map.setZoom({max_zoom});
    document.getElementById('loading').style.display = 'none';
  </script>
</body>
</html>"""


def _leaflet_analysis_layers(
    orthomosaic: SpatialProduct,
    heatmap: SpatialProduct | None,
    bounds: list[list[float]],
    interactive: bool,
) -> str:
    if not interactive:
        return ""
    declarations = [
        "const orthomosaic = L.imageOverlay("
        f"{json.dumps(_file_url(orthomosaic.preview_path))}, {json.dumps(bounds)}, "
        "{opacity: 0.82, interactive: false});"
    ]
    overlays = [
        "'Ranh giới ảnh ghép': footprint",
        "'Tâm ảnh ghép': centerPoint",
        "'Ảnh orthomosaic': orthomosaic",
    ]
    if heatmap is not None and heatmap.raster is not None and heatmap.preview_path.exists():
        heat_bounds = _footprint_bounds(_raster_footprint(heatmap))
        declarations.append(
            "const heatmap = L.imageOverlay("
            f"{json.dumps(_file_url(heatmap.preview_path))}, {json.dumps(heat_bounds)}, "
            "{opacity: 0.58, interactive: false});"
        )
        overlays.append("'Mật độ cỏ dại': heatmap")
    declarations.append(
        "L.control.layers({}, {" + ", ".join(overlays) + "}, {collapsed: false}).addTo(map);"
    )
    return "\n".join(declarations)


def _build_google_map_html(
    orthomosaic: SpatialProduct,
    heatmap: SpatialProduct | None,
    footprint: list[list[float]],
    interactive: bool,
    api_key: str,
) -> str:
    center = _footprint_center(footprint)
    bounds = _footprint_bounds(footprint)
    max_zoom = 20 if interactive else 19
    controls = "true" if interactive else "false"
    layer_panel = _google_layer_panel(heatmap) if interactive else ""
    analysis_layers = _google_analysis_layers(orthomosaic, heatmap, bounds, interactive)
    query = urlencode(
        {
            "key": api_key,
            "callback": "initMap",
            "v": "weekly",
            "loading": "async",
            "language": "vi",
            "region": "VN",
        }
    )
    fallback = "Không tải được Google Maps. Kiểm tra API key, billing và kết nối Internet."
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html, body, #map {{ width: 100%; height: 100%; margin: 0; background: #202622; }}
    #loading {{ position: absolute; inset: 0; display: grid; place-items: center;
      color: #d9e0dc; font: 13px sans-serif; text-align: center; padding: 18px; }}
    #map {{ position: absolute; inset: 0; }}
    #layers {{ position: absolute; z-index: 5; top: 10px; right: 10px; background: #fff;
      color: #202823; border: 1px solid #d9dfdb; border-radius: 6px;
      box-shadow: 0 2px 8px #0004; padding: 11px 13px;
      font: 13px sans-serif; display: grid; gap: 7px; }}
    #layers label {{ display: flex; align-items: center; gap: 8px; min-height: 28px;
      white-space: nowrap; }}
    #layers input {{ width: 16px; height: 16px; accent-color: #16724a; }}
  </style>
</head>
<body>
  <div id="loading">Đang tải Google Maps…</div>
  <div id="map"></div>
  {layer_panel}
  <script>
    window.gm_authFailure = () => {{
      document.getElementById('loading').textContent = {json.dumps(fallback)};
      document.getElementById('loading').style.display = 'grid';
    }};
    window.initMap = function() {{
      const map = new google.maps.Map(document.getElementById('map'), {{
        center: {json.dumps({"lat": center[0], "lng": center[1]})},
        zoom: 18,
        mapTypeId: 'hybrid',
        disableDefaultUI: {str(not interactive).lower()},
        zoomControl: {controls},
        mapTypeControl: {controls},
        streetViewControl: false,
        fullscreenControl: {controls},
        mapTypeControlOptions: {{mapTypeIds: ['satellite', 'hybrid', 'terrain']}}
      }});
      const footprintPath = {json.dumps([{"lat": item[0], "lng": item[1]} for item in footprint])};
      const footprint = new google.maps.Polygon({{
        paths: footprintPath, strokeColor: '#19D37E', strokeOpacity: 1, strokeWeight: 3,
        fillColor: '#19D37E', fillOpacity: 0.16, map
      }});
      const centerPoint = new google.maps.Circle({{
        center: {json.dumps({"lat": center[0], "lng": center[1]})}, radius: 0.35,
        strokeColor: '#FFFFFF', strokeWeight: 2, fillColor: '#E7473C', fillOpacity: 1, map
      }});
      {analysis_layers}
      const fieldBounds = new google.maps.LatLngBounds();
      footprintPath.forEach(point => fieldBounds.extend(point));
      map.fitBounds(fieldBounds, {64 if interactive else 18});
      google.maps.event.addListenerOnce(map, 'idle', () => {{
        if (map.getZoom() > {max_zoom}) map.setZoom({max_zoom});
      }});
      document.getElementById('loading').style.display = 'none';
    }};
  </script>
  <script async src="https://maps.googleapis.com/maps/api/js?{escape(query)}"
          onerror="document.getElementById('loading').textContent={json.dumps(fallback)}"></script>
</body>
</html>"""


def _google_layer_panel(heatmap: SpatialProduct | None) -> str:
    heatmap_control = (
        '<label><input id="heatmap-toggle" type="checkbox">Mật độ cỏ dại</label>'
        if heatmap is not None and heatmap.raster is not None and heatmap.preview_path.exists()
        else ""
    )
    return (
        '<div id="layers">'
        '<label><input id="footprint-toggle" type="checkbox" checked>Ranh giới ảnh ghép</label>'
        '<label><input id="center-toggle" type="checkbox" checked>Tâm ảnh ghép</label>'
        '<label><input id="orthomosaic-toggle" type="checkbox">Ảnh orthomosaic</label>'
        f"{heatmap_control}</div>"
    )


def _google_analysis_layers(
    orthomosaic: SpatialProduct,
    heatmap: SpatialProduct | None,
    bounds: list[list[float]],
    interactive: bool,
) -> str:
    if not interactive:
        return ""
    south_west, north_east = bounds
    google_bounds = {
        "south": south_west[0],
        "west": south_west[1],
        "north": north_east[0],
        "east": north_east[1],
    }
    lines = [
        "const orthomosaic = new google.maps.GroundOverlay("
        f"{json.dumps(_file_url(orthomosaic.preview_path))}, {json.dumps(google_bounds)}, "
        "{opacity: 0.82});",
        "document.getElementById('footprint-toggle').onchange = event => "
        "footprint.setMap(event.target.checked ? map : null);",
        "document.getElementById('center-toggle').onchange = event => "
        "centerPoint.setMap(event.target.checked ? map : null);",
        "document.getElementById('orthomosaic-toggle').onchange = event => "
        "orthomosaic.setMap(event.target.checked ? map : null);",
    ]
    if heatmap is not None and heatmap.raster is not None and heatmap.preview_path.exists():
        heat_bounds = _footprint_bounds(_raster_footprint(heatmap))
        heat_google_bounds = {
            "south": heat_bounds[0][0],
            "west": heat_bounds[0][1],
            "north": heat_bounds[1][0],
            "east": heat_bounds[1][1],
        }
        lines.extend(
            (
                "const heatmap = new google.maps.GroundOverlay("
                f"{json.dumps(_file_url(heatmap.preview_path))}, "
                f"{json.dumps(heat_google_bounds)}, {{opacity: 0.58}});",
                "document.getElementById('heatmap-toggle').onchange = event => "
                "heatmap.setMap(event.target.checked ? map : null);",
            )
        )
    return "\n".join(lines)


def _raster_footprint(product: SpatialProduct) -> list[list[float]]:
    raster = product.raster
    if raster is None:
        raise ValueError("Ảnh ghép chưa có CRS và phép biến đổi tọa độ")
    a, b, c, d, e, f = raster.transform
    pixel_corners = (
        (0.0, 0.0),
        (float(raster.width), 0.0),
        (float(raster.width), float(raster.height)),
        (0.0, float(raster.height)),
    )
    map_x = [a * column + b * row + c for column, row in pixel_corners]
    map_y = [d * column + e * row + f for column, row in pixel_corners]
    longitudes, latitudes = transform(raster.crs, "EPSG:4326", map_x, map_y)
    return [[latitude, longitude] for latitude, longitude in zip(latitudes, longitudes)]


def _footprint_center(footprint: list[list[float]]) -> list[float]:
    return [
        sum(point[0] for point in footprint) / len(footprint),
        sum(point[1] for point in footprint) / len(footprint),
    ]


def _footprint_bounds(footprint: list[list[float]]) -> list[list[float]]:
    latitudes = [point[0] for point in footprint]
    longitudes = [point[1] for point in footprint]
    return [[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]]


def _map_view(parent: QWidget) -> QWebEngineView:
    view = QWebEngineView(parent)
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    settings = view.settings()
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
        True,
    )
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
        True,
    )
    return view


def _google_maps_api_key() -> str:
    return os.environ.get(_GOOGLE_KEY_ENV, "").strip() or _stored_google_maps_api_key()


def _stored_google_maps_api_key() -> str:
    value = QSettings().value(_GOOGLE_KEY_SETTING, "")
    return str(value).strip() if value is not None else ""


def _file_url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path.resolve())).toString()


def _base_url(path: Path) -> QUrl:
    return QUrl.fromLocalFile(str(path.resolve().parent) + "/")


def _placeholder_html(message: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{height:100%;margin:0;background:#202622;color:#d9e0dc;font:12px sans-serif}}
body{{display:grid;place-items:center;text-align:center;padding:12px;box-sizing:border-box}}
</style></head><body>{escape(message)}</body></html>"""
