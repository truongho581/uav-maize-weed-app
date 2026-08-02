"""Visual tokens shared by the Qt Widgets shell."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


COLORS = {
    "canvas": "#F4F6F5",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF1EF",
    "sidebar": "#18211D",
    "sidebar_hover": "#26332D",
    "text": "#1A211E",
    "muted": "#66716B",
    "line": "#D9DFDB",
    "brand": "#16724A",
    "brand_hover": "#115E3D",
    "brand_soft": "#E3F3EA",
    "info": "#236C8E",
    "warning": "#A35C00",
    "danger": "#B13A32",
    "focus": "#2684A6",
    "success": "#247A52",
    "success_soft": "#E6F4EC",
    "info_soft": "#E7F1F6",
    "warning_soft": "#FFF2D9",
    "danger_soft": "#FCE9E7",
    "viewer": "#252C29",
}

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
CONTROL_HEIGHT = 36
PRIMARY_CONTROL_HEIGHT = 40
ICON_SIZE = 18
PANEL_RADIUS = 6


def application_font() -> QFont:
    families = set(QFontDatabase.families())
    family = next(
        (
            candidate
            for candidate in (
                ".AppleSystemUIFont",
                "Segoe UI",
                "Noto Sans",
                "DejaVu Sans",
                "Arial",
            )
            if candidate in families
        ),
        "Arial",
    )
    font = QFont(family)
    font.setPointSize(10)
    return font


def stylesheet() -> str:
    return f"""
    QWidget {{
        color: {COLORS['text']};
        font-size: 10pt;
    }}
    QMainWindow, QDialog, #AppShell, #PageSurface, #OverviewScrollBody {{
        background: {COLORS['canvas']};
    }}
    QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
    #Sidebar {{
        background: {COLORS['sidebar']};
        border: none;
    }}
    #BrandTitle {{
        color: #FFFFFF;
        background: transparent;
        font-size: 15pt;
        font-weight: 700;
    }}
    #BrandSubtitle {{
        color: #A8B7AF;
        background: transparent;
        font-size: 9pt;
    }}
    QPushButton#NavButton {{
        color: #DDE7E2;
        background: transparent;
        border: none;
        border-radius: 6px;
        padding: 0;
        min-width: 44px;
        max-width: 44px;
        min-height: 44px;
        max-height: 44px;
    }}
    QPushButton#NavButton:hover {{ background: {COLORS['sidebar_hover']}; }}
    QPushButton#NavButton:checked {{
        color: #FFFFFF;
        background: {COLORS['brand']};
        font-weight: 600;
    }}
    QPushButton#NavButton[sidebarExpanded="true"] {{
        min-width: 200px;
        max-width: 200px;
        text-align: left;
        padding: 0 13px;
    }}
    QPushButton#SidebarActionButton {{
        color: #DDE7E2;
        background: transparent;
        border: none;
        border-radius: 6px;
        min-width: 44px;
        max-width: 44px;
        min-height: 44px;
        max-height: 44px;
        padding: 0;
    }}
    QPushButton#SidebarActionButton:hover {{ background: {COLORS['sidebar_hover']}; }}
    QPushButton#SidebarActionButton:focus {{
        border: 2px solid #7BC5A2;
        padding: 0;
    }}
    QPushButton#SidebarActionButton[sidebarExpanded="true"] {{
        min-width: 200px;
        max-width: 200px;
        text-align: left;
        padding: 0 13px;
    }}
    QLabel#PageTitle {{ font-size: 24px; font-weight: 600; }}
    QLabel#PanelTitle {{ font-size: 16px; font-weight: 600; }}
    QLabel#SectionTitle {{ font-size: 14px; font-weight: 600; }}
    QLabel#MutedLabel, QLabel#MapStatusLabel {{ color: {COLORS['muted']}; }}
    QLabel#MetricLabel {{ color: {COLORS['muted']}; font-size: 10.5pt; font-weight: 500; }}
    QLabel#MetricValue {{ font-size: 26px; font-weight: 600; }}
    QLabel#CompactMetricValue {{ font-size: 16px; font-weight: 600; }}
    QWidget#InspectorPanel QLabel#InspectorValue {{ font-size: 10.5pt; font-weight: 500; }}
    QLabel#ViewerTitle {{ font-weight: 600; }}
    QLabel#NorthIndicator {{
        color: {COLORS['text']};
        background: {COLORS['surface_alt']};
        border: 1px solid {COLORS['line']};
        border-radius: 4px;
        padding: 5px 8px;
        font-weight: 700;
    }}
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: 5px;
        padding: 7px 10px;
        min-height: 20px;
        selection-background-color: {COLORS['brand']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 2px solid {COLORS['focus']}; padding: 6px 9px;
    }}
    QPushButton {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: 5px;
        padding: 7px 12px;
        min-height: 20px;
    }}
    QPushButton:hover {{ background: {COLORS['surface_alt']}; }}
    QPushButton:focus {{ border: 2px solid {COLORS['focus']}; padding: 6px 11px; }}
    QPushButton:pressed {{ background: #E3E8E5; }}
    QPushButton:disabled {{ color: #87918C; background: #EDF0EE; border-color: #DDE2DF; }}
    QPushButton#IconButton, QToolButton#IconButton {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: 4px;
        padding: 0;
    }}
    QPushButton#IconButton:hover, QToolButton#IconButton:hover {{
        background: {COLORS['surface_alt']};
    }}
    QPushButton#IconButton:pressed, QToolButton#IconButton:pressed {{ background: #DDE4E0; }}
    QPushButton#IconButton:focus, QToolButton#IconButton:focus {{
        border: 2px solid {COLORS['focus']};
    }}
    QPushButton#IconButton:checked, QToolButton#IconButton:checked {{
        background: {COLORS['brand_soft']};
        border-color: {COLORS['brand']};
    }}
    QPushButton#IconButton:disabled, QToolButton#IconButton:disabled {{
        background: #EDF0EE;
        border-color: {COLORS['line']};
    }}
    QPushButton#PrimaryButton {{
        color: #FFFFFF;
        background: {COLORS['brand']};
        border-color: {COLORS['brand']};
        font-weight: 600;
        min-height: 24px;
    }}
    QPushButton#PrimaryButton:hover {{ background: {COLORS['brand_hover']}; }}
    QPushButton#PrimaryButton:pressed {{ background: #0D5033; }}
    QPushButton#DestructiveButton {{
        color: #FFFFFF; background: {COLORS['danger']}; border-color: {COLORS['danger']};
        font-weight: 600;
    }}
    QPushButton#PrimaryIconButton {{
        color: #FFFFFF;
        background: {COLORS['brand']};
        border: 1px solid {COLORS['brand']};
        border-radius: 4px;
        padding: 0;
    }}
    QPushButton#PrimaryIconButton:hover {{ background: {COLORS['brand_hover']}; }}
    QWidget#WorkspacePanel, QFrame#ViewerToolbar, QFrame#KpiCard, QFrame#ReportCard {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: {PANEL_RADIUS}px;
    }}
    QTabWidget::pane {{ border: none; background: transparent; }}
    QTabBar::tab {{
        color: {COLORS['muted']}; background: transparent; border: none;
        border-bottom: 2px solid transparent; padding: 9px 14px; min-width: 96px;
    }}
    QTabBar::tab:hover {{ color: {COLORS['text']}; background: #F0F4F2; }}
    QTabBar::tab:selected {{
        color: {COLORS['brand']}; border-bottom-color: {COLORS['brand']}; font-weight: 600;
    }}
    QTabBar#SegmentedTabs::tab, QTabBar#LayerTabs::tab {{
        background: {COLORS['surface_alt']}; border: 1px solid {COLORS['line']};
        border-right: none; border-bottom: 1px solid {COLORS['line']};
        padding: 8px 12px; min-width: 74px;
    }}
    QTabBar#SegmentedTabs::tab:first, QTabBar#LayerTabs::tab:first {{
        border-top-left-radius: 5px; border-bottom-left-radius: 5px;
    }}
    QTabBar#SegmentedTabs::tab:last, QTabBar#LayerTabs::tab:last {{
        border-right: 1px solid {COLORS['line']};
        border-top-right-radius: 5px; border-bottom-right-radius: 5px;
    }}
    QTabBar#SegmentedTabs::tab:selected, QTabBar#LayerTabs::tab:selected {{
        color: {COLORS['brand']}; background: {COLORS['brand_soft']};
        border-color: #9BCDB2; font-weight: 600;
    }}
    QTabBar#LayerTabs::tab {{ min-width: 64px; padding: 8px 9px; }}
    QTabBar#CompactContentTabs::tab {{ min-width: 62px; padding: 9px 8px; }}
    QCheckBox {{ spacing: 8px; min-height: 28px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; }}
    QSlider::groove:horizontal {{ height: 4px; background: #D7DEDA; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {COLORS['brand']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 16px; height: 16px; margin: -6px 0; background: {COLORS['surface']};
        border: 2px solid {COLORS['brand']}; border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{ background: {COLORS['brand_soft']}; }}
    QSplitter::handle {{ background: {COLORS['line']}; height: 4px; width: 4px; }}
    QSplitter::handle:hover {{ background: #AEBBB4; }}
    QTableView {{
        background: {COLORS['surface']};
        alternate-background-color: #F8FAF9;
        border: 1px solid {COLORS['line']};
        border-radius: 5px;
        gridline-color: {COLORS['line']};
        selection-background-color: {COLORS['brand_soft']};
        selection-color: {COLORS['text']};
    }}
    QTableView::item {{ padding: 7px 8px; border-bottom: 1px solid #E8ECE9; }}
    QTableView::item:hover {{ background: #F0F5F2; }}
    QTableView::item:selected {{ background: {COLORS['brand_soft']}; }}
    QHeaderView::section {{
        color: {COLORS['muted']};
        background: {COLORS['surface_alt']};
        border: none;
        border-bottom: 1px solid {COLORS['line']};
        padding: 8px;
        font-weight: 600;
    }}
    QFrame#Divider {{ background: {COLORS['line']}; border: none; }}
    QFrame#MessagePanel {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: 5px;
    }}
    QWidget#WarningBanner {{
        color: {COLORS['warning']}; background: {COLORS['warning_soft']};
        border: 1px solid #E8C788; border-radius: 5px;
    }}
    QLabel#CameraStatusBar {{
        color: {COLORS['muted']}; background: {COLORS['surface']};
        border-top: 1px solid {COLORS['line']}; padding: 6px 12px;
        font-size: 12px;
    }}
    QGraphicsView#ImageViewer {{
        background: {COLORS['viewer']};
        border: 1px solid {COLORS['line']};
        border-radius: 4px;
    }}
    QListWidget#LayerList {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: 4px;
        padding: 3px;
    }}
    QListWidget#LayerList::item {{ padding: 4px; }}
    QWidget#InspectorPanel {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: {PANEL_RADIUS}px;
    }}
    QWidget#FieldMapPanel {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: {PANEL_RADIUS}px;
    }}
    QWidget#MapPreviewPanel {{
        background: {COLORS['surface_alt']};
        border: 1px solid {COLORS['line']};
        border-radius: 4px;
    }}
    QLabel#ReportMapPreview {{
        color: {COLORS['muted']};
        background: {COLORS['surface_alt']};
        border: 1px solid {COLORS['line']};
        border-radius: 4px;
    }}
    QFrame#MapTopBar {{
        background: {COLORS['surface']}; border-bottom: 1px solid {COLORS['line']};
    }}
    QPushButton#MapPreviewButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 0;
    }}
    QPushButton#MapPreviewButton:hover {{ border-color: {COLORS['brand']}; }}
    QFrame#WeedSwatch {{ background: #D64A3A; border: 1px solid #A93228; }}
    QFrame#CropSwatch {{ background: #229C5B; border: 1px solid #14703E; }}
    QFrame#Maize2Swatch {{ background: #3EA35E; border: 1px solid #27733F; }}
    QFrame#Maize4Swatch {{ background: #3C80CF; border: 1px solid #285B96; }}
    QFrame#Maize6Swatch {{ background: #DE9A31; border: 1px solid #9C6C10; }}
    QLabel#StatusReady {{ color: {COLORS['brand']}; font-weight: 600; }}
    QLabel#StatusIncomplete {{ color: {COLORS['warning']}; font-weight: 600; }}
    QLabel#StatusEmpty {{ color: {COLORS['muted']}; font-weight: 600; }}
    QLabel#StatusFailed {{ color: {COLORS['danger']}; font-weight: 600; }}
    QLabel#StatusBadge {{ padding: 3px 8px; border-radius: 4px; font-weight: 600; }}
    QLabel#StatusBadge[statusKind="success"] {{ color: {COLORS['success']}; background: {COLORS['success_soft']}; }}
    QLabel#StatusBadge[statusKind="info"] {{ color: {COLORS['info']}; background: {COLORS['info_soft']}; }}
    QLabel#StatusBadge[statusKind="warning"] {{ color: {COLORS['warning']}; background: {COLORS['warning_soft']}; }}
    QLabel#StatusBadge[statusKind="danger"] {{ color: {COLORS['danger']}; background: {COLORS['danger_soft']}; }}
    QLabel#StatusBadge[statusKind="neutral"] {{ color: {COLORS['muted']}; background: {COLORS['surface_alt']}; }}
    QStatusBar {{
        color: {COLORS['muted']};
        background: {COLORS['surface']};
        border-top: 1px solid {COLORS['line']};
    }}
    QScrollArea {{ border: none; background: {COLORS['canvas']}; }}
    QProgressBar {{
        color: {COLORS['text']};
        background: {COLORS['surface_alt']};
        border: 1px solid {COLORS['line']};
        border-radius: 4px;
        text-align: center;
        min-height: 18px;
    }}
    QProgressBar::chunk {{ background: {COLORS['brand']}; border-radius: 3px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #B8C1BC; min-height: 32px; border-radius: 4px; }}
    QScrollBar::handle:vertical:hover {{ background: #8E9A94; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: #B8C1BC; min-width: 32px; border-radius: 4px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QToolTip {{ color: #FFFFFF; background: #26312C; border: none; padding: 5px; }}
    """
