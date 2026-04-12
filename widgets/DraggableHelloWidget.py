from PySide6.QtWidgets import QLabel, QVBoxLayout

from .DraggableWidget import DraggableWidget


class DraggableHelloWidget(DraggableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet(
            "background-color: rgba(40, 40, 40, 200);"
            "color: white;"
            "border: 1px solid #666;"
            "border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(QLabel("hello world"))

