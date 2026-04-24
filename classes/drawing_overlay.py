from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QMouseEvent, QPaintEvent
from PySide6.QtCore import Qt, QRect, QPoint, QBuffer, Signal, QSize


class DrawingOverlay(QWidget):
    """Vector-first annotation layer (defensively coded to avoid racey paint calls)."""
    annotation_changed = Signal()

    TOOL_BRUSH = "brush"
    TOOL_RECT = "rect"

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Minimal defensive defaults (so paintEvent won't crash if called early) ---
        self.annot_pixmap = QPixmap(1, 1)
        self.annot_pixmap.fill(Qt.transparent)
        self.strokes = []   # list of stroke dicts
        self.rects = []     # list of rect dicts
        self.tool = self.TOOL_BRUSH
        self.color = QColor(Qt.black)
        self.brush_size = 6

        # Rectangle-specific settings
        # fill_color=None means "no fill" (outline-only mode)
        self.rect_fill_color: QColor | None = QColor(Qt.black)  # filled by default
        self.rect_border_color: QColor = QColor(Qt.black)
        self.rect_border_width: int = 2   # px; 0 = no border

        self._drawing = False
        self._current_stroke = []
        self._rect_start = QPoint()
        self._rect_current = QRect()
        self._dirty = False
        self.enabled = False

        # Widget attributes
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_StaticContents, True)

    # ------------------- Public API -------------------
    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not self.enabled)
        if self.enabled:
            self.setFocus()

    def set_tool(self, tool: str):
        if tool in (self.TOOL_BRUSH, self.TOOL_RECT):
            self.tool = tool

    def set_color(self, color: QColor):
        """Set brush colour AND sync rect colours for convenience."""
        self.color = color

    def set_brush_size(self, size: int):
        self.brush_size = max(1, int(size))

    def set_rect_fill_color(self, color: QColor | None):
        """None = no fill (transparent interior)."""
        self.rect_fill_color = color

    def set_rect_border_color(self, color: QColor):
        self.rect_border_color = color

    def set_rect_border_width(self, width: int):
        self.rect_border_width = max(0, int(width))

    def clear_annotations(self, emit: bool = True):
        self.strokes = []
        self.rects = []
        if getattr(self, "annot_pixmap", None) is not None:
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
        return bool(getattr(self, "_dirty", False))

    def has_vector(self) -> bool:
        return bool(getattr(self, "strokes", []) or getattr(self, "rects", []))

    def export_png_bytes(self, target_width: int, target_height: int) -> bytes:
        """Render vector primitives to a raster PNG sized target_width x target_height."""
        try:
            if target_width <= 0 or target_height <= 0:
                return b""
            pm = QPixmap(QSize(target_width, target_height))
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)

            for s in self.strokes:
                pts = s.get("points", [])
                if not pts:
                    continue
                pen = QPen(QColor(*s.get("color", (0, 0, 0))),
                           s.get("width", 1), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                p.setPen(pen)
                prev = None
                for nx, ny in pts:
                    x = nx * target_width
                    y = ny * target_height
                    if prev is None:
                        prev = (x, y)
                    else:
                        p.drawLine(prev[0], prev[1], x, y)
                        prev = (x, y)

            for r in self.rects:
                x0, y0, x1, y1 = r.get("rect", (0, 0, 0, 0))
                x = x0 * target_width
                y = y0 * target_height
                w = (x1 - x0) * target_width
                h = (y1 - y0) * target_height

                fill_raw = r.get("fill_color")
                border_raw = r.get("border_color", (0, 0, 0))
                border_w = r.get("border_width", 0)

                if fill_raw is not None:
                    p.setBrush(QColor(*fill_raw))
                else:
                    p.setBrush(Qt.NoBrush)

                if border_w > 0:
                    p.setPen(QPen(QColor(*border_raw), border_w))
                else:
                    p.setPen(Qt.NoPen)

                p.drawRect(x, y, w, h)

            p.end()
            buffer = QBuffer()
            buffer.open(QBuffer.ReadWrite)
            pm.save(buffer, "PNG")
            data = buffer.data()
            buffer.close()
            return bytes(data)
        except Exception as e:
            print(f"[DrawingOverlay] export_png_bytes error: {e}")
            return b""

    def get_vector_shapes(self) -> dict:
        return {"strokes": list(getattr(self, "strokes", []) or []),
                "rects": list(getattr(self, "rects", []) or [])}

    # ------------------- Events -------------------
    def resizeEvent(self, event):
        try:
            w = max(1, self.width())
            h = max(1, self.height())
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

    def _to_normalized(self, pt):
        w = max(1, self.width())
        h = max(1, self.height())
        return (pt.x() / w, pt.y() / h)

    def _color_to_tuple(self, color: QColor):
        return (color.red(), color.green(), color.blue())

    def mousePressEvent(self, ev: QMouseEvent):
        if not getattr(self, "enabled", False):
            return
        if ev.button() != Qt.LeftButton:
            return
        self._drawing = True
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        if getattr(self, "tool", None) == self.TOOL_BRUSH:
            self._current_stroke = [p]
        else:
            self._rect_start = p
            self._rect_current = QRect(p, p)
        ev.accept()

    def mouseMoveEvent(self, ev: QMouseEvent):
        if not getattr(self, "enabled", False) or not getattr(self, "_drawing", False):
            return
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        if getattr(self, "tool", None) == self.TOOL_BRUSH:
            try:
                self._current_stroke.append(p)
                self.update()
            except Exception:
                pass
        else:
            self._rect_current = QRect(self._rect_start, p).normalized()
            self._dirty = True
            self.update()
        ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if not getattr(self, "enabled", False) or not getattr(self, "_drawing", False):
            return
        p = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()

        if getattr(self, "tool", None) == self.TOOL_BRUSH:
            normalized = [self._to_normalized(pt) for pt in self._current_stroke]
            if len(normalized) >= 2:
                color_tuple = self._color_to_tuple(self.color)
                self.strokes.append({
                    "points": normalized,
                    "width": int(self.brush_size),
                    "color": color_tuple,
                })
            self.annot_pixmap = QPixmap(1, 1)
            self.annot_pixmap.fill(Qt.transparent)
            self._current_stroke = []
        else:
            rect = QRect(self._rect_start, p).normalized()
            x0 = rect.left()   / max(1, self.width())
            y0 = rect.top()    / max(1, self.height())
            x1 = rect.right()  / max(1, self.width())
            y1 = rect.bottom() / max(1, self.height())

            fill_raw = (self._color_to_tuple(self.rect_fill_color)
                        if self.rect_fill_color is not None else None)
            border_raw = self._color_to_tuple(self.rect_border_color)

            self.rects.append({
                "rect": (x0, y0, x1, y1),
                # legacy "color" key kept for backward-compat with overlay_render
                "color": fill_raw if fill_raw is not None else border_raw,
                "fill_color": fill_raw,
                "border_color": border_raw,
                "border_width": int(self.rect_border_width),
            })
            self._rect_current = QRect()

        self._drawing = False
        self._dirty = True
        self.update()
        try:
            self.annotation_changed.emit()
        except Exception:
            pass
        ev.accept()

    def paintEvent(self, ev: QPaintEvent):
        strokes = getattr(self, "strokes", []) or []
        rects   = getattr(self, "rects",   []) or []
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            if getattr(self, "annot_pixmap", None) is not None and not self.annot_pixmap.isNull():
                try:
                    painter.drawPixmap(0, 0, self.annot_pixmap)
                except Exception:
                    pass

            # ── Committed strokes ────────────────────────────────────────
            for s in strokes:
                pts = s.get("points", [])
                if not pts:
                    continue
                pen = QPen(QColor(*s.get("color", (0, 0, 0))),
                           s.get("width", 1), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                painter.setPen(pen)
                prev = None
                w = max(1, self.width())
                h = max(1, self.height())
                for nx, ny in pts:
                    x = nx * w
                    y = ny * h
                    if prev is None:
                        prev = (x, y)
                    else:
                        painter.drawLine(prev[0], prev[1], x, y)
                        prev = (x, y)

            # ── Committed rects ──────────────────────────────────────────
            for r in rects:
                x0, y0, x1, y1 = r.get("rect", (0, 0, 0, 0))
                x = x0 * self.width()
                y = y0 * self.height()
                w = (x1 - x0) * self.width()
                h = (y1 - y0) * self.height()

                fill_raw   = r.get("fill_color")
                border_raw = r.get("border_color", (0, 0, 0))
                border_w   = r.get("border_width", 0)

                painter.setBrush(QColor(*fill_raw) if fill_raw is not None else Qt.NoBrush)
                painter.setPen(QPen(QColor(*border_raw), border_w) if border_w > 0 else Qt.NoPen)
                painter.drawRect(x, y, w, h)

            # ── In-progress drawing preview ──────────────────────────────
            if getattr(self, "_drawing", False):
                if getattr(self, "tool", None) == self.TOOL_BRUSH:
                    current_stroke = getattr(self, "_current_stroke", [])
                    if len(current_stroke) >= 2:
                        pen = QPen(self.color, self.brush_size,
                                   Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                        painter.setPen(pen)
                        prev = current_stroke[0]
                        for i in range(1, len(current_stroke)):
                            curr = current_stroke[i]
                            painter.drawLine(prev, curr)
                            prev = curr

                elif (getattr(self, "tool", None) == self.TOOL_RECT and
                      not getattr(self, "_rect_current", QRect()).isNull()):
                    fill_raw   = (self._color_to_tuple(self.rect_fill_color)
                                  if self.rect_fill_color is not None else None)
                    border_w   = self.rect_border_width

                    painter.setBrush(QColor(*fill_raw) if fill_raw is not None else Qt.NoBrush)
                    painter.setPen(
                        QPen(self.rect_border_color, border_w) if border_w > 0 else Qt.NoPen
                    )
                    painter.drawRect(self._rect_current)

            painter.end()

        except Exception as e:
            print(f"[DrawingOverlay] paintEvent error: {e}")
