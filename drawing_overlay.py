# drawing_overlay.py
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QMouseEvent, QPaintEvent
from PySide6.QtCore import Qt, QRect, QPoint, QBuffer, Signal, QSize


class DrawingOverlay(QWidget):
    """Vector-first annotation layer (defensively coded to avoid racey paint calls)."""
    annotation_changed = Signal()

    TOOL_BRUSH = "brush"
    TOOL_RECT = "rect"

    def __init__(self, parent=None):
        # ensure QWidget init happens first
        super().__init__(parent)

        # --- Minimal defensive defaults (so paintEvent won't crash if called early) ---
        self.annot_pixmap = QPixmap(1, 1)
        self.annot_pixmap.fill(Qt.transparent)
        self.strokes = []   # list of stroke dicts
        self.rects = []     # list of rect dicts
        self.tool = self.TOOL_BRUSH
        self.color = QColor(Qt.black)
        self.brush_size = 6
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
        self.color = color

    def clear_annotations(self, emit: bool = True):
        # Defensive: ensure attributes exist
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

            # strokes
            for s in getattr(self, "strokes", []) or []:
                pts = s.get("points", [])
                if not pts:
                    continue
                pen = QPen(QColor(*s.get("color", (0, 0, 0))), s.get("width", 1), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
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

            # rects
            for r in getattr(self, "rects", []) or []:
                x0, y0, x1, y1 = r.get("rect", (0, 0, 0, 0))
                x = x0 * target_width
                y = y0 * target_height
                w = (x1 - x0) * target_width
                h = (y1 - y0) * target_height
                col = QColor(*r.get("color", (0, 0, 0)))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
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
        return {"strokes": list(getattr(self, "strokes", []) or []), "rects": list(getattr(self, "rects", []) or [])}

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
                painter = QPainter(self.annot_pixmap)
                pen = QPen(getattr(self, "color", QColor(Qt.black)), getattr(self, "brush_size", 6),
                           Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                painter.setPen(pen)
                prev = self._current_stroke[-1]
                painter.drawLine(prev, p)
                painter.end()
                self._current_stroke.append(p)
                self._dirty = True
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
                color_tuple = (self.color.red(), self.color.green(), self.color.blue())
                self.strokes.append({"points": normalized, "width": int(self.brush_size), "color": color_tuple})
            self.annot_pixmap = QPixmap(1, 1)
            self.annot_pixmap.fill(Qt.transparent)
            self._current_stroke = []
        else:
            rect = QRect(self._rect_start, p).normalized()
            x0 = rect.left() / max(1, self.width())
            y0 = rect.top() / max(1, self.height())
            x1 = rect.right() / max(1, self.width())
            y1 = rect.bottom() / max(1, self.height())
            color_tuple = (self.color.red(), self.color.green(), self.color.blue())
            self.rects.append({"rect": (x0, y0, x1, y1), "color": color_tuple})
            self._rect_current = QRect()

        self._drawing = False
        self._dirty = True
        self.update()
        try:
            self.annotation_changed.emit()

            # # optionally ask owning viewer to persist vectors immediately (if available)
            # try:
            #     parent_viewer = getattr(self.parent(), "parent", None)
            #     # some hierarchy differences exist; just try walking up a bit
            #     if parent_viewer is None:
            #         parent_viewer = getattr(self.parent(), "parentWidget", None)
            #     # attempt to retrieve PDFViewer instance (heuristic)
            #     pv = None
            #     if hasattr(self, "parent") and callable(getattr(self, "parent")):
            #         p = self.parent()
            #         # try p.parent() or p.parentWidget()
            #         pv = getattr(p, "parent", lambda: None)()
            #     if pv is not None and hasattr(pv, "_save_vector_immediate"):
            #         # orig_page_num lookup via widget property
            #         try:
            #             orig = self.parent().property("orig_page_num")
            #             if orig is not None:
            #                 pv._save_vector_immediate(self.parent(), orig)
            #         except Exception:
            #             pass
            # except Exception:
            #     pass

        except Exception:
            pass
        ev.accept()

    def paintEvent(self, ev: QPaintEvent):
        # Defensive: don't crash if attributes missing; fall back to empty lists
        strokes = getattr(self, "strokes", []) or []
        rects = getattr(self, "rects", []) or []
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            if getattr(self, "annot_pixmap", None) is not None and not self.annot_pixmap.isNull():
                try:
                    painter.drawPixmap(0, 0, self.annot_pixmap)
                except Exception:
                    pass

            # draw strokes
            for s in strokes:
                pts = s.get("points", [])
                if not pts:
                    continue
                pen = QPen(QColor(*s.get("color", (0, 0, 0))), s.get("width", 1), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
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

            # draw rects
            for r in rects:
                x0, y0, x1, y1 = r.get("rect", (0, 0, 0, 0))
                x = x0 * self.width()
                y = y0 * self.height()
                w = (x1 - x0) * self.width()
                h = (y1 - y0) * self.height()
                col = QColor(*r.get("color", (0, 0, 0)))
                painter.setPen(Qt.NoPen)
                painter.setBrush(col)
                painter.drawRect(x, y, w, h)

            # draw current rect preview if active
            if getattr(self, "_drawing", False) and getattr(self, "tool", None) == self.TOOL_RECT and not getattr(self, "_rect_current", QRect()).isNull():
                pen = QPen(self.color, 1, Qt.SolidLine)
                painter.setPen(pen)
                painter.setBrush(self.color)
                painter.drawRect(self._rect_current)

            painter.end()
        except Exception as e:
            # guard against any unexpected drawing-time errors
            print(f"[DrawingOverlay] paintEvent error: {e}")


class PageWidget(QWidget):
    """Container: QLabel base + DrawingOverlay overlay (with compatibility shims)."""
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

    def clear_base(self, emit: bool = True):
        try:
            self.base_label.clear()
        except Exception:
            pass
        self.base_pixmap = None
        try:
            self.overlay.clear_annotations(emit=emit)
        except Exception:
            pass

    def clear(self):
        self.clear_base(emit=False)

    def has_annotations(self) -> bool:
        return self.overlay.is_dirty() or self.overlay.has_vector()

    def export_annotations_png(self, target_width: int, target_height: int) -> bytes:
        return self.overlay.export_png_bytes(target_width, target_height)

    # compatibility shims
    def setText(self, text: str):
        self.base_label.setText(text)

    def text(self) -> str:
        return self.base_label.text()

    def setPixmap(self, pixmap: QPixmap):
        try:
            if isinstance(pixmap, QPixmap):
                self.set_base_pixmap(pixmap)
            else:
                pm = QPixmap()
                ok = pm.loadFromData(pixmap)
                if ok and not pm.isNull():
                    self.set_base_pixmap(pm)
        except Exception:
            try:
                self.base_label.setPixmap(pixmap)
            except Exception:
                pass

    def setStyleSheet(self, sheet: str):
        try:
            QWidget.setStyleSheet(self, sheet)
        except Exception:
            pass
        try:
            self.base_label.setStyleSheet(sheet)
        except Exception:
            pass
