from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QMouseEvent, QPaintEvent
from PySide6.QtCore import Qt, QRect, QPoint, QBuffer, Signal


class DrawingOverlay(QWidget):
    """Transparent annotation layer. Supports brush and filled rectangle.
    Emits annotation_changed when user commits a change (so viewer can mark document modified).
    """
    annotation_changed = Signal()

    TOOL_BRUSH = "brush"
    TOOL_RECT = "rect"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_StaticContents, True)

        self.annot_pixmap = QPixmap(1, 1)
        self.annot_pixmap.fill(Qt.transparent)

        self.tool = self.TOOL_BRUSH
        self.color = QColor(Qt.black)
        self.brush_size = 6

        self._drawing = False
        self._last_point = QPoint()
        self._rect_start = QPoint()
        self._rect_current = QRect()

        self._dirty = False
        self.enabled = False

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        # Accept mouse events only when enabled
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not self.enabled)
        # Ensure widget grabs mouse when enabled
        if self.enabled:
            self.setFocus()

    def set_tool(self, tool: str):
        if tool in (self.TOOL_BRUSH, self.TOOL_RECT):
            self.tool = tool

    def set_color(self, color: QColor):
        self.color = color

    def clear_annotations(self):
        if not self.annot_pixmap.isNull():
            self.annot_pixmap.fill(Qt.transparent)
            self._dirty = False
            self.update()
            # notify cleared => changed state
            self.annotation_changed.emit()

    def is_dirty(self) -> bool:
        return self._dirty

    def resizeEvent(self, event):
        w = max(1, self.width())
        h = max(1, self.height())
        if self.annot_pixmap.width() < w or self.annot_pixmap.height() < h:
            new_pix = QPixmap(w, h)
            new_pix.fill(Qt.transparent)
            painter = QPainter(new_pix)
            painter.drawPixmap(0, 0, self.annot_pixmap)
            painter.end()
            self.annot_pixmap = new_pix
        super().resizeEvent(event)

    # Mouse events: overlay receives them only when enabled (set_enabled True)
    def mousePressEvent(self, ev: QMouseEvent):
        if not self.enabled:
            return
        if ev.button() != Qt.LeftButton:
            return
        self._drawing = True
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        self._last_point = p
        self._rect_start = p
        self._rect_current = QRect(p, p)
        ev.accept()

    def mouseMoveEvent(self, ev: QMouseEvent):
        if not self.enabled or not self._drawing:
            return
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        if self.tool == self.TOOL_BRUSH:
            painter = QPainter(self.annot_pixmap)
            pen = QPen(self.color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(self._last_point, p)
            painter.end()
            self._last_point = p
            self._dirty = True
            self.update()
        else:  # rect tool - preview only
            self._rect_current = QRect(self._rect_start, p).normalized()
            self.update()
        ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if not self.enabled or not self._drawing:
            return
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        if self.tool == self.TOOL_BRUSH:
            # final stroke already drawn in mouseMoveEvent
            pass
        else:
            painter = QPainter(self.annot_pixmap)
            painter.setPen(QPen(self.color, 1))
            painter.setBrush(self.color)
            painter.drawRect(QRect(self._rect_start, p).normalized())
            painter.end()
            self._dirty = True
            self._rect_current = QRect()
        self._drawing = False
        self.update()
        # Notify viewer that something changed
        self.annotation_changed.emit()
        ev.accept()

    def paintEvent(self, ev: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, self.annot_pixmap)
        if self._drawing and self.tool == self.TOOL_RECT and not self._rect_current.isNull():
            pen = QPen(self.color, 1, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(self.color)
            painter.drawRect(self._rect_current)
        painter.end()

    def export_png_bytes(self, target_width: int, target_height: int) -> bytes:
        """Return PNG bytes of the annotation layer scaled to target size (exact size)."""
        if self.annot_pixmap.isNull():
            return b""
        scaled = self.annot_pixmap.scaled(target_width, target_height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        scaled.save(buffer, "PNG")
        data = buffer.data()
        buffer.close()
        return bytes(data)


class PageWidget(QWidget):
    """Container for a single page: base QLabel + DrawingOverlay on top."""
    def __init__(self, width=200, height=200, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: white;")

        self.base_label = QLabel(self)
        self.base_label.setAlignment(Qt.AlignCenter)
        self.base_label.setStyleSheet("QLabel { border: none; }")
        self.base_label.setFixedSize(width, height)

        self.overlay = DrawingOverlay(self)
        self.overlay.setFixedSize(width, height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.base_label)

        self.base_pixmap = None

    def resizeEvent(self, ev):
        sz = self.base_label.size()
        self.overlay.setFixedSize(sz)
        super().resizeEvent(ev)

    def set_base_pixmap(self, pixmap: QPixmap):
        if pixmap is None or pixmap.isNull():
            return
        self.base_pixmap = pixmap
        self.base_label.setPixmap(pixmap)
        self.base_label.setFixedSize(pixmap.size())
        self.overlay.setFixedSize(pixmap.size())
        self.overlay.update()

    def clear_base(self):
        self.base_label.clear()
        self.base_pixmap = None
        # also clear overlay
        self.overlay.clear_annotations()

    def has_annotations(self) -> bool:
        return self.overlay.is_dirty()

    def export_annotations_png(self, target_width: int, target_height: int) -> bytes:
        return self.overlay.export_png_bytes(target_width, target_height)
