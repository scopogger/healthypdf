import os
import threading
from typing import Optional, Dict, List
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
        # Store raw thumbnails WITHOUT page numbers
        self.cache: OrderedDict[tuple, QPixmap] = OrderedDict()  # (page_num, size) -> pixmap

    def get_raw(self, page_num: int, size: int) -> Optional[QPixmap]:
        """Get raw thumbnail without page number overlay"""
        key = (page_num, size)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put_raw(self, page_num: int, size: int, pixmap: QPixmap):
        """Store raw thumbnail without page number overlay"""
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
                # Pass raw pixmap WITHOUT page number
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
        self.size_slider = None
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

        # CRITICAL: Track the current display order
        self.display_order: List[int] = []  # List of original page indices in display order

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

        # Remove text label (only show icon)
        self.thumbnail_list.setWordWrap(True)
        self.thumbnail_list.setFlow(QListWidget.LeftToRight)
        self.thumbnail_list.setLayoutMode(QListWidget.Batched)

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

        # Set initial icon size
        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))

        # Connect scroll to lazy load
        self.thumbnail_list.verticalScrollBar().valueChanged.connect(lambda _: self.load_timer.start(50))

        layout.addWidget(self.thumbnail_list)

        # Thumbnail size slider (only one)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setObjectName("thumbnailSizeSlider")  # Unique identifier
        self.size_slider.setRange(100, 300)
        self.size_slider.setValue(self.thumbnail_size)
        self.size_slider.setTickPosition(QSlider.TicksBelow)
        self.size_slider.setTickInterval(50)
        self.size_slider.valueChanged.connect(self.on_size_changed)

        layout.addWidget(self.size_slider)

        # Connect item click and selection change
        self.thumbnail_list.itemClicked.connect(self._on_item_clicked)
        self.thumbnail_list.currentItemChanged.connect(self._on_current_item_changed)

        self.setMinimumWidth(150)

    def set_document(self, document, doc_path: str, password: str = ""):
        """Set the document to display thumbnails for"""
        self.clear_thumbnails()

        self.document = document
        self.doc_path = doc_path
        self.document_password = password
        self.page_rotations.clear()
        self.deleted_pages.clear()

        if document:
            # Initialize display order with original page indices
            self.display_order = list(range(len(document)))
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
        self.display_order = []

    def create_thumbnail_items(self):
        """Create thumbnail items for all pages"""
        if self.document is None:
            return

        for page_num in range(len(self.document)):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, page_num)  # Store ORIGINAL page number
            item.setSizeHint(QSize(self.thumbnail_size + 12, self.thumbnail_size + 12))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

            # Create placeholder with page number
            placeholder = self._create_placeholder_with_number(page_num)
            item.setIcon(QIcon(placeholder))

            self.thumbnail_list.addItem(item)

        # Update grid size
        self.update_grid_size()

    def _create_placeholder_with_number(self, original_page_num: int) -> QPixmap:
        """Create a placeholder pixmap with the current display number"""
        placeholder = QPixmap(self.thumbnail_size, self.thumbnail_size)
        placeholder.fill(Qt.white)

        # Get display number for this page
        display_num = self._get_display_number(original_page_num)

        if display_num is not None:
            painter = QPainter(placeholder)
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw page number bar at bottom
            h = placeholder.height()
            bar_h = max(18, int(h * 0.14))
            painter.fillRect(0, h - bar_h, placeholder.width(), bar_h, QColor(0, 0, 0, 150))

            # Draw page number
            f = painter.font()
            f.setBold(True)
            f.setPointSize(self.page_number_font_size)
            painter.setFont(f)
            painter.setPen(Qt.white)

            painter.drawText(placeholder.rect().adjusted(0, 0, 0, -2),
                             Qt.AlignHCenter | Qt.AlignBottom,
                             str(display_num))
            painter.end()

        return placeholder

    def _get_display_number(self, original_page_num: int) -> Optional[int]:
        """Get 1-based display number for an original page index"""
        if original_page_num in self.deleted_pages:
            return None

        try:
            # Find position in display order
            if original_page_num in self.display_order:
                return self.display_order.index(original_page_num) + 1
        except (ValueError, AttributeError):
            pass

        # Fallback: count non-deleted pages up to this one
        count = 1
        for i in range(original_page_num):
            if i not in self.deleted_pages:
                count += 1
        return count if original_page_num not in self.deleted_pages else None

    def update_grid_size(self):
        """Update the grid size based on current thumbnail size"""
        if self.thumbnail_list.count() == 0:
            return

        item_width = self.thumbnail_size + 12
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

        # Update all thumbnails with new placeholders
        self._refresh_all_thumbnails()

        # Reload visible thumbnails with new size
        self.load_timer.start(200)

    def _refresh_all_thumbnails(self):
        """Refresh all thumbnail icons with updated page numbers"""
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item:
                original_page = item.data(Qt.UserRole)

                # Check if we have a cached raw thumbnail
                raw_pixmap = self.thumbnail_cache.get_raw(original_page, self.thumbnail_size)

                if raw_pixmap:
                    # Add current page number overlay
                    final_pixmap = self._add_page_number_overlay(raw_pixmap, original_page)
                    item.setIcon(QIcon(final_pixmap))
                else:
                    # Use placeholder with number
                    placeholder = self._create_placeholder_with_number(original_page)
                    item.setIcon(QIcon(placeholder))

    def load_visible_thumbnails(self):
        """Load thumbnails for visible items only"""
        if self.document is None or self.thumbnail_list.count() == 0:
            return

        # Get visible range with buffer
        first_visible = None
        last_visible = None

        # Try to get actual visible range
        try:
            viewport_rect = self.thumbnail_list.viewport().rect()
            for i in range(self.thumbnail_list.count()):
                item = self.thumbnail_list.item(i)
                if item and not item.isHidden():
                    item_rect = self.thumbnail_list.visualItemRect(item)
                    if item_rect.intersects(viewport_rect):
                        if first_visible is None:
                            first_visible = i
                        last_visible = i
        except:
            pass

        if first_visible is None or last_visible is None:
            first_visible = 0
            last_visible = min(self.thumbnail_list.count() - 1, len(self.display_order) - 1)

        # Add buffer
        buffer_size = 5
        start = max(0, first_visible - buffer_size)
        end = min(self.thumbnail_list.count(), last_visible + buffer_size + 1)

        for i in range(start, end):
            if i < self.thumbnail_list.count():
                item = self.thumbnail_list.item(i)
                if item and not item.isHidden():
                    original_page = item.data(Qt.UserRole)
                    if original_page is not None and original_page not in self.deleted_pages:
                        self.load_thumbnail(original_page)

    def load_thumbnail(self, original_page_num: int):
        """Load thumbnail for specific page (by original page number)"""
        if original_page_num >= len(self.document):
            return

        # Find the item for this page
        item = None
        for i in range(self.thumbnail_list.count()):
            test_item = self.thumbnail_list.item(i)
            if test_item and test_item.data(Qt.UserRole) == original_page_num:
                item = test_item
                break

        if not item:
            return

        # Check cache first for RAW thumbnail
        cached_raw = self.thumbnail_cache.get_raw(original_page_num, self.thumbnail_size)
        if cached_raw:
            # Add current page number overlay
            final_pixmap = self._add_page_number_overlay(cached_raw, original_page_num)
            item.setIcon(QIcon(final_pixmap))
            return

        # Generate unique render ID
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"thumb_{self.current_render_id}_{original_page_num}_{self.thumbnail_size}"

        # Get rotation for this page
        rotation = self.page_rotations.get(original_page_num, 0)

        # Create worker
        worker = ThumbnailRenderWorker(
            self.doc_path,
            original_page_num,
            self.on_thumbnail_rendered,
            render_id,
            self.thumbnail_size,
            rotation,
            self.document_password
        )

        with self.render_lock:
            self.active_workers[render_id] = worker

        self.thread_pool.start(worker)

    def on_thumbnail_rendered(self, original_page_num: int, raw_pixmap: QPixmap, render_id: str, size: int):
        """Handle rendered thumbnail result"""
        with self.render_lock:
            if render_id in self.active_workers:
                del self.active_workers[render_id]

        # Store RAW pixmap in cache
        self.thumbnail_cache.put_raw(original_page_num, size, raw_pixmap)

        # Find and update the item
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and item.data(Qt.UserRole) == original_page_num:
                # Add current page number overlay
                final_pixmap = self._add_page_number_overlay(raw_pixmap, original_page_num)
                item.setIcon(QIcon(final_pixmap))
                break

    def _add_page_number_overlay(self, raw_pixmap: QPixmap, original_page_num: int) -> QPixmap:
        """Add page number overlay to a raw thumbnail"""
        display_num = self._get_display_number(original_page_num)
        if display_num is None:
            return raw_pixmap

        # Create a copy to avoid modifying the cached version
        result = QPixmap(raw_pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw page number bar at bottom
        h = result.height()
        bar_h = max(18, int(h * 0.14))
        painter.fillRect(0, h - bar_h, result.width(), bar_h, QColor(0, 0, 0, 150))

        # Draw page number
        f = painter.font()
        f.setBold(True)
        f.setPointSize(self.page_number_font_size)
        painter.setFont(f)
        painter.setPen(Qt.white)

        painter.drawText(result.rect().adjusted(0, 0, 0, -2),
                         Qt.AlignHCenter | Qt.AlignBottom,
                         str(display_num))
        painter.end()

        return result

    def _on_item_clicked(self, item):
        if not item:
            return

        # Get the ORIGINAL page number from the item's user data
        page_num = item.data(Qt.UserRole)
        if page_num is not None and page_num not in self.deleted_pages:
            print(f"Thumbnail clicked: original page {page_num}")
            self.page_clicked.emit(page_num)

    def _on_current_item_changed(self, current, previous):
        if not current:
            return

        # Get the ORIGINAL page number from the item's user data
        page_num = current.data(Qt.UserRole)
        if page_num is not None and page_num not in self.deleted_pages:
            print(f"Thumbnail selected: original page {page_num}")
            self.page_clicked.emit(page_num)

    def set_current_page(self, original_page_num: int):
        """Highlight the thumbnail for the given ORIGINAL page number."""
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and not item.isHidden() and item.data(Qt.UserRole) == original_page_num:
                # Temporarily disconnect to avoid recursion
                self.thumbnail_list.itemClicked.disconnect()
                self.thumbnail_list.currentItemChanged.disconnect()

                self.thumbnail_list.setCurrentItem(item)
                self.thumbnail_list.scrollToItem(item)

                # Reconnect signals
                self.thumbnail_list.itemClicked.connect(self._on_item_clicked)
                self.thumbnail_list.currentItemChanged.connect(self._on_current_item_changed)
                break

    def hide_page_thumbnail(self, original_page_num: int):
        """Hide (remove) thumbnail for deleted page"""
        self.deleted_pages.add(original_page_num)

        # Find and remove the item
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and item.data(Qt.UserRole) == original_page_num:
                # remove from the list entirely
                self.thumbnail_list.takeItem(i)
                break

        # Remove from cache and display order
        self.thumbnail_cache.remove_page(original_page_num)

        # Remove from display order
        if original_page_num in self.display_order:
            self.display_order.remove(original_page_num)

    def rotate_page_thumbnail(self, original_page_num: int, rotation: int):
        """Rotate a page thumbnail and reload it"""
        current_rotation = self.page_rotations.get(original_page_num, 0)
        new_rotation = (current_rotation + rotation) % 360
        self.page_rotations[original_page_num] = new_rotation

        # Remove from cache to force reload
        self.thumbnail_cache.remove_page(original_page_num)

        # Find and update the item
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and item.data(Qt.UserRole) == original_page_num:
                # Set placeholder while loading
                placeholder = self._create_placeholder_with_number(original_page_num)
                item.setIcon(QIcon(placeholder))
                break

        # Reload the thumbnail
        QTimer.singleShot(100, lambda: self.load_thumbnail(original_page_num))

    def update_thumbnails_order(self, visible_order: List[int]):
        """Update display order and refresh all thumbnails

        Args:
            visible_order: List of ORIGINAL page indices in their new display order
        """
        # Update our display order
        self.display_order = visible_order.copy()

        # Rebuild the list widget to match the new order
        self.thumbnail_list.clear()

        # Add visible pages in order
        for original_page in visible_order:
            if original_page < len(self.document):
                item = QListWidgetItem()
                item.setData(Qt.UserRole, original_page)
                item.setSizeHint(QSize(self.thumbnail_size + 12, self.thumbnail_size + 12))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                # Check cache for raw thumbnail
                raw_pixmap = self.thumbnail_cache.get_raw(original_page, self.thumbnail_size)
                if raw_pixmap:
                    final_pixmap = self._add_page_number_overlay(raw_pixmap, original_page)
                    item.setIcon(QIcon(final_pixmap))
                else:
                    placeholder = self._create_placeholder_with_number(original_page)
                    item.setIcon(QIcon(placeholder))

                self.thumbnail_list.addItem(item)

        # Note: do NOT append deleted pages as hidden items at the end.
        # Trigger loading of visible thumbnails
        self.load_timer.start(50)

    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        self.resize_timer.start(300)

    def showEvent(self, event):
        """Handle show events"""
        super().showEvent(event)
        if self.document:
            self.load_timer.start(200)

    def wheelEvent(self, event):
        """Handle wheel events to trigger thumbnail loading"""
        super().wheelEvent(event)
        self.load_timer.start(300)
