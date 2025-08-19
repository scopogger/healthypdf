import sys
import os
from typing import Optional, Dict, Tuple, Set
from dataclasses import dataclass
from collections import OrderedDict
import weakref
import gc
import threading

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QScrollArea, QLabel, QPushButton, QSlider, QSpinBox, QFileDialog,
    QMessageBox, QFrame, QSizePolicy, QProgressBar, QStatusBar,
    QMenuBar, QMenu, QToolBar, QSplitter, QListWidget, QTreeView,
    QListWidgetItem, QLineEdit
)
from PySide6.QtCore import (
    Qt, QThread, QObject, Signal, QTimer, QSize, QRect,
    QRunnable, QThreadPool, QPointF
)
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QAction, QKeySequence,
    QDragEnterEvent, QDropEvent, QIcon
)

import fitz  # PyMuPDF


@dataclass
class PageInfo:
    """Information about a PDF page"""
    page_num: int
    width: int
    height: int
    rotation: int = 0


class PageCache:
    """Aggressive LRU Cache for rendered pages - keeps only essential pages"""

    def __init__(self, max_size: int = 6):
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
                gc.collect()

    def clear(self):
        self.cache.clear()
        gc.collect()

    def keep_only_pages(self, page_numbers: Set[int]):
        """Keep only specified pages in cache, remove all others"""
        pages_to_remove = [p for p in self.cache.keys() if p not in page_numbers]
        for page_num in pages_to_remove:
            del self.cache[page_num]
        if pages_to_remove:
            gc.collect()


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


class PageRenderWorker(QRunnable):
    """Worker for rendering pages in background with cancellation support"""

    def __init__(self, doc_path: str, page_num: int, zoom: float, callback, render_id: str, rotation: int = 0):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num
        self.zoom = zoom
        self.callback = callback
        self.render_id = render_id
        self.rotation = rotation
        self.cancelled = False

    def cancel(self):
        """Cancel this rendering task"""
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

            # Apply rotation if needed
            if self.rotation != 0:
                page.set_rotation(self.rotation)

            # Calculate matrix for zoom with lower quality for memory efficiency
            matrix = fitz.Matrix(self.zoom, self.zoom)

            # Use lower quality settings to reduce memory usage
            pix = page.get_pixmap(
                matrix=matrix,
                alpha=False,
                colorspace=fitz.csRGB,
                clip=None
            )

            if self.cancelled:
                doc.close()
                return

            # Convert to QPixmap with compression
            img_data = pix.tobytes("ppm")
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)

            # Apply mild compression to reduce memory footprint
            if not self.cancelled:
                if pixmap.width() > 2000 or pixmap.height() > 2000:
                    pixmap = pixmap.scaled(
                        min(2000, pixmap.width()),
                        min(2000, pixmap.height()),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )

            doc.close()

            if not self.cancelled:
                self.callback(self.page_num, pixmap, self.render_id)

        except Exception as e:
            if not self.cancelled:
                print(f"Error rendering page {self.page_num}: {e}")


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

            matrix = fitz.Matrix(0.2, 0.2)  # 20% scale for thumbnails

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


class IntegratedThumbnailWidget(QListWidget):
    """Enhanced thumbnail widget that integrates with the old UI design"""

    page_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSpacing(10)
        self.setMovement(QListWidget.Static)

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
            self.load_all_thumbnails()

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
            item.setSizeHint(QSize(120, 160))
            self.addItem(item)

    def load_all_thumbnails(self):
        """Start loading all thumbnails in background"""
        if not self.document:
            return

        for page_num in range(len(self.document)):
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

    def hide_page_thumbnail(self, page_num: int):
        """Hide thumbnail for deleted page"""
        if page_num < self.count():
            item = self.item(page_num)
            if item:
                item.setHidden(True)

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

            self.load_thumbnail(page_num)

    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        self.resize_timer.start(100)

    def adjust_grid_size_delayed(self):
        """Adjust grid size with delay to avoid excessive updates"""
        if self.count() == 0:
            return

        width = self.viewport().width()
        item_width = 120  # Fixed thumbnail width
        num_columns = max(1, (width - self.spacing()) // (item_width + self.spacing()))
        grid_width = (width - (num_columns + 1) * self.spacing()) // num_columns

        new_grid_size = QSize(grid_width, item_width + 30)

        if new_grid_size != self.gridSize():
            self.setGridSize(new_grid_size)


class IntegratedPDFViewer(QScrollArea):
    """Enhanced PDF viewer that integrates efficient rendering with the old UI architecture"""

    page_changed = Signal(int)
    document_modified = Signal(bool)  # New signal for document modification status

    def __init__(self, parent=None):
        super().__init__(parent)

        # Core properties
        self.document = None
        self.doc_path = ""
        self.pages_info = []
        self.page_widgets = []
        self.zoom_level = 1.0

        # Document modification tracking (from new version)
        self.is_modified = False
        self.deleted_pages = set()
        self.page_order = []
        self.page_rotations = {}

        # Caching and threading (from new version)
        self.page_cache = PageCache(max_size=6)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(2)

        # Track active render tasks
        self.active_workers: Dict[str, PageRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # UI setup
        self.setup_ui()

        # Timer for lazy loading
        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.update_visible_pages)

        # Connect scroll events
        self.verticalScrollBar().valueChanged.connect(self.on_scroll)

        # Last visible pages for cleanup
        self.last_visible_pages = set()

    def setup_ui(self):
        """Setup the scrollable area"""
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignCenter)

        # Container widget for pages
        self.pages_container = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setSpacing(10)
        self.pages_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.setWidget(self.pages_container)

    def open_document(self, file_path: str) -> bool:
        """Open a PDF document (enhanced from new version)"""
        try:
            self.close_document()
            self.zoom_level = 1.0

            self.document = fitz.open(file_path)
            self.doc_path = file_path

            # Reset modification tracking
            self.is_modified = False
            self.deleted_pages = set()
            self.page_order = list(range(len(self.document)))
            self.page_rotations = {}

            # Get page information
            self.pages_info = []
            for page_num in range(len(self.document)):
                page = self.document[page_num]
                rect = page.rect
                page_info = PageInfo(
                    page_num=page_num,
                    width=int(rect.width),
                    height=int(rect.height)
                )
                self.pages_info.append(page_info)

            self.create_page_widgets()
            self.verticalScrollBar().setValue(0)

            QTimer.singleShot(50, self.update_visible_pages)

            return True

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open PDF: {e}")
            return False

    def close_document(self):
        """Close current document and clear resources (enhanced from new version)"""
        self.cancel_all_renders()

        if self.document:
            self.document.close()
            self.document = None

        self.doc_path = ""
        self.pages_info.clear()
        self.page_cache.clear()
        self.last_visible_pages.clear()

        # Reset modification tracking
        self.is_modified = False
        self.deleted_pages = set()
        self.page_order = []
        self.page_rotations = {}

        # Clear page widgets
        for widget in self.page_widgets:
            widget.deleteLater()
        self.page_widgets.clear()

        # Clear layout
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        gc.collect()

    def cancel_all_renders(self):
        """Cancel all active rendering tasks"""
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

    def create_page_widgets(self):
        """Create placeholder widgets for all pages"""
        self.page_widgets = []

        for page_info in self.pages_info:
            display_width = int(page_info.width * self.zoom_level)
            display_height = int(page_info.height * self.zoom_level)

            page_widget = QLabel(f"Page {page_info.page_num + 1}")
            page_widget.setMinimumSize(display_width, display_height)
            page_widget.setAlignment(Qt.AlignCenter)
            page_widget.setStyleSheet("""
                QLabel {
                    border: 1px solid #ccc;
                    background-color: #f5f5f5;
                    color: #666;
                }
            """)

            self.page_widgets.append(page_widget)
            self.pages_layout.addWidget(page_widget)

    def on_scroll(self):
        """Handle scroll events"""
        self.cancel_all_renders()
        self.scroll_timer.start(100)

    def update_visible_pages(self):
        """Update pages that are visible with aggressive memory management"""
        if not self.document:
            return

        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()

        # Find visible pages
        buffer_pages = 1
        visible_pages = set()
        current_center_page = None

        viewport_center_y = scroll_y + viewport_rect.height() // 2

        for i, widget in enumerate(self.page_widgets):
            widget_center_y = widget.y() + widget.height() // 2
            widget_y = widget.y() - scroll_y
            widget_bottom = widget_y + widget.height()

            if widget_bottom >= 0 and widget_y <= viewport_rect.height():
                visible_pages.add(i)

                if current_center_page is None or abs(widget_center_y - viewport_center_y) < abs(
                        self.page_widgets[current_center_page].y() + self.page_widgets[
                            current_center_page].height() // 2 - viewport_center_y):
                    current_center_page = i

        # Add buffer pages
        if current_center_page is not None:
            for offset in range(-buffer_pages, buffer_pages + 1):
                page_num = current_center_page + offset
                if 0 <= page_num < len(self.page_widgets):
                    visible_pages.add(page_num)

        # Clean up cache
        self.page_cache.keep_only_pages(visible_pages)

        # Reset non-visible widgets
        for page_num in self.last_visible_pages - visible_pages:
            if page_num < len(self.page_widgets):
                widget = self.page_widgets[page_num]
                page_info = self.pages_info[page_num]
                display_width = int(page_info.width * self.zoom_level)
                display_height = int(page_info.height * self.zoom_level)
                widget.setFixedSize(display_width, display_height)
                widget.clear()
                widget.setText(f"Page {page_num + 1}")
                widget.setStyleSheet("""
                    QLabel {
                        border: 1px solid #ccc;
                        background-color: #f5f5f5;
                        color: #666;
                    }
                """)

        # Load visible pages
        for page_num in visible_pages:
            self.load_page(page_num)

        self.last_visible_pages = visible_pages.copy()

        if current_center_page is not None:
            self.page_changed.emit(current_center_page)

        gc.collect()

    def load_page(self, page_num: int):
        """Load a specific page with cancellation support"""
        if page_num >= len(self.page_widgets):
            return

        widget = self.page_widgets[page_num]

        # Check if already loaded
        if hasattr(widget, 'pixmap') and widget.pixmap():
            return

        # Check cache
        cached_pixmap = self.page_cache.get(page_num)
        if cached_pixmap:
            widget.setPixmap(cached_pixmap)
            widget.setFixedSize(cached_pixmap.size())
            widget.setStyleSheet("")
            return

        # Generate render ID
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"render_{self.current_render_id}_{page_num}"

        # Get rotation
        rotation = self.page_rotations.get(page_num, 0)

        # Create worker
        worker = PageRenderWorker(
            self.doc_path,
            page_num,
            self.zoom_level,
            self.on_page_rendered,
            render_id,
            rotation
        )

        with self.render_lock:
            self.active_workers[render_id] = worker

        self.thread_pool.start(worker)

    def on_page_rendered(self, page_num: int, pixmap: QPixmap, render_id: str):
        """Handle rendered page result"""
        with self.render_lock:
            if render_id in self.active_workers:
                del self.active_workers[render_id]

        if page_num not in self.last_visible_pages:
            return

        if page_num < len(self.page_widgets):
            self.page_cache.put(page_num, pixmap)
            widget = self.page_widgets[page_num]

            if not (hasattr(widget, 'pixmap') and widget.pixmap()):
                widget.setPixmap(pixmap)
                widget.setFixedSize(pixmap.size())
                widget.setStyleSheet("")

    def set_zoom(self, zoom: float):
        """Set zoom level and refresh pages"""
        if not self.document or zoom == self.zoom_level:
            return

        self.cancel_all_renders()
        self.zoom_level = zoom
        self.page_cache.clear()

        # Reset all widgets
        for i, widget in enumerate(self.page_widgets):
            page_info = self.pages_info[i]
            display_width = int(page_info.width * self.zoom_level)
            display_height = int(page_info.height * self.zoom_level)
            widget.setMinimumSize(display_width, display_height)
            widget.setFixedSize(display_width, display_height)
            widget.clear()
            widget.setText(f"Page {i + 1}")
            widget.setStyleSheet("""
                QLabel {
                    border: 1px solid #ccc;
                    background-color: #f5f5f5;
                    color: #666;
                }
            """)

        gc.collect()
        QTimer.singleShot(50, self.update_visible_pages)

    def get_current_page(self) -> int:
        """Get the currently centered page number"""
        if not self.document or not self.page_widgets:
            return 0

        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()
        viewport_center_y = scroll_y + viewport_rect.height() // 2

        current_page = 0
        min_distance = float('inf')

        for i, widget in enumerate(self.page_widgets):
            if widget.isHidden():
                continue

            widget_center_y = widget.y() + widget.height() // 2
            distance = abs(widget_center_y - viewport_center_y)

            if distance < min_distance:
                min_distance = distance
                current_page = i

        return current_page

    # Page manipulation methods (from new version)
    def rotate_page_clockwise(self):
        """Rotate current page clockwise by 90 degrees"""
        return self._rotate_page(90)

    def rotate_page_counterclockwise(self):
        """Rotate current page counterclockwise by 90 degrees"""
        return self._rotate_page(-90)

    def _rotate_page(self, rotation: int):
        """Internal method to rotate a page"""
        if not self.document:
            return False

        current_page = self.get_current_page()

        current_rotation = self.page_rotations.get(current_page, 0)
        new_rotation = (current_rotation + rotation) % 360
        self.page_rotations[current_page] = new_rotation

        self.is_modified = True
        self.document_modified.emit(True)

        # Clear cached version
        if current_page in self.page_cache.cache:
            del self.page_cache.cache[current_page]

        # Force re-render
        self.force_render_visible_pages()
        return True

    def delete_current_page(self):
        """Delete the current page"""
        if not self.document:
            return False

        current_page = self.get_current_page()

        # Check if it's the last remaining page
        remaining_pages = len(self.pages_info) - len(self.deleted_pages)
        if remaining_pages <= 1:
            QMessageBox.warning(None, "Cannot Delete", "Cannot delete the last remaining page.")
            return False

        self.deleted_pages.add(current_page)
        self.is_modified = True
        self.document_modified.emit(True)

        # Hide the widget
        if current_page < len(self.page_widgets):
            widget = self.page_widgets[current_page]
            widget.hide()

        self.page_changed.emit(self.get_current_page())
        self.force_render_visible_pages()
        self.update_visible_pages()
        return True

    def move_page_up(self):
        """Move current page up by one position"""
        if not self.document:
            return False

        current_page = self.get_current_page()

        # Find current widget and previous visible widget
        current_widget = None
        current_layout_pos = -1

        for i in range(self.pages_layout.count()):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), 'objectName'):
                widget = item.widget()
                if widget == self.page_widgets[current_page] and not widget.isHidden():
                    current_widget = widget
                    current_layout_pos = i
                    break

        if current_widget is None or current_layout_pos <= 0:
            return False

        # Find previous visible widget
        prev_widget = None
        prev_layout_pos = -1

        for i in range(current_layout_pos - 1, -1, -1):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() and not item.widget().isHidden():
                prev_widget = item.widget()
                prev_layout_pos = i
                break

        if prev_widget is None:
            return False

        # Swap widgets
        self.pages_layout.removeWidget(current_widget)
        self.pages_layout.removeWidget(prev_widget)

        self.pages_layout.insertWidget(prev_layout_pos, current_widget)
        self.pages_layout.insertWidget(current_layout_pos, prev_widget)

        self.is_modified = True
        self.document_modified.emit(True)
        self.page_changed.emit(self.get_current_page())
        self.force_render_visible_pages()
        return True

    def move_page_down(self):
        """Move current page down by one position"""
        if not self.document:
            return False

        current_page = self.get_current_page()

        # Find current widget
        current_widget = None
        current_layout_pos = -1

        for i in range(self.pages_layout.count()):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), 'objectName'):
                widget = item.widget()
                if widget == self.page_widgets[current_page] and not widget.isHidden():
                    current_widget = widget
                    current_layout_pos = i
                    break

        if current_widget is None:
            return False

        # Find next visible widget
        next_widget = None
        next_layout_pos = -1

        for i in range(current_layout_pos + 1, self.pages_layout.count()):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() and not item.widget().isHidden():
                next_widget = item.widget()
                next_layout_pos = i
                break

        if next_widget is None:
            return False

        # Swap widgets
        self.pages_layout.removeWidget(current_widget)
        self.pages_layout.removeWidget(next_widget)

        self.pages_layout.insertWidget(current_layout_pos, next_widget)
        self.pages_layout.insertWidget(next_layout_pos, current_widget)

        self.is_modified = True
        self.document_modified.emit(True)
        self.force_render_visible_pages()
        self.page_changed.emit(self.get_current_page())
        return True

    def force_render_visible_pages(self):
        """Force re-render all currently visible pages"""
        self.cancel_all_renders()
        QTimer.singleShot(50, self.update_visible_pages)

    def go_to_page(self, page_num: int):
        """Navigate to specific page"""
        if 0 <= page_num < len(self.page_widgets):
            self.cancel_all_renders()
            widget = self.page_widgets[page_num]
            self.ensureWidgetVisible(widget)

    def save_changes(self, file_path: str = None) -> bool:
        """Save changes to file (enhanced from new version)"""
        if not self.document or not self.is_modified:
            return True

        try:
            save_path = file_path if file_path else self.doc_path

            # Create new document with modifications
            new_doc = fitz.open()

            # Get current page order from layout (only visible pages)
            page_order = []
            for i in range(self.pages_layout.count()):
                item = self.pages_layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if not widget.isHidden():
                        # Find which page this widget represents
                        for j, page_widget in enumerate(self.page_widgets):
                            if page_widget == widget:
                                page_order.append(j)
                                break

            # Copy pages in the new order with rotations applied
            for page_num in page_order:
                if 0 <= page_num < len(self.document):
                    temp_doc = fitz.open()
                    temp_doc.insert_pdf(self.document, from_page=page_num, to_page=page_num)

                    # Apply rotation if needed
                    rotation = self.page_rotations.get(page_num, 0)
                    if rotation != 0:
                        temp_page = temp_doc[0]
                        temp_page.set_rotation(rotation)

                    new_doc.insert_pdf(temp_doc)
                    temp_doc.close()

            # Save the new document
            if save_path == self.doc_path:
                import tempfile
                import shutil

                temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(temp_fd)

                new_doc.save(temp_path)
                new_doc.close()

                self.document.close()
                shutil.move(temp_path, self.doc_path)
                self.document = fitz.open(self.doc_path)
            else:
                new_doc.save(save_path)
                new_doc.close()

            # Reset modification state
            self.is_modified = False
            self.deleted_pages.clear()
            self.page_rotations.clear()
            self.document_modified.emit(False)

            return True

        except Exception as e:
            QMessageBox.critical(None, "Save Error", f"Failed to save PDF: {e}")
            return False

    def has_unsaved_changes(self) -> bool:
        """Check if document has unsaved changes"""
        return self.is_modified


class ZoomSelector(QWidget):
    """Zoom selector widget compatible with old UI"""

    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_viewer = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.zoom_input = QLineEdit()
        self.zoom_input.setFixedWidth(60)
        self.zoom_input.setText("100%")
        self.zoom_input.editingFinished.connect(self._on_zoom_input_changed)

        layout.addWidget(self.zoom_input)

    def set_pdf_viewer(self, viewer):
        """Connect to PDF viewer"""
        self.pdf_viewer = viewer

    def _on_zoom_input_changed(self):
        """Handle zoom input change"""
        try:
            text = self.zoom_input.text().replace('%', '')
            zoom_percent = float(text)
            zoom_factor = zoom_percent / 100.0

            if self.pdf_viewer:
                self.pdf_viewer.set_zoom(zoom_factor)

            self.zoom_changed.emit(zoom_factor)
        except ValueError:
            # Reset to current zoom if invalid input
            if self.pdf_viewer:
                current_zoom = int(self.pdf_viewer.zoom_level * 100)
                self.zoom_input.setText(f"{current_zoom}%")

    def set_zoom_value(self, zoom_factor: float):
        """Set zoom value programmatically"""
        zoom_percent = int(zoom_factor * 100)
        self.zoom_input.setText(f"{zoom_percent}%")


class IntegratedMainWindow(QMainWindow):
    """Main window that integrates both UI systems"""

    def __init__(self):
        super().__init__()

        # Core components
        self.pdf_viewer = None
        self.thumbnail_widget = None
        self.zoom_selector = None

        # UI state
        self.current_document_path = ""

        # Setup UI
        self.setup_ui()
        self.setup_menus()
        self.setup_toolbar()
        self.setup_status_bar()

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Window settings
        self.setWindowTitle("Integrated PDF Editor")
        self.resize(1400, 800)

        # Update initial state
        self.update_ui_state()

    def setup_ui(self):
        """Setup main UI layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)

        # Create splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel for thumbnails
        left_panel = QWidget()
        left_panel.setMinimumWidth(180)
        left_panel.setMaximumWidth(250)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(2, 2, 2, 2)

        # Thumbnail label
        thumbnail_label = QLabel("Page Thumbnails")
        thumbnail_label.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        thumbnail_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(thumbnail_label)

        # Thumbnail widget
        self.thumbnail_widget = IntegratedThumbnailWidget()
        self.thumbnail_widget.page_clicked.connect(self.on_thumbnail_clicked)
        left_layout.addWidget(self.thumbnail_widget)

        # Thumbnail size slider
        self.thumbnail_size_slider = QSlider(Qt.Horizontal)
        self.thumbnail_size_slider.setRange(0, 19)
        self.thumbnail_size_slider.setValue(1)
        self.thumbnail_size_slider.setTickPosition(QSlider.TicksBelow)
        self.thumbnail_size_slider.setTickInterval(1)
        left_layout.addWidget(self.thumbnail_size_slider)

        splitter.addWidget(left_panel)

        # Main PDF viewer
        self.pdf_viewer = IntegratedPDFViewer()
        self.pdf_viewer.page_changed.connect(self.on_page_changed)
        self.pdf_viewer.document_modified.connect(self.on_document_modified)
        splitter.addWidget(self.pdf_viewer)

        # Set initial splitter sizes
        splitter.setSizes([200, 1200])
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, False)

        layout.addWidget(splitter)

    def setup_menus(self):
        """Setup menu bar (compatible with old UI)"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        self.action_open = QAction("Open...", self)
        self.action_open.setShortcut(QKeySequence.Open)
        self.action_open.triggered.connect(self.open_file)
        file_menu.addAction(self.action_open)

        self.action_close = QAction("Close", self)
        self.action_close.setShortcut(QKeySequence.Close)
        self.action_close.triggered.connect(self.close_file)
        file_menu.addAction(self.action_close)

        file_menu.addSeparator()

        self.action_save = QAction("Save", self)
        self.action_save.setShortcut(QKeySequence.Save)
        self.action_save.triggered.connect(self.save_file)
        file_menu.addAction(self.action_save)

        self.action_save_as = QAction("Save As...", self)
        self.action_save_as.setShortcut(QKeySequence.SaveAs)
        self.action_save_as.triggered.connect(self.save_file_as)
        file_menu.addAction(self.action_save_as)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")

        self.action_delete_page = QAction("Delete Current Page", self)
        self.action_delete_page.setShortcut("Delete")
        self.action_delete_page.triggered.connect(self.delete_current_page)
        edit_menu.addAction(self.action_delete_page)

        edit_menu.addSeparator()

        self.action_move_up = QAction("Move Page Up", self)
        self.action_move_up.setShortcut("Ctrl+Up")
        self.action_move_up.triggered.connect(self.move_page_up)
        edit_menu.addAction(self.action_move_up)

        self.action_move_down = QAction("Move Page Down", self)
        self.action_move_down.setShortcut("Ctrl+Down")
        self.action_move_down.triggered.connect(self.move_page_down)
        edit_menu.addAction(self.action_move_down)

        edit_menu.addSeparator()

        self.action_rotate_cw = QAction("Rotate Clockwise", self)
        self.action_rotate_cw.setShortcut("Ctrl+R")
        self.action_rotate_cw.triggered.connect(self.rotate_clockwise)
        edit_menu.addAction(self.action_rotate_cw)

        self.action_rotate_ccw = QAction("Rotate Counterclockwise", self)
        self.action_rotate_ccw.setShortcut("Ctrl+Shift+R")
        self.action_rotate_ccw.triggered.connect(self.rotate_counterclockwise)
        edit_menu.addAction(self.action_rotate_ccw)

        # View menu
        view_menu = menubar.addMenu("View")

        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(zoom_out_action)

    def setup_toolbar(self):
        """Setup toolbar (compatible with old UI)"""
        toolbar = self.addToolBar("Main")

        # File operations
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_save)
        toolbar.addAction(self.action_save_as)
        toolbar.addSeparator()

        # Navigation
        prev_page_action = QAction("Previous Page", self)
        prev_page_action.triggered.connect(self.previous_page)
        toolbar.addAction(prev_page_action)

        next_page_action = QAction("Next Page", self)
        next_page_action.triggered.connect(self.next_page)
        toolbar.addAction(next_page_action)

        toolbar.addSeparator()

        # Page input
        self.page_input = QLineEdit()
        self.page_input.setFixedWidth(60)
        self.page_input.setPlaceholderText("Page")
        self.page_input.editingFinished.connect(self.go_to_page_input)
        toolbar.addWidget(self.page_input)

        self.page_label = QLabel("of 0")
        toolbar.addWidget(self.page_label)

        toolbar.addSeparator()

        # Zoom controls
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedSize(30, 30)
        zoom_out_btn.clicked.connect(self.zoom_out)
        toolbar.addWidget(zoom_out_btn)

        self.zoom_selector = ZoomSelector()
        self.zoom_selector.set_pdf_viewer(self.pdf_viewer)
        toolbar.addWidget(self.zoom_selector)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(30, 30)
        zoom_in_btn.clicked.connect(self.zoom_in)
        toolbar.addWidget(zoom_in_btn)

        toolbar.addSeparator()

        # Page manipulation
        toolbar.addAction(self.action_delete_page)
        toolbar.addAction(self.action_move_up)
        toolbar.addAction(self.action_move_down)
        toolbar.addAction(self.action_rotate_cw)
        toolbar.addAction(self.action_rotate_ccw)

    def setup_status_bar(self):
        """Setup status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("No document")
        self.status_bar.addWidget(self.status_label)

    def update_ui_state(self):
        """Update UI state based on document availability"""
        has_document = self.pdf_viewer.document is not None

        # Update actions
        self.action_save.setEnabled(has_document and self.pdf_viewer.has_unsaved_changes())
        self.action_save_as.setEnabled(has_document)
        self.action_close.setEnabled(has_document)
        self.action_delete_page.setEnabled(has_document)
        self.action_move_up.setEnabled(has_document)
        self.action_move_down.setEnabled(has_document)
        self.action_rotate_cw.setEnabled(has_document)
        self.action_rotate_ccw.setEnabled(has_document)

    # Event handlers
    def on_thumbnail_clicked(self, page_num: int):
        """Handle thumbnail click"""
        self.pdf_viewer.go_to_page(page_num)

    def on_page_changed(self, page_num: int):
        """Handle page change in viewer"""
        self.thumbnail_widget.set_current_page(page_num)
        self.update_status_bar(page_num)

        # Update page input
        self.page_input.setText(str(page_num + 1))

    def on_document_modified(self, is_modified: bool):
        """Handle document modification status change"""
        self.update_ui_state()

        # Update window title
        if self.current_document_path:
            filename = os.path.basename(self.current_document_path)
            if is_modified and "*" not in self.windowTitle():
                self.setWindowTitle(f"Integrated PDF Editor - {filename}*")
            elif not is_modified and "*" in self.windowTitle():
                self.setWindowTitle(f"Integrated PDF Editor - {filename}")

    def update_status_bar(self, current_page: int = 0):
        """Update status bar"""
        if self.pdf_viewer.document:
            # Count visible pages
            visible_count = 0
            for i in range(len(self.pdf_viewer.page_widgets)):
                if not self.pdf_viewer.page_widgets[i].isHidden():
                    visible_count += 1

            self.status_label.setText(f"Page {current_page + 1} of {visible_count}")
            self.page_label.setText(f"of {visible_count}")
        else:
            self.status_label.setText("No document")
            self.page_label.setText("of 0")

    # File operations
    def open_file(self):
        """Open PDF file dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            "",
            "PDF Files (*.pdf)"
        )

        if file_path:
            if self.pdf_viewer.has_unsaved_changes():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "The current document has unsaved changes. Do you want to save them?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
                )

                if reply == QMessageBox.Save:
                    if not self.pdf_viewer.save_changes():
                        return
                elif reply == QMessageBox.Cancel:
                    return

            if self.pdf_viewer.open_document(file_path):
                self.current_document_path = file_path
                filename = os.path.basename(file_path)
                self.setWindowTitle(f"Integrated PDF Editor - {filename}")

                # Update thumbnail panel
                self.thumbnail_widget.set_document(self.pdf_viewer.document, file_path)

                self.update_ui_state()
                self.update_status_bar()

    def close_file(self):
        """Close current document"""
        if self.pdf_viewer.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "The current document has unsaved changes. Do you want to save them?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )

            if reply == QMessageBox.Save:
                if not self.pdf_viewer.save_changes():
                    return
            elif reply == QMessageBox.Cancel:
                return

        self.pdf_viewer.close_document()
        self.thumbnail_widget.clear_thumbnails()
        self.current_document_path = ""
        self.setWindowTitle("Integrated PDF Editor")

        self.update_ui_state()
        self.update_status_bar()

    def save_file(self):
        """Save changes to current file"""
        if not self.current_document_path:
            self.save_file_as()
            return

        if self.pdf_viewer.save_changes():
            self.on_document_modified(False)

    def save_file_as(self):
        """Save changes to a new file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF As",
            "",
            "PDF Files (*.pdf)"
        )

        if file_path:
            if self.pdf_viewer.save_changes(file_path):
                self.current_document_path = file_path
                filename = os.path.basename(file_path)
                self.setWindowTitle(f"Integrated PDF Editor - {filename}")

    # Page operations
    def delete_current_page(self):
        """Delete the current page"""
        if self.pdf_viewer.delete_current_page():
            current_page = self.pdf_viewer.get_current_page()
            self.thumbnail_widget.hide_page_thumbnail(current_page)
            self.update_status_bar()

    def move_page_up(self):
        """Move current page up"""
        if self.pdf_viewer.move_page_up():
            self.update_status_bar()

    def move_page_down(self):
        """Move current page down"""
        if self.pdf_viewer.move_page_down():
            self.update_status_bar()

    def rotate_clockwise(self):
        """Rotate current page clockwise"""
        if self.pdf_viewer.rotate_page_clockwise():
            current_page = self.pdf_viewer.get_current_page()
            self.thumbnail_widget.rotate_page_thumbnail(current_page, 90)
            self.update_status_bar()

    def rotate_counterclockwise(self):
        """Rotate current page counterclockwise"""
        if self.pdf_viewer.rotate_page_counterclockwise():
            current_page = self.pdf_viewer.get_current_page()
            self.thumbnail_widget.rotate_page_thumbnail(current_page, -90)
            self.update_status_bar()

    # Navigation
    def previous_page(self):
        """Go to previous page"""
        current = self.pdf_viewer.get_current_page()
        if current > 0:
            self.pdf_viewer.go_to_page(current - 1)

    def next_page(self):
        """Go to next page"""
        current = self.pdf_viewer.get_current_page()
        if current < len(self.pdf_viewer.page_widgets) - 1:
            self.pdf_viewer.go_to_page(current + 1)

    def go_to_page_input(self):
        """Handle page input"""
        try:
            page_num = int(self.page_input.text()) - 1
            if 0 <= page_num < len(self.pdf_viewer.page_widgets):
                self.pdf_viewer.go_to_page(page_num)
        except ValueError:
            # Reset to current page if invalid input
            current = self.pdf_viewer.get_current_page()
            self.page_input.setText(str(current + 1))

    # Zoom operations
    def zoom_in(self):
        """Zoom in"""
        current_zoom = self.pdf_viewer.zoom_level
        new_zoom = min(5.0, current_zoom * 1.25)
        self.pdf_viewer.set_zoom(new_zoom)
        self.zoom_selector.set_zoom_value(new_zoom)

    def zoom_out(self):
        """Zoom out"""
        current_zoom = self.pdf_viewer.zoom_level
        new_zoom = max(0.1, current_zoom * 0.8)
        self.pdf_viewer.set_zoom(new_zoom)
        self.zoom_selector.set_zoom_value(new_zoom)

    # Drag and drop
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith('.pdf'):
                event.accept()
            else:
                event.ignore()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle drop events"""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.pdf'):
                if self.pdf_viewer.open_document(file_path):
                    self.current_document_path = file_path
                    filename = os.path.basename(file_path)
                    self.setWindowTitle(f"Integrated PDF Editor - {filename}")
                    self.thumbnail_widget.set_document(self.pdf_viewer.document, file_path)
                    self.update_ui_state()
                    self.update_status_bar()

    def closeEvent(self, event):
        """Handle application close event"""
        if self.pdf_viewer.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "The current document has unsaved changes. Do you want to save them?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )

            if reply == QMessageBox.Save:
                if not self.pdf_viewer.save_changes():
                    event.ignore()
                    return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        event.accept()


def main():
    """Main entry point for the application"""
    from argparse import ArgumentParser, RawTextHelpFormatter

    argument_parser = ArgumentParser(
        description="AltPDF",
        formatter_class=RawTextHelpFormatter
    )
    argument_parser.add_argument(
        "file", help="The file to open", nargs='?', type=str
    )
    options = argument_parser.parse_args()

    # Default theme (Windows dark mode flag for PySide6 GUIs)
    sys.argv += ['-platform', 'windows:darkmode=1']

    # Create QApplication
    app = QApplication(sys.argv)

    # Set application properties
    app.setApplicationName("Integrated PDF Editor")
    app.setApplicationDisplayName("PDF Editor")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("PDF Tools")

    try:
        window = IntegratedMainWindow()
        window.show()

        # If a file was passed as command line argument, open it
        if options.file and os.path.exists(options.file) and options.file.lower().endswith('.pdf'):
            window.load_document(options.file)
        elif options.file:
            print(f"Warning: File '{options.file}' not found or not a PDF file")

        sys.exit(app.exec())

    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
