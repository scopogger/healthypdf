"""
Thumbnail Widget - Displays page thumbnails in sidebar with proper resizing and larger thumbnails
"""
import os
import threading
from typing import Optional, Dict
from collections import OrderedDict

from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QSlider, QLabel,
    QFrame, QInputDialog, QMessageBox, QScrollBar
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRunnable, QThreadPool
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QFont

import fitz  # PyMuPDF


class ThumbnailCache:
    """Cache for thumbnail images with size-aware storage"""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.cache: OrderedDict[tuple, QPixmap] = OrderedDict()  # (page_num, size) -> pixmap

    def get(self, page_num: int, size: int) -> Optional[QPixmap]:
        key = (page_num, size)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, page_num: int, size: int, pixmap: QPixmap):
        key = (page_num, size)
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            self.cache[key] = pixmap
            if len(self.cache) > self.max_size:
                oldest = next(iter(self.cache))
                del self.cache[oldest]

    def clear(self):
        self.cache.clear()

    def remove_page(self, page_num: int):
        """Remove all cached thumbnails for a specific page"""
        keys_to_remove = [key for key in self.cache.keys() if key[0] == page_num]
        for key in keys_to_remove:
            del self.cache[key]


class ThumbnailRenderWorker(QRunnable):
    """Worker for rendering thumbnails in background"""

    def __init__(self, doc_path: str, page_num: int, callback, render_id: str,
                 thumbnail_size: int = 150, rotation: int = 0, password: str = ""):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num
        self.callback = callback
        self.render_id = render_id
        self.thumbnail_size = thumbnail_size
        self.rotation = rotation
        self.cancelled = False
        self.password = password

    def cancel(self):
        self.cancelled = True

    def run(self):
        if self.cancelled:
            return

        try:
            doc = fitz.open(self.doc_path)

            # Handle password protection
            if doc.needs_pass and self.password:
                if not doc.authenticate(self.password):
                    doc.close()
                    return

            if self.cancelled:
                doc.close()
                return

            page = doc[self.page_num]
            if self.cancelled:
                doc.close()
                return

            if self.rotation != 0:
                page.set_rotation(self.rotation)

            # Calculate scale for desired thumbnail size
            rect = page.rect
            scale = min(self.thumbnail_size / rect.width, self.thumbnail_size / rect.height)
            matrix = fitz.Matrix(scale, scale)

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
                self.callback(self.page_num, pixmap, self.render_id, self.thumbnail_size)

        except Exception as e:
            if not self.cancelled:
                print(f"Error rendering thumbnail {self.page_num}: {e}")


class ThumbnailWidget(QWidget):
    """Thumbnail widget for displaying page previews with resizable thumbnails"""

    page_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Document and caching
        self.document = None
        self.doc_path = ""
        self.document_password = ""
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

        # Thumbnail size (can be controlled by slider) and font
        self.thumbnail_size = 150  # Larger default size
        self.page_number_font_size = 10

        # Setup UI
        self.setup_ui()

        # Timer for delayed resize and loading
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.load_visible_thumbnails)

        self.load_timer = QTimer(self)
        self.load_timer.setSingleShot(True)
        self.load_timer.timeout.connect(self.load_visible_thumbnails)

    def setup_ui(self):
        """Setup the thumbnail widget UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # List widget for thumbnails
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListWidget.IconMode)
        self.thumbnail_list.setResizeMode(QListWidget.Adjust)
        self.thumbnail_list.setWrapping(True)
        self.thumbnail_list.setUniformItemSizes(True)
        self.thumbnail_list.setSpacing(2)
        self.thumbnail_list.setMovement(QListWidget.Static)
        self.thumbnail_list.setSelectionMode(QListWidget.SingleSelection)
        self.thumbnail_list.setStyleSheet("""
            QListWidget {
                background-color: #f8f8f8;
                border: 1px solid #ddd;
                border-radius: 3px;
            }
            QListWidget::item {
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 0px;
                margin: 1px;
            }
            QListWidget::item:selected {
                border: 2px solid #0078d4;
                background-color: #e3f2fd;
            }
            QListWidget::item:hover {
                border: 2px solid #90caf9;
                background-color: #f0f8ff;
            }
        """)
        # make the icon (pixmap) actually occupy the cell
        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))
        # trigger visible-only load on scroll
        self.thumbnail_list.verticalScrollBar().valueChanged.connect(lambda _: self.load_timer.start(50))
        layout.addWidget(self.thumbnail_list)

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(100, 300)  # 100px to 300px
        self.size_slider.setValue(self.thumbnail_size)
        self.size_slider.setTickPosition(QSlider.TicksBelow)
        self.size_slider.setTickInterval(50)
        self.size_slider.valueChanged.connect(self.on_size_changed)
        layout.addWidget(self.size_slider)

        # Connect signals (use currentItemChanged—less jank)
        self.thumbnail_list.currentItemChanged.connect(self._on_current_item_changed)

        # Set minimum width
        self.setMinimumWidth(180)

    def authenticate_document(self, file_path: str) -> Optional[str]:
        """Handle password authentication for encrypted PDFs"""
        temp_doc = fitz.open(file_path)

        if temp_doc.needs_pass:
            password, ok = QInputDialog.getText(
                self,
                "Password Required",
                f"Thumbnails: File {os.path.basename(file_path)} is password protected.\nEnter password:",
                QInputDialog.Password
            )

            if ok and password:
                if temp_doc.authenticate(password):
                    temp_doc.close()
                    return password
                else:
                    QMessageBox.warning(self, "Authentication Failed", "Invalid password for thumbnails!")
                    temp_doc.close()
                    return None
            else:
                temp_doc.close()
                return None
        else:
            temp_doc.close()
            return ""

    def set_document(self, document, doc_path: str, password: str = ""):
        """Set the document to display thumbnails for"""
        self.clear_thumbnails()

        self.document = document
        self.doc_path = doc_path
        self.document_password = password
        self.page_rotations.clear()
        self.deleted_pages.clear()

        if document:
            self.create_thumbnail_items()
            # Delay thumbnail loading to prevent freezing
            self.load_timer.start(300)

    def clear_thumbnails(self):
        """Clear all thumbnails and reset state"""
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

        self.thumbnail_list.clear()
        self.thumbnail_cache.clear()

    def create_thumbnail_items(self):
        """Create thumbnail items for all pages"""
        if not self.document:
            return

        for page_num in range(len(self.document)):
            # no text: we draw page number onto the image to avoid extra text spacing
            item = QListWidgetItem("")
            item.setData(Qt.UserRole, page_num)

            # tight cell around the image
            item.setSizeHint(QSize(self.thumbnail_size + 12, self.thumbnail_size + 12))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

            # Add placeholder icon
            placeholder = QPixmap(self.thumbnail_size, self.thumbnail_size)
            placeholder.fill(Qt.white)
            item.setIcon(QIcon(placeholder))

            self.thumbnail_list.addItem(item)

        # Update grid size
        self.update_grid_size()

    def update_grid_size(self):
        """Update the grid size based on current thumbnail size"""
        if self.thumbnail_list.count() == 0:
            return

        item_width = self.thumbnail_size + 12  # tight padding
        item_height = self.thumbnail_size + 12

        self.thumbnail_list.setGridSize(QSize(item_width, item_height))
        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))

        # Update all item size hints
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item:
                item.setSizeHint(QSize(item_width, item_height))

    def on_size_changed(self, value):
        """Handle thumbnail size slider change"""
        if value == self.thumbnail_size:
            return

        self.thumbnail_size = value
        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))

        # Cancel current renders
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

        # Clear cache (different size needed)
        self.thumbnail_cache.clear()

        # Update grid and item sizes
        self.update_grid_size()

        # Clear current icons
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item:
                placeholder = QPixmap(self.thumbnail_size, self.thumbnail_size)
                placeholder.fill(Qt.white)
                item.setIcon(QIcon(placeholder))

        # Reload visible thumbnails with new size
        self.load_timer.start(200)

    def load_visible_thumbnails(self):
        """Load thumbnails for visible items only"""
        if not self.document:
            return

        # Get visible range with buffer
        first_visible = None
        last_visible = None

        # Try to get actual visible range
        try:
            viewport_rect = self.thumbnail_list.viewport().rect()
            for i in range(self.thumbnail_list.count()):
                item = self.thumbnail_list.item(i)
                if item:
                    item_rect = self.thumbnail_list.visualItemRect(item)
                    if item_rect.intersects(viewport_rect):
                        if first_visible is None:
                            first_visible = i
                        last_visible = i
        except:
            pass

        if first_visible is None or last_visible is None:
            first_visible = 0
            last_visible = self.thumbnail_list.count() - 1

        # Add buffer
        buffer_size = 5
        start = max(0, first_visible - buffer_size)
        end = min(self.thumbnail_list.count(), last_visible + buffer_size + 1)

        for page_num in range(start, end):
            if page_num not in self.deleted_pages:
                self.load_thumbnail(page_num)

    def load_thumbnail(self, page_num: int):
        """Load thumbnail for specific page"""
        if page_num >= self.thumbnail_list.count():
            return

        item = self.thumbnail_list.item(page_num)
        if not item:
            return

        # Check cache first
        cached_pixmap = self.thumbnail_cache.get(page_num, self.thumbnail_size)
        if cached_pixmap:
            item.setIcon(QIcon(cached_pixmap))
            return

        # Generate unique render ID
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"thumb_{self.current_render_id}_{page_num}_{self.thumbnail_size}"

        # Get rotation for this page
        rotation = self.page_rotations.get(page_num, 0)

        # Create worker
        worker = ThumbnailRenderWorker(
            self.doc_path,
            page_num,
            self.on_thumbnail_rendered,
            render_id,
            self.thumbnail_size,
            rotation,
            self.document_password
        )

        with self.render_lock:
            self.active_workers[render_id] = worker

        self.thread_pool.start(worker)

    def on_thumbnail_rendered(self, page_num: int, pixmap: QPixmap, render_id: str, size: int):
        """Handle rendered thumbnail result"""
        with self.render_lock:
            if render_id in self.active_workers:
                del self.active_workers[render_id]

        if page_num < self.thumbnail_list.count():
            # paint page number onto the image itself (no extra label space)
            composed = self._overlay_page_number(pixmap, page_num)
            self.thumbnail_cache.put(page_num, size, composed)
            item = self.thumbnail_list.item(page_num)
            if item:
                item.setIcon(QIcon(composed))

    def _on_current_item_changed(self, current, previous):
        """Stable selection handler -> fixes 'always selects first' jank"""
        if not current:
            return
        page_num = current.data(Qt.UserRole)
        # Fallback to row index if user data missing
        if page_num is None:
            page_num = self.thumbnail_list.row(current)
        if page_num not in self.deleted_pages:
            self.page_clicked.emit(page_num)

    def set_current_page(self, page_num: int):
        """Highlight the current page thumbnail"""
        if page_num < self.thumbnail_list.count():
            item = self.thumbnail_list.item(page_num)
            if item and not item.isHidden():
                self.thumbnail_list.setCurrentItem(item)
                self.thumbnail_list.scrollToItem(item)

    def hide_page_thumbnail(self, page_num: int):
        """Hide thumbnail for deleted page"""
        if page_num < self.thumbnail_list.count():
            item = self.thumbnail_list.item(page_num)
            if item:
                item.setHidden(True)
                self.deleted_pages.add(page_num)
                # Remove from cache
                self.thumbnail_cache.remove_page(page_num)

    def rotate_page_thumbnail(self, page_num: int, rotation: int):
        """Rotate a page thumbnail and reload it"""
        if page_num < self.thumbnail_list.count():
            current_rotation = self.page_rotations.get(page_num, 0)
            new_rotation = (current_rotation + rotation) % 360
            self.page_rotations[page_num] = new_rotation

            # Remove from cache
            self.thumbnail_cache.remove_page(page_num)

            item = self.thumbnail_list.item(page_num)
            if item:
                # Set placeholder while loading
                placeholder = QPixmap(self.thumbnail_size, self.thumbnail_size)
                placeholder.fill(Qt.white)
                item.setIcon(QIcon(placeholder))

            # Delay reload to prevent UI freezing
            QTimer.singleShot(100, lambda: self.load_thumbnail(page_num))

    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        self.resize_timer.start(300)

    def showEvent(self, event):
        """Handle show events"""
        super().showEvent(event)
        if self.document:
            self.load_timer.start(200)

    def scrollContentsBy(self, dx, dy):
        """Override to load thumbnails when scrolling"""
        # This method doesn't exist in QWidget, but we handle scroll in the list widget
        pass

    def wheelEvent(self, event):
        """Handle wheel events to trigger thumbnail loading"""
        super().wheelEvent(event)
        self.load_timer.start(300)

    # --- helpers ---
    def _overlay_page_number(self, pixmap: QPixmap, page_index: int) -> QPixmap:
        """Draw a small dark bar with page number at the bottom of the thumbnail"""
        out = QPixmap(pixmap.size())
        out.fill(Qt.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, pixmap)
        h = pixmap.height()
        bar_h = max(18, int(h * 0.14))
        painter.fillRect(0, h - bar_h, pixmap.width(), bar_h, QColor(0, 0, 0, 150))
        f = painter.font()
        f.setBold(True)
        f.setPointSize(self.page_number_font_size)  # Use class variable
        painter.setFont(f)
        painter.setPen(Qt.white)
        painter.drawText(pixmap.rect().adjusted(0, 0, 0, -2), Qt.AlignHCenter | Qt.AlignBottom, f"{page_index + 1}")
        painter.end()
        return out
