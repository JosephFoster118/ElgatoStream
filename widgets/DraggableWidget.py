from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QWidget


class DraggableWidget(QWidget):
    """Base widget that can be dragged within its parent bounds."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._drag_offset = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            super().mouseMoveEvent(event)
            return

        parent = self.parentWidget()
        if parent is None:
            return

        new_pos = self.mapToParent(event.pos() - self._drag_offset)
        x = max(0, min(new_pos.x(), parent.width() - self.width()))
        y = max(0, min(new_pos.y(), parent.height() - self.height()))
        self.move(x, y)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
