from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
	QApplication,
	QFileDialog,
	QHBoxLayout,
	QLabel,
	QMainWindow,
	QPushButton,
	QSizePolicy,
	QVBoxLayout,
	QWidget,
)


class ImageCanvas(QWidget):
	selectionChanged = Signal(tuple)

	def __init__(self, parent: QWidget | None = None):
		super().__init__(parent)
		self.setMouseTracking(True)
		self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
		self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

		self.image_pixmap = QPixmap()
		self.image_display_rect = QRectF()
		self.selection_rect = QRectF()

		self.drag_mode = "none"
		self.active_handle = None
		self.drag_start_image = QPointF()
		self.start_rect = QRectF()

		self.zoom_factor = 1.0
		self.min_zoom = 0.1
		self.max_zoom = 40.0
		self.pan_offset = QPointF(0.0, 0.0)
		self.pan_drag_start = QPointF()
		self.pan_start_offset = QPointF()

		self.handle_names = ("tl", "tr", "bl", "br")
		self.handle_size = 12

	def hasImage(self) -> bool:
		return not self.image_pixmap.isNull()

	def loadImage(self, file_path: str) -> bool:
		pixmap = QPixmap(file_path)
		if pixmap.isNull():
			return False

		self.image_pixmap = pixmap
		self.selection_rect = QRectF()
		self.zoom_factor = 1.0
		self.pan_offset = QPointF(0.0, 0.0)
		self._updateImageDisplayRect()
		self.update()
		return True

	def clearSelection(self) -> None:
		self.selection_rect = QRectF()
		self.selectionChanged.emit(())
		self.update()

	def resizeEvent(self, event) -> None:
		super().resizeEvent(event)
		self._updateImageDisplayRect()

	def paintEvent(self, event) -> None:
		super().paintEvent(event)
		painter = QPainter(self)
		painter.fillRect(self.rect(), QColor(28, 28, 28))

		if not self.hasImage():
			painter.setPen(QColor(220, 220, 220))
			painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load an image to begin")
			return

		painter.drawPixmap(self.image_display_rect.toRect(), self.image_pixmap)

		if not self.selection_rect.isNull() and self.selection_rect.width() > 0 and self.selection_rect.height() > 0:
			rect_widget = self._imageRectToWidgetRect(self.selection_rect)

			painter.setPen(QPen(QColor(30, 255, 140), 2))
			painter.setBrush(QColor(30, 255, 140, 60))
			painter.drawRect(rect_widget)

			painter.setBrush(QColor(30, 255, 140))
			painter.setPen(Qt.PenStyle.NoPen)
			for handle_rect in self._handleRectsWidget(rect_widget).values():
				painter.drawRect(handle_rect)

	def mousePressEvent(self, event) -> None:
		if not self.hasImage():
			return

		if event.button() == Qt.MouseButton.RightButton:
			self.drag_mode = "pan"
			self.pan_drag_start = event.position()
			self.pan_start_offset = QPointF(self.pan_offset)
			self.setCursor(Qt.CursorShape.ClosedHandCursor)
			return

		if event.button() != Qt.MouseButton.LeftButton:
			return

		image_pos = self._widgetToImage(event.position())
		if image_pos is None:
			return

		self.drag_start_image = image_pos
		self.start_rect = QRectF(self.selection_rect)
		self.active_handle = None

		handle = self._hitTestHandle(event.position())
		if handle is not None:
			self.drag_mode = "resize"
			self.active_handle = handle
			return

		if not self.selection_rect.isNull() and self.selection_rect.contains(image_pos):
			self.drag_mode = "move"
			return

		if not self.selection_rect.isNull() and self.selection_rect.width() > 0 and self.selection_rect.height() > 0:
			# Preserve the current selection when clicking outside it.
			return

		self.drag_mode = "draw"
		self.selection_rect = QRectF(image_pos, image_pos)
		self._emitSelection()
		self.update()

	def mouseMoveEvent(self, event) -> None:
		if not self.hasImage():
			return

		if self.drag_mode == "pan":
			delta = event.position() - self.pan_drag_start
			self.pan_offset = self.pan_start_offset + delta
			self._updateImageDisplayRect()
			self.update()
			return

		image_pos = self._widgetToImage(event.position())

		if self.drag_mode == "none":
			handle = self._hitTestHandle(event.position())
			if handle in {"tl", "br"}:
				self.setCursor(Qt.CursorShape.SizeFDiagCursor)
			elif handle in {"tr", "bl"}:
				self.setCursor(Qt.CursorShape.SizeBDiagCursor)
			elif image_pos is not None and not self.selection_rect.isNull() and self.selection_rect.contains(image_pos):
				self.setCursor(Qt.CursorShape.SizeAllCursor)
			else:
				self.setCursor(Qt.CursorShape.CrossCursor)
			return

		if image_pos is None:
			image_pos = self._widgetToImageClamped(event.position())

		if self.drag_mode == "draw":
			self.selection_rect = QRectF(self.drag_start_image, image_pos).normalized()
		elif self.drag_mode == "move":
			delta = image_pos - self.drag_start_image
			moved = self.start_rect.translated(delta)
			self.selection_rect = self._clampRectToImage(moved)
		elif self.drag_mode == "resize" and self.active_handle:
			self.selection_rect = self._resizeFromHandle(self.active_handle, image_pos)

		self._emitSelection()
		self.update()

	def mouseReleaseEvent(self, event) -> None:
		if event.button() == Qt.MouseButton.RightButton and self.drag_mode == "pan":
			self.drag_mode = "none"
			self.update()
			return

		if event.button() == Qt.MouseButton.LeftButton:
			self.drag_mode = "none"
			self.active_handle = None
			self.update()

	def wheelEvent(self, event) -> None:
		if not self.hasImage():
			return

		delta = event.angleDelta().y()
		if delta == 0:
			return

		# Keep the same image pixel under the mouse while zooming for precision work.
		mouse_pos = event.position()
		focus_image_pos = self._widgetToImageClamped(mouse_pos)
		zoom_step = 1.1
		factor = zoom_step ** (delta / 120.0)

		new_zoom = min(max(self.zoom_factor * factor, self.min_zoom), self.max_zoom)
		if abs(new_zoom - self.zoom_factor) < 1e-9:
			return

		self.zoom_factor = new_zoom
		self._updateImageDisplayRect()

		focus_widget_after = self._imageToWidget(focus_image_pos)
		self.pan_offset += (mouse_pos - focus_widget_after)
		self._updateImageDisplayRect()
		self.update()

	def _updateImageDisplayRect(self) -> None:
		if not self.hasImage():
			self.image_display_rect = QRectF()
			return

		widget_w = max(1, self.width())
		widget_h = max(1, self.height())
		image_w = self.image_pixmap.width()
		image_h = self.image_pixmap.height()

		scale = min(widget_w / image_w, widget_h / image_h)
		base_w = image_w * scale
		base_h = image_h * scale

		draw_w = base_w * self.zoom_factor
		draw_h = base_h * self.zoom_factor
		offset_x = (widget_w - draw_w) / 2 + self.pan_offset.x()
		offset_y = (widget_h - draw_h) / 2 + self.pan_offset.y()

		self.image_display_rect = QRectF(offset_x, offset_y, draw_w, draw_h)

	def _widgetToImage(self, pos: QPointF) -> QPointF | None:
		if not self.image_display_rect.contains(pos):
			return None
		return self._widgetToImageClamped(pos)

	def _widgetToImageClamped(self, pos: QPointF) -> QPointF:
		if not self.hasImage() or self.image_display_rect.isNull():
			return QPointF()

		x = (pos.x() - self.image_display_rect.left()) / self.image_display_rect.width()
		y = (pos.y() - self.image_display_rect.top()) / self.image_display_rect.height()

		x = min(max(x, 0.0), 1.0)
		y = min(max(y, 0.0), 1.0)

		image_x = x * self.image_pixmap.width()
		image_y = y * self.image_pixmap.height()
		return QPointF(image_x, image_y)

	def _imageToWidget(self, pos: QPointF) -> QPointF:
		x = self.image_display_rect.left() + (pos.x() / self.image_pixmap.width()) * self.image_display_rect.width()
		y = self.image_display_rect.top() + (pos.y() / self.image_pixmap.height()) * self.image_display_rect.height()
		return QPointF(x, y)

	def _imageRectToWidgetRect(self, rect: QRectF) -> QRectF:
		tl = self._imageToWidget(rect.topLeft())
		br = self._imageToWidget(rect.bottomRight())
		return QRectF(tl, br).normalized()

	def _handleRectsWidget(self, rect_widget: QRectF) -> dict:
		half = self.handle_size / 2
		points = {
			"tl": rect_widget.topLeft(),
			"tr": rect_widget.topRight(),
			"bl": rect_widget.bottomLeft(),
			"br": rect_widget.bottomRight(),
		}
		return {
			name: QRectF(pt.x() - half, pt.y() - half, self.handle_size, self.handle_size)
			for name, pt in points.items()
		}

	def _hitTestHandle(self, widget_pos: QPointF):
		if self.selection_rect.isNull() or self.selection_rect.width() <= 0 or self.selection_rect.height() <= 0:
			return None

		rect_widget = self._imageRectToWidgetRect(self.selection_rect)
		for name, handle_rect in self._handleRectsWidget(rect_widget).items():
			if handle_rect.contains(widget_pos):
				return name
		return None

	def _clampRectToImage(self, rect: QRectF) -> QRectF:
		image_w = self.image_pixmap.width()
		image_h = self.image_pixmap.height()

		w = rect.width()
		h = rect.height()
		left = min(max(rect.left(), 0.0), max(0.0, image_w - w))
		top = min(max(rect.top(), 0.0), max(0.0, image_h - h))
		return QRectF(left, top, w, h)

	def _resizeFromHandle(self, handle: str, current_image_pos: QPointF) -> QRectF:
		r = self.start_rect
		if handle == "tl":
			anchor = r.bottomRight()
		elif handle == "tr":
			anchor = r.bottomLeft()
		elif handle == "bl":
			anchor = r.topRight()
		else:
			anchor = r.topLeft()

		resized = QRectF(anchor, current_image_pos).normalized()

		left = min(max(resized.left(), 0.0), float(self.image_pixmap.width()))
		top = min(max(resized.top(), 0.0), float(self.image_pixmap.height()))
		right = min(max(resized.right(), 0.0), float(self.image_pixmap.width()))
		bottom = min(max(resized.bottom(), 0.0), float(self.image_pixmap.height()))

		return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()

	def _emitSelection(self) -> None:
		if self.selection_rect.isNull() or self.selection_rect.width() <= 0 or self.selection_rect.height() <= 0:
			self.selectionChanged.emit(())
			return

		r = self.selection_rect.normalized()
		x1 = int(round(r.left()))
		y1 = int(round(r.top()))
		x2 = int(round(r.right()))
		y2 = int(round(r.bottom()))

		corners = (
			(x1, y1),
			(x2, y1),
			(x1, y2),
			(x2, y2),
		)
		self.selectionChanged.emit(corners)


class CoordinateToolWindow(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("Image Coordinate Tool")
		self.resize(1200, 800)

		self.canvas = ImageCanvas(self)
		self.canvas.selectionChanged.connect(self._updateCoordinateLabel)

		self.load_button = QPushButton("Load Image")
		self.load_button.clicked.connect(self._loadImage)

		self.clear_button = QPushButton("Clear Rectangle")
		self.clear_button.clicked.connect(self.canvas.clearSelection)

		self.save_button = QPushButton("Save Snip")
		self.save_button.clicked.connect(self._saveSnip)

		self.coord_label = QLabel("Corners: (none)")
		self.coord_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

		top_row = QHBoxLayout()
		top_row.addWidget(self.load_button)
		top_row.addWidget(self.clear_button)
		top_row.addWidget(self.save_button)
		top_row.addStretch(1)

		layout = QVBoxLayout()
		layout.addLayout(top_row)
		layout.addWidget(self.canvas, stretch=1)
		layout.addWidget(self.coord_label)

		container = QWidget()
		container.setLayout(layout)
		self.setCentralWidget(container)

	def _loadImage(self) -> None:
		file_path, _ = QFileDialog.getOpenFileName(
			self,
			"Select Image",
			"",
			"Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff);;All Files (*)",
		)

		if not file_path:
			return

		loaded = self.canvas.loadImage(file_path)
		if loaded:
			self.coord_label.setText("Corners: (none)")
		else:
			self.coord_label.setText("Failed to load image")

	def _updateCoordinateLabel(self, corners: tuple) -> None:
		if not corners:
			self.coord_label.setText("Corners: (none)")
			return

		tl, tr, bl, br = corners
		self.coord_label.setText(
			f"Corners: TL{tl}  TR{tr}  BL{bl}  BR{br}"
		)

	def _saveSnip(self) -> None:
		if not self.canvas.hasImage():
			self.coord_label.setText("No image loaded")
			return

		r = self.canvas.selection_rect.normalized()
		if r.isNull() or r.width() <= 0 or r.height() <= 0:
			self.coord_label.setText("No rectangle selected")
			return

		img_w = self.canvas.image_pixmap.width()
		img_h = self.canvas.image_pixmap.height()

		left = max(0, min(img_w, int(round(r.left()))))
		top = max(0, min(img_h, int(round(r.top()))))
		right = max(0, min(img_w, int(round(r.right()))))
		bottom = max(0, min(img_h, int(round(r.bottom()))))

		crop_w = right - left
		crop_h = bottom - top
		if crop_w <= 0 or crop_h <= 0:
			self.coord_label.setText("Rectangle is too small to save")
			return

		snip = self.canvas.image_pixmap.copy(left, top, crop_w, crop_h)
		out_path = Path.cwd() / "snip.png"
		if snip.save(str(out_path)):
			self.coord_label.setText(f"Saved snip: {out_path}")
		else:
			self.coord_label.setText("Failed to save snip.png")


def main() -> int:
	app = QApplication(sys.argv)
	window = CoordinateToolWindow()
	window.show()
	return app.exec()


if __name__ == "__main__":
	raise SystemExit(main())
