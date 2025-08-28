import threading
from typing import Optional, Dict
from collections import OrderedDict

from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QSlider
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRunnable, QThreadPool
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QFont

import fitz  # PyMuPDF


class ThumbnailCache:
    """Simple size-aware cache for thumbnail QPixmaps keyed by (page_num, size)."""
    def __init__(self, max_size: int = 200):
        self.max_size = max_size
        self.cache: OrderedDict[tuple, QPixmap] = OrderedDict()

    def get(self, page_num: int, size: int) -> Optional[QPixmap]:
        key = (page_num, size)
        pix = self.cache.get(key)
        if pix is not None:
            self.cache.move_to_end(key)
        return pix

    def put(self, page_num: int, size: int, pixmap: QPixmap):
        key = (page_num, size)
        self.cache[key] = pixmap
        self.cache.move_to_end(key)
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def remove_page(self, page_num: int):
        keys = [k for k in self.cache.keys() if k[0] == page_num]
        for k in keys:
            self.cache.pop(k, None)

    def clear(self):
        self.cache.clear()


class ThumbnailRenderWorker(QRunnable):
    """Background worker to render a thumbnail for an ORIGINAL page index."""
    def __init__(self, doc_path: str, page_num: int, callback, render_id: str,
                 thumbnail_size: int = 150, rotation: int = 0, password: str = ""):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num
        self.callback = callback
        self.render_id = render_id
        self.thumbnail_size = thumbnail_size
        self.rotation = rotation
        self.password = password
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        if self.cancelled:
            return
        try:
            doc = fitz.open(self.doc_path)
            if doc.needs_pass and self.password:
                if not doc.authenticate(self.password):
                    doc.close()
                    return

            if self.cancelled:
                doc.close()
                return

            # Safety: if page index out of range, abort
            if not (0 <= self.page_num < len(doc)):
                doc.close()
                return

            page = doc[self.page_num]
            if self.rotation:
                page.set_rotation(self.rotation)

            rect = page.rect
            scale = min(self.thumbnail_size / rect.width, self.thumbnail_size / rect.height)
            matrix = fitz.Matrix(scale, scale)

            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
            data = pix.tobytes("ppm")
            qpix = QPixmap()
            qpix.loadFromData(data)
            doc.close()

            if not self.cancelled:
                self.callback(self.page_num, qpix, self.render_id, self.thumbnail_size)

        except Exception as e:
            if not self.cancelled:
                print(f"[ThumbnailRenderWorker] Error rendering page {self.page_num}: {e}")


class ThumbnailWidget(QWidget):
    """Thumbnail list widget that keeps thumbnails in sync with the PDFViewer.

    Important: thumbnails are identified by ORIGINAL page indices (stable IDs).
    `set_display_order(visible_order)` expects a list of ORIGINAL page indices in the display order.
    """
    page_clicked = Signal(int)  # emits ORIGINAL page index when user clicks thumbnail

    def __init__(self, parent=None):
        super().__init__(parent)

        # Document & cache
        self.document = None
        self.doc_path = ""
        self.document_password = ""
        self.thumbnail_cache = ThumbnailCache()
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)

        # Workers
        self.active_workers: Dict[str, ThumbnailRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # Page state keyed by ORIGINAL page index
        self.page_rotations: Dict[int, int] = {}
        self.deleted_pages: set = set()

        # UI & layout
        self.thumbnail_size = 150
        self.display_order_map: Dict[int, int] = {}  # original -> display index (0-based)

        self._setup_ui()

        # Timers to batch loads
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.load_visible_thumbnails)

        self.load_timer = QTimer(self)
        self.load_timer.setSingleShot(True)
        self.load_timer.timeout.connect(self.load_visible_thumbnails)

    # ---------------- UI setup ----------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListWidget.IconMode)
        self.thumbnail_list.setResizeMode(QListWidget.Adjust)
        self.thumbnail_list.setSpacing(4)
        self.thumbnail_list.setMovement(QListWidget.Static)
        self.thumbnail_list.setSelectionMode(QListWidget.SingleSelection)
        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))
        # lazy load when user scrolls
        self.thumbnail_list.verticalScrollBar().valueChanged.connect(lambda _: self.load_timer.start(50))

        # click/selection
        self.thumbnail_list.itemClicked.connect(self._on_item_clicked)
        self.thumbnail_list.currentItemChanged.connect(self._on_current_item_changed)

        layout.addWidget(self.thumbnail_list)

        # slider
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(100, 300)
        self.size_slider.setValue(self.thumbnail_size)
        self.size_slider.valueChanged.connect(self.on_size_changed)
        layout.addWidget(self.size_slider)

    # ---------------- Document lifecycle ----------------
    def set_document(self, document, doc_path: str, password: str = ""):
        """Attach a fitz.Document instance (document is kept by PDFViewer)."""
        self.clear_thumbnails()
        self.document = document
        self.doc_path = doc_path
        self.document_password = password
        self.page_rotations.clear()
        self.deleted_pages.clear()
        self.display_order_map.clear()

        if document:
            self.create_thumbnail_items()
            self.load_timer.start(200)

    def clear_thumbnails(self):
        with self.render_lock:
            for w in list(self.active_workers.values()):
                try:
                    w.cancel()
                except Exception:
                    pass
            self.active_workers.clear()
        self.thumbnail_list.clear()
        self.thumbnail_cache.clear()
        self.display_order_map.clear()
        self.deleted_pages.clear()

    def create_thumbnail_items(self):
        if self.document is None:
            return
        # create a QListWidgetItem per original page index, store original index in Qt.UserRole
        for orig_index in range(len(self.document)):
            item = QListWidgetItem("")
            item.setData(Qt.UserRole, orig_index)
            item.setSizeHint(QSize(self.thumbnail_size + 12, self.thumbnail_size + 12))
            placeholder = QPixmap(self.thumbnail_size, self.thumbnail_size)
            placeholder.fill(Qt.white)
            item.setIcon(QIcon(self._overlay_page_number(placeholder, orig_index)))
            self.thumbnail_list.addItem(item)
        self.update_grid_size()

    def update_grid_size(self):
        w = self.thumbnail_size + 12
        self.thumbnail_list.setGridSize(QSize(w, w))
        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))
        for i in range(self.thumbnail_list.count()):
            it = self.thumbnail_list.item(i)
            if it:
                it.setSizeHint(QSize(w, w))

    # ---------------- Loading & rendering ----------------
    def load_visible_thumbnails(self):
        # guard: do not access closed doc
        if self.document is None:
            return
        try:
            _ = len(self.document)
        except (ValueError, RuntimeError):
            return

        # determine visible rows
        vp = self.thumbnail_list.viewport().rect()
        first, last = None, None
        for i in range(self.thumbnail_list.count()):
            try:
                r = self.thumbnail_list.visualItemRect(self.thumbnail_list.item(i))
            except Exception:
                continue
            if r.intersects(vp):
                if first is None:
                    first = i
                last = i
        if first is None:
            first, last = 0, self.thumbnail_list.count() - 1

        buf = 5
        start = max(0, first - buf)
        end = min(self.thumbnail_list.count(), last + buf + 1)

        # load by ORIGINAL index stored in item.data
        for idx in range(start, end):
            item = self.thumbnail_list.item(idx)
            if not item:
                continue
            orig = item.data(Qt.UserRole)
            if orig in self.deleted_pages:
                continue
            self._ensure_thumbnail_for_item(item, orig)

    def _ensure_thumbnail_for_item(self, item: QListWidgetItem, orig: int):
        # try cache
        cached = self.thumbnail_cache.get(orig, self.thumbnail_size)
        if cached:
            item.setIcon(QIcon(cached))
            return

        # spawn worker
        with self.render_lock:
            self.current_render_id += 1
            rid = f"thumb_{self.current_render_id}_{orig}_{self.thumbnail_size}"
        rot = self.page_rotations.get(orig, 0)
        w = ThumbnailRenderWorker(self.doc_path, orig, self.on_thumbnail_rendered, rid, self.thumbnail_size, rot, self.document_password)
        with self.render_lock:
            self.active_workers[rid] = w
        self.thread_pool.start(w)

    def on_thumbnail_rendered(self, page_num: int, pixmap: QPixmap, render_id: str, size: int):
        with self.render_lock:
            self.active_workers.pop(render_id, None)
        composed = self._overlay_page_number(pixmap, page_num)
        self.thumbnail_cache.put(page_num, size, composed)
        # set icon on the item with matching original id
        for i in range(self.thumbnail_list.count()):
            it = self.thumbnail_list.item(i)
            if it and it.data(Qt.UserRole) == page_num:
                it.setIcon(QIcon(composed))
                break

    # ---------------- Ordering API ----------------
    def set_display_order(self, visible_order: list[int]):
        """
        visible_order: list of ORIGINAL page indices in display order.
        Reorders the QListWidget items to match the viewer layout, removes deleted items,
        updates overlay numbers, and preserves the thumbnail scrollbar and selection so the UI doesn't jump.
        """
        # remember scrollbar and selection
        scrollbar = self.thumbnail_list.verticalScrollBar()
        old_scroll = scrollbar.value() if scrollbar is not None else 0

        cur_item = self.thumbnail_list.currentItem()
        cur_selected_orig = cur_item.data(Qt.UserRole) if cur_item else None

        # Update display map
        self.display_order_map = {orig: idx for idx, orig in enumerate(visible_order)}

        # Extract existing items
        items = []
        for _ in range(self.thumbnail_list.count()):
            items.append(self.thumbnail_list.takeItem(0))

        # Map by original id
        orig_map = {}
        for it in items:
            if not it:
                continue
            try:
                orig = it.data(Qt.UserRole)
            except Exception:
                orig = None
            if orig is not None:
                orig_map[orig] = it

        # Add visible items in explicit order
        for orig in visible_order:
            it = orig_map.get(orig)
            if it:
                it.setHidden(False)
                self.thumbnail_list.addItem(it)

        # Any leftover items correspond to removed pages; don't re-add them.
        # We also remove them from cache to free memory.
        for orig, it in orig_map.items():
            if orig not in self.display_order_map:
                try:
                    self.thumbnail_cache.remove_page(orig)
                except Exception:
                    pass
                # best-effort: delete reference
                try:
                    del it
                except Exception:
                    pass

        # Update overlays/texts for visible items
        for i in range(self.thumbnail_list.count()):
            it = self.thumbnail_list.item(i)
            if not it:
                continue
            orig = it.data(Qt.UserRole)
            disp_idx = self.display_order_map.get(orig, None)
            if disp_idx is not None:
                # textual fallback under icon
                it.setText(str(disp_idx + 1))
            # refresh cached pixmap overlay if present
            try:
                pix = self.thumbnail_cache.get(orig, self.thumbnail_size)
                if isinstance(pix, QPixmap):
                    it.setIcon(QIcon(self._overlay_page_number(pix, orig)))
            except Exception:
                pass

        # Restore selection (prefer previous selection if still present)
        target_item = None
        if cur_selected_orig is not None:
            for i in range(self.thumbnail_list.count()):
                it = self.thumbnail_list.item(i)
                if it and it.data(Qt.UserRole) == cur_selected_orig:
                    target_item = it
                    break

        if target_item is None and self.thumbnail_list.count() > 0:
            # choose first visible item (safer than jumping to end)
            target_item = self.thumbnail_list.item(0)

        # avoid firing click handlers while changing selection
        try:
            self.thumbnail_list.itemClicked.disconnect()
        except Exception:
            pass
        try:
            self.thumbnail_list.currentItemChanged.disconnect()
        except Exception:
            pass

        if target_item:
            self.thumbnail_list.setCurrentItem(target_item)
            # restore old scroll value (clamped)
            try:
                if scrollbar is not None:
                    maxv = scrollbar.maximum()
                    scrollbar.setValue(min(old_scroll, maxv))
            except Exception:
                pass

        # reconnect signals
        self.thumbnail_list.itemClicked.connect(self._on_item_clicked)
        self.thumbnail_list.currentItemChanged.connect(self._on_current_item_changed)

        # schedule reload of visible icons
        self.load_timer.start(50)

    def set_current_page(self, orig_page: int):
        """
        Highlight thumbnail corresponding to an ORIGINAL page id, but avoid causing
        list to jump to the end. We try to center the item rather than scroll to bottom.
        """
        target_item = None
        for i in range(self.thumbnail_list.count()):
            it = self.thumbnail_list.item(i)
            if it and it.data(Qt.UserRole) == orig_page:
                target_item = it
                break

        if not target_item:
            return

        # disconnect signals, set current, scroll to center, reconnect
        try:
            self.thumbnail_list.itemClicked.disconnect()
        except Exception:
            pass
        try:
            self.thumbnail_list.currentItemChanged.disconnect()
        except Exception:
            pass

        self.thumbnail_list.setCurrentItem(target_item)
        try:
            self.thumbnail_list.scrollToItem(target_item, QListWidget.PositionAtCenter)
        except Exception:
            # fallback: small delay restore
            pass

        self.thumbnail_list.itemClicked.connect(self._on_item_clicked)
        self.thumbnail_list.currentItemChanged.connect(self._on_current_item_changed)

    def hide_page_thumbnail(self, orig_page: int):
        """Hide (mark deleted) thumbnail for an ORIGINAL page index."""
        for i in range(self.thumbnail_list.count()):
            it = self.thumbnail_list.item(i)
            if it and it.data(Qt.UserRole) == orig_page:
                it.setHidden(True)
                self.deleted_pages.add(orig_page)
                self.thumbnail_cache.remove_page(orig_page)
                break

    def rotate_page_thumbnail(self, orig_page: int, rotation: int):
        """Rotate a thumbnail and schedule reload for that original page."""
        current = self.page_rotations.get(orig_page, 0)
        self.page_rotations[orig_page] = (current + rotation) % 360
        self.thumbnail_cache.remove_page(orig_page)
        # find item and set placeholder
        for i in range(self.thumbnail_list.count()):
            it = self.thumbnail_list.item(i)
            if it and it.data(Qt.UserRole) == orig_page:
                placeholder = QPixmap(self.thumbnail_size, self.thumbnail_size)
                placeholder.fill(Qt.white)
                it.setIcon(QIcon(self._overlay_page_number(placeholder, orig_page)))
                break
        QTimer.singleShot(80, self.load_visible_thumbnails)

    # ---------------- Interaction ----------------
    def _on_item_clicked(self, item):
        if not item:
            return
        orig = item.data(Qt.UserRole)
        if orig is not None and orig not in self.deleted_pages:
            self.page_clicked.emit(orig)

    def _on_current_item_changed(self, current, previous):
        if current:
            orig = current.data(Qt.UserRole)
            if orig is not None and orig not in self.deleted_pages:
                self.page_clicked.emit(orig)

    # ---------------- Utilities ----------------
    def _overlay_page_number(self, pixmap: QPixmap, orig_index: int) -> QPixmap:
        """Stamp the display number (from display_order_map) onto pixmap."""
        if not isinstance(pixmap, QPixmap):
            return pixmap
        out = QPixmap(pixmap.size())
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, pixmap)

        h = pixmap.height()
        bar_h = max(16, int(h * 0.12))
        p.fillRect(0, h - bar_h, pixmap.width(), bar_h, QColor(0, 0, 0, 150))

        f = QFont()
        f.setBold(True)
        f.setPointSize(max(8, int(h * 0.08)))
        p.setFont(f)
        p.setPen(Qt.white)

        display_idx = self.display_order_map.get(orig_index)
        if display_idx is None:
            # fallback: count non-deleted originals up to this orig index
            display_idx = sum(1 for k in range(orig_index + 1) if k not in self.deleted_pages) - 1
            if display_idx < 0:
                display_idx = 0

        p.drawText(pixmap.rect().adjusted(0, 0, 0, -2),
                   Qt.AlignHCenter | Qt.AlignBottom,
                   str(display_idx + 1))
        p.end()
        return out

    # ---------------- Events and sizing ----------------
    def on_size_changed(self, value: int):
        if value == self.thumbnail_size:
            return
        self.thumbnail_size = value
        self.thumbnail_list.setIconSize(QSize(value, value))
        self.thumbnail_cache.clear()
        self.update_grid_size()
        self.load_timer.start(200)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_timer.start(250)

    def showEvent(self, event):
        super().showEvent(event)
        if self.document:
            self.load_timer.start(150)
