from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSizePolicy
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QSize

from classes.document import PageInfo
from classes.drawing_overlay import DrawingOverlay


class PageWidget(QWidget):
    """Container: QLabel base + DrawingOverlay overlay (with compatibility shims)."""

    __slots__ = ['prev', 'next', 'page_info', 'zoom_level', 'base_pixmap', 'layout_index', 'orig_page_num']

    def __init__(self, page_info: PageInfo, index: int = -1, prev=None, next=None, parent=None, zoom=1.0):
        super(PageWidget, self).__init__()

        self.prev = prev

        if prev is not None:
            if prev.next is not None:
                prev.next.clear()
            prev.next = self

        self.next = next

        if next is not None:
            if next.prev is not None:
                next.prev.clear()
            next.prev = self

        self.page_info = page_info

        self.zoom_level = zoom

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_SetStyle, True)
        self.setStyleSheet("background-color: rgba(250, 250, 250, 1);")

        display_size = self.calculate_display_size()
        width = display_size.width()
        height = display_size.height()

        self.base_label = QLabel(self)
        self.base_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.base_label.setStyleSheet("QLabel { border: none; }")

        self.setMinimumSize(width, height)
        self.setMaximumSize(width, height)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        self.base_label.setText(f"Страница {page_info.page_num}\nЗагрузка...")
        self.base_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.overlay = DrawingOverlay(self)
        self.overlay.setFixedSize(width, height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.base_label)

        # self.is_empty = True
        self.base_pixmap = None
        # self.tmp_pixmap = None

        self.layout_index: int = index
        self.orig_page_num: int = page_info.page_num

    def calculate_display_size(self) -> QSize:
        """Calculate the actual display size for a page at current zoom.
        This matches what PyMuPDF will render."""
        # PyMuPDF uses the matrix to scale, resulting in dimensions = original * zoom
        # We need to ensure we're calculating the exact same dimensions
        width = int(self.page_info.width * self.zoom_level + 0.5)  # Round to nearest
        height = int(self.page_info.height * self.zoom_level) + 0.5

        # Ensure minimum size for visibility
        width = max(width, 100)
        height = max(height, 100)

        return QSize(width, height)

    def isVisibleByViewport(self, scroll: int, viewport_height: int):
        top = scroll  # a_min
        bottom = scroll + viewport_height  # a_max

        # TODO: Костыль. При первом рендеринге задаётся y. До этого - он нулевой
        if self.y() == 0: return True

        # print(f"y: {self.y()}; height: {self.height()}")

        # return top <= self.y() <= bottom or top <= self.y() + self.height() <= bottom

        return max(top, self.y()) <= min(bottom, self.y() + self.height())

    def resizeEvent(self, ev):
        sz = self.base_label.size()
        self.overlay.setFixedSize(sz)
        super().resizeEvent(ev)
        # if not self.base_pixmap is None:
        #     scaled = self.base_pixmap.scaled(self.width(), self.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        #     self.set_base_pixmap(scaled)  # self.setPixmap(scaled)

    def set_base_pixmap(self, pixmap: QPixmap):
        if pixmap is None or pixmap.isNull():
            return
        self.base_pixmap = pixmap
        self.base_label.setPixmap(pixmap)
        self.base_label.setFixedSize(pixmap.size())
        self.overlay.setFixedSize(pixmap.size())
        # self.is_empty = False
        self.overlay.update()

    def clear_base(self, emit: bool = True):
        # 20.01.2026 - is_empty - помечает виджет-страницу на перезапись
        # (для бесшовного зума)
        # self.is_empty = True

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

    def setZoom(self, zoom):
        self.zoom_level = zoom

        display_size = self.calculate_display_size()
        width = display_size.width()
        height = display_size.height()

        self.setMinimumSize(width, height)
        self.setMaximumSize(width, height)
