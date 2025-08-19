"""
Thumbnail Widget - Displays page thumbnails in sidebar
"""

import threading
from typing import Optional, Dict
from collections import OrderedDict

from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRunnable, QThreadPool
from PySide6.QtGui import QPixmap, QIcon

import fitz  # PyMuPDF


class ThumbnailCache:
    """Cache for thumbnail images"""

    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self.cache: OrderedDict[int, QPixmap] = OrderedDict()

    def get(self, page_num: int) -> Optional[QPixmap]:
        if page_num in self.cache:
            self.cache.move_to_end(page_num)
            return self.cache[page_num]
        return None

    def put(self, page_num: int, pixmap: QPixmap):
        if page_num in self.cache:
            self.cache.move_to_end(page_num)
        else:
            self.cache[page_num] = pixmap
            if len(self.cache) > self.max_size:
                oldest = next(iter(self.cache))
                del self.cache[oldest]

    def clear(self):
        self.cache.clear()


class ThumbnailRenderWorker(QRunnable):
    """Worker for rendering thumbnails in background"""

    def __init__(self, doc_path: str, page_num: int, callback, render_id: str, rotation: int = 0):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num
        self.callback = callback
        self.render_id = render_id
        self.rotation = rotation
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        if self.cancelled:
            return

        try:
            doc = fitz.open(self.doc_path)
            if self.cancelled:
                doc.close()
                return

            page = doc[self.page_num]
            if self.cancelled:
                doc.close()
                return

            if self.rotation != 0:
                page.set_rotation(self.rotation)

            # Small scale for thumbnails
            matrix = fitz.Matrix(0.15, 0.15)

            pix = page.get_pixmap(
                matrix=matrix,
                alpha=False,
                colorspace=fitz.csRGB
            )

            if self.cancelled:
                doc.close()
                return

            img_data = pix.tobytes("ppm")
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)

            doc.close()

            if not self.cancelled:
                self.callback(self.page_num, pixmap, self.render_id)

        except Exception as e:
            if not self.cancelled:
                print(f"Error rendering thumbnail {self.page_num}: {e}")


class ThumbnailWidget(QListWidget):
    """Thumbnail widget for displaying page previews"""

    page_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Setup list widget
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSpacing(8)
        self.setMovement(QListWidget.Static)
        self.setMaximumWidth(250)
        self.setMinimumWidth(150)

        # Document and caching
        self.document = None
        self.doc_path = ""
        self.thumbnail_cache = ThumbnailCache()
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)

        # Track active render tasks
        self.active_workers: Dict[str, ThumbnailRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # Page modifications tracking
        self.page_rotations = {}
        self.deleted_pages = set()

        # Connect signals
        self.itemClicked.connect(self._on_item_clicked)

        # Timer for delayed resize
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.adjust_grid_size_delayed)

    def set_document(self, document, doc_path: str):
        """Set the document to display thumbnails for"""
        self.clear_thumbnails()

        self.document = document
        self.doc_path = doc_path
        self.page_rotations.clear()
        self.deleted_pages.clear()

        if document:
            self.create_thumbnail_items()
            # Delay thumbnail loading to prevent freezing
            QTimer.singleShot(200, self.load_visible_thumbnails)

    def clear_thumbnails(self):
        """Clear all thumbnails and reset state"""
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

        self.clear()
        self.thumbnail_cache.clear()

    def create_thumbnail_items(self):
        """Create thumbnail items for all pages"""
        if not self.document:
            return

        for page_num in range(len(self.document)):
            item = QListWidgetItem(f"Page {page_num + 1}")
            item.setData(Qt.UserRole, page_num)
            item.setSizeHint(QSize(100, 130))
            item.setTextAlignment(Qt.AlignCenter)
            self.addItem(item)

    def load_visible_thumbnails(self):
        """Load thumbnails for visible items only"""
        if not self.document:
            return

        # Get visible range
        first_visible = self.indexAt(self.rect().topLeft()).row()
        last_visible = self.indexAt(self.rect().bottomLeft()).row()
        
        if first_visible < 0:
            first_visible = 0
        if last_visible < 0 or last_visible >= self.count():
            last_visible = self.count() - 1

        # Load thumbnails for visible range + small buffer
        buffer_size = 3
        start = max(0, first_visible - buffer_size)
        end = min(self.count(), last_visible + buffer_size + 1)

        for page_num in range(start, end):
            self.load_thumbnail(page_num)

    def load_thumbnail(self, page_num: int):
        """Load thumbnail for specific page"""
        if page_num >= self.count():
            return

        item = self.item(page_num)
        if not item:
            return

        # Check cache first
        cached_pixmap = self.thumbnail_cache.get(page_num)
        if cached_pixmap:
            item.setIcon(QIcon(cached_pixmap))
            return

        # Generate unique render ID
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"thumb_{self.current_render_id}_{page_num}"

        # Get rotation for this page
        rotation = self.page_rotations.get(page_num, 0)

        # Create worker
        worker = ThumbnailRenderWorker(
            self.doc_path,
            page_num,
            self.on_thumbnail_rendered,
            render_id,
            rotation
        )

        with self.render_lock:
            self.active_workers[render_id] = worker

        self.thread_pool.start(worker)

    def on_thumbnail_rendered(self, page_num: int, pixmap: QPixmap, render_id: str):
        """Handle rendered thumbnail result"""
        with self.render_lock:
            if render_id in self.active_workers:
                del self.active_workers[render_id]

        if page_num < self.count():
            self.thumbnail_cache.put(page_num, pixmap)
            item = self.item(page_num)
            if item:
                item.setIcon(QIcon(pixmap))

    def _on_item_clicked(self, item):
        """Handle item click"""
        page_num = item.data(Qt.UserRole)
        if page_num is not None:
            self.page_clicked.emit(page_num)

    def set_current_page(self, page_num: int):
        """Highlight the current page thumbnail"""
        for i in range(self.count()):
            item = self.item(i)
            if item:
                if i == page_num:
                    self.setCurrentItem(item)
                    self.scrollToItem(item)

    def hide_page_thumbnail(self, page_num: int):
        """Hide thumbnail for deleted page"""
        if page_num < self.count():
            item = self.item(page_num)
            if item:
                item.setHidden(True)
                self.deleted_pages.add(page_num)

    def rotate_page_thumbnail(self, page_num: int, rotation: int):
        """Rotate a page thumbnail and reload it"""
        if page_num < self.count():
            current_rotation = self.page_rotations.get(page_num, 0)
            new_rotation = (current_rotation + rotation) % 360
            self.page_rotations[page_num] = new_rotation

            # Clear from cache and reload
            if page_num in self.thumbnail_cache.cache:
                del self.thumbnail_cache.cache[page_num]

            item = self.item(page_num)
            if item:
                item.setIcon(QIcon())  # Clear icon

            # Delay reload to prevent UI freezing
            QTimer.singleShot(100, lambda: self.load_thumbnail(page_num))

    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        self.resize_timer.start(200)

    def adjust_grid_size_delayed(self):
        """Adjust grid size with delay to avoid excessive updates"""
        if self.count() == 0:
            return

        width = self.viewport().width()
        item_width = 100  # Fixed thumbnail width
        margin = 20
        
        if width > item_width + margin:
            new_grid_size = QSize(width - margin, item_width + 40)
            if new_grid_size != self.gridSize():
                self.setGridSize(new_grid_size)

    def scrollContentsBy(self, dx, dy):
        """Override to load thumbnails when scrolling"""
        super().scrollContentsBy(dx, dy)
        # Load thumbnails for newly visible items after scroll
        QTimer.singleShot(300, self.load_visible_thumbnails)