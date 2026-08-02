"""Reusable pan, zoom, navigation, and measurement graphics view."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QNativeGestureEvent,
    QPen,
    QPolygonF,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsView,
)


@dataclass(frozen=True, slots=True)
class _ViewState:
    transform: QTransform
    horizontal: int
    vertical: int


class PanZoomGraphicsView(QGraphicsView):
    pointerMoved = Signal(float, float)
    zoomChanged = Signal(float)
    measurementChanged = Signal(str, object)
    historyChanged = Signal(bool, bool)

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self._tool = "pan"
        self._measure_points: list[QPointF] = []
        self._measure_items: list[object] = []
        self._history: list[_ViewState] = []
        self._history_index = -1
        self._native_zoom_active = False
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    @property
    def tool(self) -> str:
        return self._tool

    def set_tool(self, tool: str) -> None:
        if tool not in {"pan", "point", "distance", "area"}:
            raise ValueError(f"unknown viewer tool: {tool}")
        self.clear_measurements()
        self._tool = tool
        self.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag
            if tool == "pan"
            else QGraphicsView.DragMode.NoDrag
        )
        self.viewport().setCursor(
            Qt.CursorShape.OpenHandCursor if tool == "pan" else Qt.CursorShape.CrossCursor
        )

    def clear_measurements(self) -> None:
        scene = self.scene()
        if scene is not None:
            for item in self._measure_items:
                scene.removeItem(item)  # type: ignore[arg-type]
        self._measure_items.clear()
        self._measure_points.clear()
        self.measurementChanged.emit("clear", ())

    def zoom_by(
        self,
        factor: float,
        *,
        anchor: QPointF | None = None,
        remember: bool = True,
    ) -> None:
        current = self.transform().m11()
        target = current * factor
        if 0.03 <= target <= 80.0:
            if anchor is None:
                self.scale(factor, factor)
            else:
                anchor_point = anchor.toPoint()
                scene_before = self.mapToScene(anchor_point)
                previous_anchor = self.transformationAnchor()
                self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
                self.scale(factor, factor)
                scene_after = self.mapToScene(anchor_point)
                delta = scene_after - scene_before
                self.translate(delta.x(), delta.y())
                self.setTransformationAnchor(previous_anchor)
            self.zoomChanged.emit(self.transform().m11())
            if remember:
                self.remember_view()

    def notify_zoom(self) -> None:
        self.zoomChanged.emit(self.transform().m11())

    def remember_view(self) -> None:
        state = _ViewState(
            QTransform(self.transform()),
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value(),
        )
        if self._history_index >= 0 and self._same_state(self._history[self._history_index], state):
            return
        del self._history[self._history_index + 1 :]
        self._history.append(state)
        if len(self._history) > 30:
            self._history.pop(0)
        self._history_index = len(self._history) - 1
        self.historyChanged.emit(self._history_index > 0, False)

    def previous_view(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._restore_state(self._history[self._history_index])

    def next_view(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._restore_state(self._history[self._history_index])

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        factor = _wheel_zoom_factor(event)
        if factor is None:
            if event.phase() is Qt.ScrollPhase.ScrollEnd:
                self.remember_view()
            event.accept()
            return
        remember = event.phase() in {
            Qt.ScrollPhase.NoScrollPhase,
            Qt.ScrollPhase.ScrollEnd,
        }
        self.zoom_by(factor, anchor=event.position(), remember=remember)
        event.accept()

    def event(self, event: QEvent) -> bool:
        if self._handle_native_gesture(event):
            return True
        return super().event(event)

    def viewportEvent(self, event: QEvent) -> bool:  # noqa: N802
        if self._handle_native_gesture(event):
            return True
        return super().viewportEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton and self._tool != "pan":
            if self._tool == "area" and len(self._measure_points) >= 3:
                self._finish_area()
            else:
                self.clear_measurements()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._tool != "pan":
            point = self.mapToScene(event.position().toPoint())
            self._add_measurement_point(point)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if self._tool == "pan" and event.button() == Qt.MouseButton.LeftButton:
            self.remember_view()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._tool == "area" and len(self._measure_points) >= 2:
            point = self.mapToScene(event.position().toPoint())
            self._add_measurement_point(point)
            self._finish_area()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        scene_position = self.mapToScene(event.position().toPoint())
        self.pointerMoved.emit(scene_position.x(), scene_position.y())
        super().mouseMoveEvent(event)

    def _add_measurement_point(self, point: QPointF) -> None:
        if self._tool == "point":
            self.clear_measurements()
        marker = QGraphicsEllipseItem(-4, -4, 8, 8)
        marker.setPos(point)
        marker.setPen(QPen(QColor("#FFFFFF"), 1))
        marker.setBrush(QBrush(QColor("#D64A3A")))
        marker.setFlag(marker.GraphicsItemFlag.ItemIgnoresTransformations)
        marker.setZValue(10)
        self.scene().addItem(marker)
        self._measure_items.append(marker)
        if self._tool == "point":
            self.measurementChanged.emit("point", (point.x(), point.y()))
            return
        self._measure_points.append(point)
        if self._tool == "distance" and len(self._measure_points) == 2:
            first, second = self._measure_points
            line = QGraphicsLineItem(first.x(), first.y(), second.x(), second.y())
            line.setPen(_measurement_pen())
            line.setZValue(10)
            self.scene().addItem(line)
            self._measure_items.append(line)
            distance = hypot(second.x() - first.x(), second.y() - first.y())
            self.measurementChanged.emit("distance", distance)
            self._measure_points.clear()

    def _finish_area(self) -> None:
        polygon = QGraphicsPolygonItem(QPolygonF(self._measure_points))
        polygon.setPen(_measurement_pen())
        polygon.setBrush(QBrush(QColor(214, 74, 58, 45)))
        polygon.setZValue(10)
        self.scene().addItem(polygon)
        self._measure_items.append(polygon)
        area = 0.0
        points = self._measure_points
        for index, point in enumerate(points):
            following = points[(index + 1) % len(points)]
            area += point.x() * following.y() - following.x() * point.y()
        self.measurementChanged.emit("area", abs(area) / 2)
        self._measure_points.clear()

    def _restore_state(self, state: _ViewState) -> None:
        self.setTransform(state.transform)
        self.horizontalScrollBar().setValue(state.horizontal)
        self.verticalScrollBar().setValue(state.vertical)
        self.notify_zoom()
        self.historyChanged.emit(
            self._history_index > 0,
            self._history_index < len(self._history) - 1,
        )

    def _handle_native_gesture(self, event: QEvent) -> bool:
        if not isinstance(event, QNativeGestureEvent):
            return False
        gesture = event.gestureType()
        if gesture is Qt.NativeGestureType.BeginNativeGesture:
            self._native_zoom_active = True
            event.accept()
            return True
        if gesture is Qt.NativeGestureType.EndNativeGesture:
            if self._native_zoom_active:
                self.remember_view()
            self._native_zoom_active = False
            event.accept()
            return True
        if gesture is not Qt.NativeGestureType.ZoomNativeGesture:
            return False
        factor = max(0.5, min(2.0, 1.0 + event.value()))
        self.zoom_by(factor, anchor=event.position(), remember=False)
        self._native_zoom_active = True
        event.accept()
        return True

    @staticmethod
    def _same_state(left: _ViewState, right: _ViewState) -> bool:
        return (
            left.transform == right.transform
            and left.horizontal == right.horizontal
            and left.vertical == right.vertical
        )


def _measurement_pen() -> QPen:
    pen = QPen(QColor("#D64A3A"), 2)
    pen.setCosmetic(True)
    return pen


def _wheel_zoom_factor(event: QWheelEvent) -> float | None:
    angle_delta = event.angleDelta().y()
    if angle_delta:
        return max(0.5, min(2.0, 1.2 ** (angle_delta / 120.0)))
    pixel_delta = event.pixelDelta().y()
    if pixel_delta:
        return max(0.5, min(2.0, 1.0025**pixel_delta))
    return None
