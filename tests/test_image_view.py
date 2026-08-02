from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QNativeGestureEvent, QPointingDevice, QWheelEvent
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsScene
from pytestqt.qtbot import QtBot

from uav_crop_analysis.ui.views.image_view import PanZoomGraphicsView


def test_point_marker_stays_at_clicked_scene_position(qtbot: QtBot) -> None:
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0, 0, 800, 500))
    view = PanZoomGraphicsView(scene)
    qtbot.addWidget(view)
    view.resize(500, 320)
    view.show()
    view.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    view.set_tool("point")
    viewport_point = QPoint(173, 119)
    expected = view.mapToScene(viewport_point)

    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=viewport_point)

    markers = [item for item in scene.items() if isinstance(item, QGraphicsEllipseItem)]
    assert len(markers) == 1
    assert abs(markers[0].pos().x() - expected.x()) < 0.01
    assert abs(markers[0].pos().y() - expected.y()) < 0.01


def test_touchpad_pixel_scroll_zooms_viewer(qtbot: QtBot) -> None:
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0, 0, 800, 500))
    view = PanZoomGraphicsView(scene)
    qtbot.addWidget(view)
    view.resize(500, 320)
    view.show()
    initial_zoom = view.transform().m11()
    anchor = QPoint(250, 160)
    scene_anchor = view.mapToScene(anchor)
    event = QWheelEvent(
        QPointF(anchor),
        QPointF(250, 160),
        QPoint(0, 48),
        QPoint(),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )

    view.wheelEvent(event)

    assert event.isAccepted()
    assert view.transform().m11() > initial_zoom
    mapped_anchor = view.mapToScene(anchor)
    assert abs(mapped_anchor.x() - scene_anchor.x()) <= 1.0
    assert abs(mapped_anchor.y() - scene_anchor.y()) <= 1.0


def test_native_trackpad_pinch_zooms_viewer(qtbot: QtBot) -> None:
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0, 0, 800, 500))
    view = PanZoomGraphicsView(scene)
    qtbot.addWidget(view)
    view.resize(500, 320)
    view.show()
    initial_zoom = view.transform().m11()
    position = QPointF(250, 160)
    event = QNativeGestureEvent(
        Qt.NativeGestureType.ZoomNativeGesture,
        QPointingDevice.primaryPointingDevice(),
        2,
        position,
        position,
        position,
        0.15,
        QPointF(),
        sequenceId=1,
    )

    assert view.viewportEvent(event)
    assert event.isAccepted()
    assert view.transform().m11() > initial_zoom
