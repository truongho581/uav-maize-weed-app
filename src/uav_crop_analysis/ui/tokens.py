"""Visual tokens shared by the Qt Widgets shell."""

from __future__ import annotations

from PySide6.QtGui import QFont


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
}


def application_font() -> QFont:
    font = QFont()
    font.setFamilies(["Inter", "Segoe UI", "SF Pro Text", "Noto Sans", "Arial"])
    font.setPointSize(10)
    return font


def stylesheet() -> str:
    return f"""
    QWidget {{
        color: {COLORS['text']};
        background: {COLORS['canvas']};
        font-size: 10pt;
    }}
    QMainWindow, #AppShell, #PageSurface, #OverviewScrollBody {{
        background: {COLORS['canvas']};
    }}
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
        border-radius: 5px;
        padding: 10px 12px;
        text-align: left;
        min-height: 22px;
    }}
    QPushButton#NavButton:hover {{ background: {COLORS['sidebar_hover']}; }}
    QPushButton#NavButton:checked {{
        color: #FFFFFF;
        background: {COLORS['brand']};
        font-weight: 600;
    }}
    QLabel#PageTitle {{
        font-size: 20pt;
        font-weight: 700;
    }}
    QLabel#SectionTitle {{
        font-size: 12pt;
        font-weight: 700;
    }}
    QLabel#MutedLabel, QLabel#MetricLabel {{ color: {COLORS['muted']}; }}
    QLabel#MetricValue {{ font-size: 17pt; font-weight: 700; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: 5px;
        padding: 7px 10px;
        min-height: 22px;
        selection-background-color: {COLORS['brand']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 2px solid {COLORS['focus']}; padding: 6px 9px;
    }}
    QPushButton {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['line']};
        border-radius: 5px;
        padding: 7px 12px;
        min-height: 22px;
    }}
    QPushButton:hover {{ background: {COLORS['surface_alt']}; }}
    QPushButton:focus {{ border: 2px solid {COLORS['focus']}; padding: 6px 11px; }}
    QPushButton:disabled {{ color: #98A19C; background: #EDF0EE; }}
    QPushButton#IconButton {{ padding: 7px; min-width: 22px; }}
    QPushButton#PrimaryButton {{
        color: #FFFFFF;
        background: {COLORS['brand']};
        border-color: {COLORS['brand']};
        font-weight: 600;
    }}
    QPushButton#PrimaryButton:hover {{ background: {COLORS['brand_hover']}; }}
    QTabBar::tab {{
        background: {COLORS['surface_alt']};
        border: 1px solid {COLORS['line']};
        padding: 8px 14px;
        min-width: 110px;
    }}
    QTabBar::tab:first {{ border-top-left-radius: 5px; border-bottom-left-radius: 5px; }}
    QTabBar::tab:last {{ border-top-right-radius: 5px; border-bottom-right-radius: 5px; }}
    QTabBar::tab:selected {{
        color: #FFFFFF;
        background: {COLORS['brand']};
        border-color: {COLORS['brand']};
        font-weight: 600;
    }}
    QTabBar#LayerTabs::tab {{ min-width: 76px; padding: 8px 10px; }}
    QCheckBox {{ spacing: 7px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; }}
    QSplitter::handle {{ background: {COLORS['line']}; height: 1px; width: 1px; }}
    QTableView {{
        background: {COLORS['surface']};
        alternate-background-color: #F8FAF9;
        border: 1px solid {COLORS['line']};
        border-radius: 5px;
        gridline-color: {COLORS['line']};
        selection-background-color: {COLORS['brand_soft']};
        selection-color: {COLORS['text']};
    }}
    QTableView::item {{ padding: 8px; border-bottom: 1px solid #E8ECE9; }}
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
    QGraphicsView#ImageViewer {{
        background: #202724;
        border: 1px solid {COLORS['line']};
        border-radius: 5px;
    }}
    QWidget#InspectorPanel {{
        background: {COLORS['surface']};
        border-left: 1px solid {COLORS['line']};
    }}
    QFrame#WeedSwatch {{ background: #D64A3A; border: 1px solid #A93228; }}
    QLabel#StatusReady {{ color: {COLORS['brand']}; font-weight: 600; }}
    QLabel#StatusIncomplete {{ color: {COLORS['warning']}; font-weight: 600; }}
    QLabel#StatusEmpty {{ color: {COLORS['muted']}; font-weight: 600; }}
    QLabel#StatusFailed {{ color: {COLORS['danger']}; font-weight: 600; }}
    QStatusBar {{
        color: {COLORS['muted']};
        background: {COLORS['surface']};
        border-top: 1px solid {COLORS['line']};
    }}
    QScrollArea {{ border: none; background: {COLORS['canvas']}; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #B8C1BC; min-height: 32px; border-radius: 5px; }}
    QToolTip {{ color: #FFFFFF; background: #26312C; border: none; padding: 5px; }}
    """
