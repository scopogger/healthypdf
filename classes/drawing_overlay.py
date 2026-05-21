from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QMouseEvent, QPaintEvent, QKeyEvent
from PySide6.QtCore import Qt, QRect, QPoint, QBuffer, Signal, QSize


class DrawingOverlay(QWidget):
    """Vector-first annotation layer.

    All primitives (strokes AND rects) are stored in a single ordered list
    `self.primitives` so they render in the exact order the user drew them

    Undo / redo is implemented as a simple stack:
      • Ctrl+Z  — undo last primitive
      • Ctrl+Shift+Z — redo
    """
    annotation_changed = Signal()

    TOOL_BRUSH = "brush"
    TOOL_RECT  = "rect"

    # Maximum selectable thicknesses
    MAX_BRUSH_SIZE   = 20
    MAX_BORDER_WIDTH = 10

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Ordered list of all committed primitives ──────────────────────
        # Each item is a dict with a "kind" key: "stroke" or "rect"
        self.primitives: list[dict] = []
        # Redo stack — items popped off primitives land here
        self._redo_stack: list[dict] = []

        # Вот эти штуки не переделал - а наверно стоило бы
        # .strokes / .rects они до сих пор нужны
        # но лучше не писать в них ничего и использовать `primitives`

        self.annot_pixmap = QPixmap(1, 1)
        self.annot_pixmap.fill(Qt.transparent)

        self.tool  = self.TOOL_BRUSH
        self.color = QColor(Qt.black)
        self.brush_size = 4
        self.brush_opacity = 255  # 0-255

        # Rectangle-specific settings
        self.rect_fill_color:   QColor | None = QColor(Qt.black)
        self.rect_border_color: QColor        = QColor(Qt.black)
        self.rect_border_width: int           = 2
        self.rect_opacity: int = 255  # 0-255

        self._drawing       = False
        self._current_stroke: list[QPoint] = []
        self._rect_start    = QPoint()
        self._rect_current  = QRect()
        self._dirty         = False
        self.enabled        = False

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_StaticContents, True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ── Вот эти штуки стоит переделать как-то ─────────────────────────────────────────
    @property
    def strokes(self) -> list:
        return [p for p in self.primitives if p.get("kind") == "stroke"]

    @property
    def rects(self) -> list:
        return [p for p in self.primitives if p.get("kind") == "rect"]

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not self.enabled)
        if self.enabled:
            self.setFocus()

    def set_tool(self, tool: str):
        if tool in (self.TOOL_BRUSH, self.TOOL_RECT):
            self.tool = tool

    def set_color(self, color: QColor):
        self.color = color

    def set_brush_size(self, size: int):
        self.brush_size = max(1, min(int(size), self.MAX_BRUSH_SIZE))

    def set_brush_opacity(self, opacity_percent: int):
        """opacity_percent: 10-100"""
        self.brush_opacity = max(10, min(100, int(opacity_percent))) * 255 // 100

    def set_rect_opacity(self, opacity_percent: int):
        """opacity_percent: 10-100"""
        self.rect_opacity = max(10, min(100, int(opacity_percent))) * 255 // 100

    def set_rect_fill_color(self, color: "QColor | None"):
        self.rect_fill_color = color

    def set_rect_border_color(self, color: QColor):
        self.rect_border_color = color

    def set_rect_border_width(self, width: int):
        self.rect_border_width = max(0, min(int(width), self.MAX_BORDER_WIDTH))

    # ── Undo / Redo ────────────────────────────────────────────────────
    def undo(self):
        if not self.primitives:
            return
        self._redo_stack.append(self.primitives.pop())
        self._dirty = bool(self.primitives)
        self.update()
        try:
            self.annotation_changed.emit()
        except Exception:
            pass

    def redo(self):
        if not self._redo_stack:
            return
        self.primitives.append(self._redo_stack.pop())
        self._dirty = True
        self.update()
        try:
            self.annotation_changed.emit()
        except Exception:
            pass

    def clear_annotations(self, emit: bool = True):
        self.primitives.clear()
        self._redo_stack.clear()
        self.annot_pixmap = QPixmap(1, 1)
        self.annot_pixmap.fill(Qt.transparent)
        self._dirty = False
        self.update()
        if emit:
            try:
                self.annotation_changed.emit()
            except Exception:
                pass

    def is_dirty(self) -> bool:
        return bool(self._dirty)

    def has_vector(self) -> bool:
        return bool(self.primitives)

    def get_vector_shapes(self) -> dict:
        """Возвращают dict в старом формате с overlay_render / save."""
        return {
            "strokes": self.strokes,
            "rects":   self.rects,
        }

    def export_png_bytes(self, target_width: int, target_height: int) -> bytes:
        try:
            if target_width <= 0 or target_height <= 0:
                return b""
            pm = QPixmap(QSize(target_width, target_height))
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            self._paint_primitives(p, target_width, target_height)
            p.end()
            buf = QBuffer()
            buf.open(QBuffer.ReadWrite)
            pm.save(buf, "PNG")
            data = bytes(buf.data())
            buf.close()
            return data
        except Exception as e:
            print(f"[DrawingOverlay] export_png_bytes error: {e}")
            return b""

    # ── Internal paint helper ──────────────────────────────────────────
    def _paint_primitives(self, painter: QPainter, w: int, h: int,
                          extra_stroke: list | None = None,
                          extra_rect: QRect | None = None):
        """Draw all committed primitives in order, then any in-progress preview."""
        for prim in self.primitives:
            kind = prim.get("kind")
            opacity = prim.get("opacity", 255)
            painter.setOpacity(opacity / 255.0)
            if kind == "stroke":
                pts = prim.get("points", [])
                if len(pts) < 2:
                    continue
                # Render onto offscreen pixmap to avoid per-segment opacity accumulation
                tmp = QPixmap(w, h)
                tmp.fill(Qt.transparent)
                tmp_p = QPainter(tmp)
                tmp_p.setRenderHint(QPainter.Antialiasing)
                pen = QPen(QColor(*prim.get("color", (0, 0, 0))),
                           prim.get("width", 1),
                           Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                tmp_p.setPen(pen)
                tmp_p.setBrush(Qt.NoBrush)
                prev = None
                for nx, ny in pts:
                    x, y = nx * w, ny * h
                    if prev is None:
                        prev = (x, y)
                    else:
                        tmp_p.drawLine(prev[0], prev[1], x, y)
                        prev = (x, y)
                tmp_p.end()
                painter.setOpacity(opacity / 255.0)
                painter.drawPixmap(0, 0, tmp)
                painter.setOpacity(1.0)
            elif kind == "rect":
                x0, y0, x1, y1 = prim.get("rect", (0, 0, 0, 0))
                rx, ry = x0 * w, y0 * h
                rw, rh = (x1 - x0) * w, (y1 - y0) * h
                fill_raw   = prim.get("fill_color")
                border_raw = prim.get("border_color", (0, 0, 0))
                border_w   = prim.get("border_width", 0)
                painter.setBrush(QColor(*fill_raw) if fill_raw is not None else Qt.NoBrush)
                painter.setPen(QPen(QColor(*border_raw), border_w) if border_w > 0 else Qt.NoPen)
                painter.drawRect(rx, ry, rw, rh)
        painter.setOpacity(1.0)  # restore

        # ── In-progress preview ──────────────────────────────────────────
        if extra_stroke and len(extra_stroke) >= 2:
            # Render stroke onto offscreen pixmap first, then composite with opacity.
            # This prevents segment-by-segment opacity accumulation.
            tmp = QPixmap(w, h)
            tmp.fill(Qt.transparent)
            tmp_painter = QPainter(tmp)
            tmp_painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(self.color, self.brush_size,
                       Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            tmp_painter.setPen(pen)
            tmp_painter.setBrush(Qt.NoBrush)
            prev = extra_stroke[0]
            for pt in extra_stroke[1:]:
                tmp_painter.drawLine(prev, pt)
                prev = pt
            tmp_painter.end()
            painter.setOpacity(self.brush_opacity / 255.0)
            painter.drawPixmap(0, 0, tmp)
            painter.setOpacity(1.0)

        if extra_rect and not extra_rect.isNull():
            painter.setOpacity(self.rect_opacity / 255.0)
            fill_raw = (self._color_to_tuple(self.rect_fill_color)
                        if self.rect_fill_color is not None else None)
            painter.setBrush(QColor(*fill_raw) if fill_raw is not None else Qt.NoBrush)
            painter.setPen(
                QPen(self.rect_border_color, self.rect_border_width)
                if self.rect_border_width > 0 else Qt.NoPen
            )
            painter.drawRect(extra_rect)
            painter.setOpacity(1.0)

    # ── Helpers ────────────────────────────────────────────────────────
    def _to_normalized(self, pt: QPoint):
        return (pt.x() / max(1, self.width()),
                pt.y() / max(1, self.height()))

    def _color_to_tuple(self, color: QColor):
        return (color.red(), color.green(), color.blue())

    # ── Resize ────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        try:
            w, h = max(1, self.width()), max(1, self.height())
            if self.annot_pixmap.width() < w or self.annot_pixmap.height() < h:
                new_pix = QPixmap(w, h)
                new_pix.fill(Qt.transparent)
                painter = QPainter(new_pix)
                painter.drawPixmap(0, 0, self.annot_pixmap)
                painter.end()
                self.annot_pixmap = new_pix
        except Exception:
            pass
        super().resizeEvent(event)

    # ── Keyboard: Ctrl+Z / Ctrl+Shift+Z ───────────────────────────────
    def keyPressEvent(self, ev: QKeyEvent):
        if not self.enabled:
            super().keyPressEvent(ev)
            return
        mods = ev.modifiers()
        if mods & Qt.ControlModifier:
            if ev.key() == Qt.Key_Z:
                if mods & Qt.ShiftModifier:
                    self.redo()
                else:
                    self.undo()
                ev.accept()
                return
        super().keyPressEvent(ev)

    # ── Mouse ─────────────────────────────────────────────────────────
    def mousePressEvent(self, ev: QMouseEvent):
        if not self.enabled:
            return
        if ev.button() != Qt.LeftButton:
            return
        # Any new stroke clears the redo stack (standard UX)
        self._redo_stack.clear()
        self._drawing = True
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        if self.tool == self.TOOL_BRUSH:
            self._current_stroke = [p]
        else:
            self._rect_start   = p
            self._rect_current = QRect(p, p)
        ev.accept()

    def mouseMoveEvent(self, ev: QMouseEvent):
        if not self.enabled or not self._drawing:
            return
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        if self.tool == self.TOOL_BRUSH:
            self._current_stroke.append(p)
        else:
            self._rect_current = QRect(self._rect_start, p).normalized()
        self.update()
        ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if not self.enabled or not self._drawing:
            return
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()

        if self.tool == self.TOOL_BRUSH:
            normalized = [self._to_normalized(pt) for pt in self._current_stroke]
            if len(normalized) >= 2:
                self.primitives.append({
                    "kind":    "stroke",
                    "points":  normalized,
                    "width":   int(self.brush_size),
                    "color":   self._color_to_tuple(self.color),
                    "opacity": self.brush_opacity,
                })
            self._current_stroke = []
        else:
            rect = QRect(self._rect_start, p).normalized()
            x0 = rect.left()   / max(1, self.width())
            y0 = rect.top()    / max(1, self.height())
            x1 = rect.right()  / max(1, self.width())
            y1 = rect.bottom() / max(1, self.height())
            fill_raw   = (self._color_to_tuple(self.rect_fill_color)
                          if self.rect_fill_color is not None else None)
            border_raw = self._color_to_tuple(self.rect_border_color)
            self.primitives.append({
                "kind":         "rect",
                "rect":         (x0, y0, x1, y1),
                "color":        fill_raw if fill_raw is not None else border_raw,
                "fill_color":   fill_raw,
                "border_color": border_raw,
                "border_width": int(self.rect_border_width),
                "opacity":      self.rect_opacity,
            })
            self._rect_current = QRect()

        self._drawing = False
        self._dirty   = True
        self.update()
        try:
            self.annotation_changed.emit()
        except Exception:
            pass
        ev.accept()

    # ── Paint ─────────────────────────────────────────────────────────
    def paintEvent(self, ev: QPaintEvent):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            w, h = max(1, self.width()), max(1, self.height())

            self._paint_primitives(
                painter, w, h,
                extra_stroke = self._current_stroke if self._drawing and self.tool == self.TOOL_BRUSH else None,
                extra_rect   = self._rect_current   if self._drawing and self.tool == self.TOOL_RECT  else None,
            )
            painter.end()
        except Exception as e:
            print(f"[DrawingOverlay] paintEvent error: {e}")
