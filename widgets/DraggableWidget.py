from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QWidget

RESIZE_MARGIN = 8
CORNER_MARGIN = 16
MIN_SIZE = 40


class DraggableWidget(QWidget):
    """Base widget that can be dragged within its parent bounds.

    Args:
        resizable: If True, edges and corners can be dragged to resize the widget.
    """

    def __init__(self, parent=None, resizable=True):
        super().__init__(parent)
        self._dragging = False
        self._drag_offset = QPoint()
        self._resizable = resizable
        self._resize_edge = None
        self._resize_start_rect = QRect()
        self._resize_start_mouse = QPoint()

        if resizable:
            self.setMouseTracking(True)

    def _getResizeEdge(self, pos):
        """Return (left, right, top, bottom) booleans for which edges are active, or None."""
        r = self.rect()
        m = RESIZE_MARGIN
        cm = CORNER_MARGIN

        near_left = pos.x() < cm
        near_right = pos.x() > r.width() - cm
        near_top = pos.y() < cm
        near_bottom = pos.y() > r.height() - cm

        # Corners get a larger detection zone so diagonal resize is easy to grab.
        if near_left and near_top:
            return (True, False, True, False)
        if near_right and near_top:
            return (False, True, True, False)
        if near_left and near_bottom:
            return (True, False, False, True)
        if near_right and near_bottom:
            return (False, True, False, True)

        # Plain edges.
        left = pos.x() < m
        right = pos.x() > r.width() - m
        top = pos.y() < m
        bottom = pos.y() > r.height() - m
        if any([left, right, top, bottom]):
            return (left, right, top, bottom)
        return None

    def _cursorForEdge(self, edge):
        left, right, top, bottom = edge
        if (left and top) or (right and bottom):
            return Qt.CursorShape.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._resizable:
                edge = self._getResizeEdge(event.pos())
                if edge is not None:
                    self._resize_edge = edge
                    self._resize_start_rect = self.geometry()
                    self._resize_start_mouse = self.mapToParent(event.pos())
                    event.accept()
                    return
            self._dragging = True
            self._drag_offset = event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge is not None:
            mouse_pos = self.mapToParent(event.pos())
            delta = mouse_pos - self._resize_start_mouse
            left_edge, right_edge, top_edge, bottom_edge = self._resize_edge
            start = self._resize_start_rect
            parent = self.parentWidget()

            new_rect = QRect(start)

            # Horizontal axis.
            if left_edge:
                new_left = max(0, start.left() + delta.x())
                new_left = min(new_left, start.right() - MIN_SIZE + 1)
                new_rect.setLeft(new_left)
            elif right_edge:
                new_right = start.right() + delta.x()
                if parent:
                    new_right = min(new_right, parent.width() - 1)
                new_right = max(new_right, start.left() + MIN_SIZE - 1)
                new_rect.setRight(new_right)

            # Vertical axis (independent of horizontal).
            if top_edge:
                new_top = max(0, start.top() + delta.y())
                new_top = min(new_top, start.bottom() - MIN_SIZE + 1)
                new_rect.setTop(new_top)
            elif bottom_edge:
                new_bottom = start.bottom() + delta.y()
                if parent:
                    new_bottom = min(new_bottom, parent.height() - 1)
                new_bottom = max(new_bottom, start.top() + MIN_SIZE - 1)
                new_rect.setBottom(new_bottom)

            self.setGeometry(new_rect)
            event.accept()
            return

        if self._dragging:
            parent = self.parentWidget()
            if parent is None:
                return
            new_pos = self.mapToParent(event.pos() - self._drag_offset)
            x = max(0, min(new_pos.x(), parent.width() - self.width()))
            y = max(0, min(new_pos.y(), parent.height() - self.height()))
            self.move(x, y)
            event.accept()
            return

        if self._resizable:
            edge = self._getResizeEdge(event.pos())
            if edge is not None:
                self.setCursor(self._cursorForEdge(edge))
            else:
                self.unsetCursor()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._resize_edge = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
