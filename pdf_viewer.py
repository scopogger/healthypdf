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
    QMenuBar, QMenu, QToolBar, QSplitter
)
from PySide6.QtCore import (
    Qt, QThread, QObject, Signal, QTimer, QSize, QRect,
    QRunnable, QThreadPool
)
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QAction, QKeySequence,
    QDragEnterEvent, QDropEvent
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

    def __init__(self, max_size: int = 6):  # Reduced from 20 to 6
        self.max_size = max_size
        self.cache: OrderedDict[int, QPixmap] = OrderedDict()

    def get(self, page_num: int) -> Optional[QPixmap]:
        if page_num in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(page_num)
            return self.cache[page_num]
        return None

    def put(self, page_num: int, pixmap: QPixmap):
        if page_num in self.cache:
            self.cache.move_to_end(page_num)
        else:
            self.cache[page_num] = pixmap
            if len(self.cache) > self.max_size:
                # Remove least recently used
                oldest = next(iter(self.cache))
                del self.cache[oldest]
                gc.collect()  # Force garbage collection

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

            # Small scale for thumbnail
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
                alpha=False,  # No alpha channel
                colorspace=fitz.csRGB,  # Use RGB instead of CMYK
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
                # Scale down slightly if very large to save memory
                if pixmap.width() > 2000 or pixmap.height() > 2000:
                    pixmap = pixmap.scaled(
                        min(2000, pixmap.width()),
                        min(2000, pixmap.height()),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )

            doc.close()

            if not self.cancelled:
                # Call callback with result
                self.callback(self.page_num, pixmap, self.render_id)

        except Exception as e:
            if not self.cancelled:
                print(f"Error rendering page {self.page_num}: {e}")


class ThumbnailWidget(QLabel):
    """Widget to display a page thumbnail"""

    clicked = Signal(int)  # Emits page number when clicked

    def __init__(self, page_num: int, parent=None):
        super().__init__(parent)
        self.page_num = page_num
        self.is_loaded = False
        self.is_current = False

        # Set fixed size for thumbnails
        self.setFixedSize(120, 160)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(True)

        # Style
        self.update_style()

        # Placeholder text
        self.setText(f"Page\n{page_num + 1}")

    def update_style(self):
        """Update styling based on current state"""
        if self.is_current:
            self.setStyleSheet("""
                QLabel {
                    border: 3px solid #007ACC;
                    background-color: #f0f8ff;
                    color: #333;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("""
                QLabel {
                    border: 1px solid #ccc;
                    background-color: #f9f9f9;
                    color: #666;
                    font-size: 10px;
                }
                QLabel:hover {
                    border: 2px solid #007ACC;
                    background-color: #f5f8ff;
                }
            """)

    def set_pixmap(self, pixmap: QPixmap):
        """Set the thumbnail pixmap"""
        # Scale pixmap to fit widget while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.setPixmap(scaled_pixmap)
        self.is_loaded = True

    def set_current(self, is_current: bool):
        """Mark this thumbnail as current page"""
        if self.is_current != is_current:
            self.is_current = is_current
            self.update_style()

    def mousePressEvent(self, event):
        """Handle mouse click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.page_num)


class ThumbnailPanel(QScrollArea):
    """Scrollable panel showing page thumbnails"""

    page_clicked = Signal(int)  # Emitted when a thumbnail is clicked

    def __init__(self, parent=None):
        super().__init__(parent)

        self.document = None
        self.doc_path = ""
        self.thumbnail_widgets = []
        self.thumbnail_cache = ThumbnailCache()
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)  # Only one thumbnail renderer

        # Track active render tasks
        self.active_workers: Dict[str, ThumbnailRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # Page rotations (page_num -> rotation_degrees)
        self.page_rotations = {}

        self.setup_ui()

    def setup_ui(self):
        """Setup the thumbnail panel UI"""
        self.setFixedWidth(140)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Container widget
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setSpacing(5)
        self.layout.setAlignment(Qt.AlignTop)

        self.setWidget(self.container)

    def set_document(self, document, doc_path: str):
        """Set the document to display thumbnails for"""
        self.clear_thumbnails()

        self.document = document
        self.doc_path = doc_path
        self.page_rotations.clear()

        if document:
            self.create_thumbnail_widgets()
            self.load_all_thumbnails()

    def clear_thumbnails(self):
        """Clear all thumbnails and reset state"""
        # Cancel active renders
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

        # Clear widgets
        for widget in self.thumbnail_widgets:
            widget.deleteLater()
        self.thumbnail_widgets.clear()

        # Clear layout
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.thumbnail_cache.clear()

    def create_thumbnail_widgets(self):
        """Create thumbnail widgets for all pages"""
        if not self.document:
            return

        for page_num in range(len(self.document)):
            widget = ThumbnailWidget(page_num)
            widget.clicked.connect(self.on_thumbnail_clicked)

            self.thumbnail_widgets.append(widget)
            self.layout.addWidget(widget)

    def load_all_thumbnails(self):
        """Start loading all thumbnails in background"""
        if not self.document:
            return

        for page_num in range(len(self.document)):
            self.load_thumbnail(page_num)

    def load_thumbnail(self, page_num: int):
        """Load thumbnail for specific page"""
        if page_num >= len(self.thumbnail_widgets):
            return

        widget = self.thumbnail_widgets[page_num]
        if widget.is_loaded:
            return

        # Check cache first
        cached_pixmap = self.thumbnail_cache.get(page_num)
        if cached_pixmap:
            widget.set_pixmap(cached_pixmap)
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

        if page_num < len(self.thumbnail_widgets):
            # Cache the pixmap
            self.thumbnail_cache.put(page_num, pixmap)

            # Update widget
            widget = self.thumbnail_widgets[page_num]
            if not widget.is_loaded:
                widget.set_pixmap(pixmap)

    def on_thumbnail_clicked(self, page_num: int):
        """Handle thumbnail click"""
        self.page_clicked.emit(page_num)

    def set_current_page(self, page_num: int):
        """Highlight the current page thumbnail"""
        for i, widget in enumerate(self.thumbnail_widgets):
            widget.set_current(i == page_num)

    def hide_page_thumbnail(self, page_num: int):
        """Hide thumbnail for deleted page"""
        if page_num < len(self.thumbnail_widgets):
            self.thumbnail_widgets[page_num].hide()

    def rotate_page_thumbnail(self, page_num: int, rotation: int):
        """Rotate a page thumbnail and reload it"""
        if page_num < len(self.thumbnail_widgets):
            # Update rotation tracking
            current_rotation = self.page_rotations.get(page_num, 0)
            new_rotation = (current_rotation + rotation) % 360
            self.page_rotations[page_num] = new_rotation

            # Clear from cache and reload
            if page_num in self.thumbnail_cache.cache:
                del self.thumbnail_cache.cache[page_num]

            widget = self.thumbnail_widgets[page_num]
            widget.is_loaded = False
            widget.clear()
            widget.setText(f"Page\n{page_num + 1}")
            widget.update_style()

            # Reload with new rotation
            self.load_thumbnail(page_num)


class PageWidget(QLabel):
    """Widget to display a single PDF page"""

    def __init__(self, page_num: int, page_info: PageInfo, parent=None):
        super().__init__(parent)
        self.page_num = page_num
        self.page_info = page_info
        self.is_loaded = False

        # Set placeholder
        self.setMinimumSize(200, 280)  # A4 ratio placeholder
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                border: 1px solid #ccc;
                background-color: #f5f5f5;
                color: #666;
            }
        """)
        self.setText(f"Page {page_num + 1}")

    def set_pixmap(self, pixmap: QPixmap):
        """Set the rendered page pixmap"""
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.is_loaded = True
        self.setStyleSheet("")  # Remove placeholder styling


class PDFViewer(QScrollArea):
    """Main PDF viewing widget with aggressive lazy loading and cancellation"""

    page_changed = Signal(int)  # Emitted when visible page changes

    def __init__(self, parent=None):
        super().__init__(parent)

        self.document = None
        self.doc_path = ""
        self.pages_info = []
        self.page_widgets = []
        self.zoom_level = 1.0

        # Document modification tracking
        self.is_modified = False
        self.deleted_pages = set()
        self.page_order = []  # Track current page order
        self.page_rotations = {}  # Track page rotations

        # Cache and thread pool with aggressive memory management
        self.page_cache = PageCache(max_size=6)  # Only 6 pages max
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(2)  # Reduced threads

        # Track active render tasks for cancellation
        self.active_workers: Dict[str, PageRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # Setup UI
        self.setup_ui()

        # Timer for lazy loading with faster response
        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.update_visible_pages)

        # Connect scroll events
        self.verticalScrollBar().valueChanged.connect(self.on_scroll)

        # Last visible pages for cleanup
        self.last_visible_pages = set()

    def force_render_visible_pages(self):
        """Force re-render all currently visible pages with slight delay"""
        self.cancel_all_renders()
        QTimer.singleShot(50, self.update_visible_pages)

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
        """Open a PDF document"""
        try:
            # Clear existing document completely
            self.close_document()

            # Reset zoom level to 100% for new document
            self.zoom_level = 1.0

            # Open new document
            self.document = fitz.open(file_path)
            self.doc_path = file_path

            # Track if document has been modified
            self.is_modified = False
            self.deleted_pages = set()  # Track deleted page numbers
            self.page_order = list(range(len(self.document)))  # Track current page order
            self.page_rotations = {}  # Track page rotations

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

            # Create page widgets (placeholders initially)
            self.create_page_widgets()

            # Reset scroll position to top
            self.verticalScrollBar().setValue(0)

            # Start loading visible pages
            QTimer.singleShot(50, self.update_visible_pages)

            return True

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open PDF: {e}")
            return False

    def close_document(self):
        """Close current document and clear resources"""
        # Cancel all active rendering tasks
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

        # Force cleanup
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
            # Calculate display size based on zoom
            display_width = int(page_info.width * self.zoom_level)
            display_height = int(page_info.height * self.zoom_level)

            page_widget = PageWidget(page_info.page_num, page_info)
            page_widget.setMinimumSize(display_width, display_height)

            self.page_widgets.append(page_widget)
            self.pages_layout.addWidget(page_widget)

    def on_scroll(self):
        """Handle scroll events with immediate cancellation of irrelevant renders"""
        # Cancel existing renders immediately
        self.cancel_all_renders()

        # Start timer for new renders
        self.scroll_timer.start(100)  # Faster debounce

    def update_visible_pages(self):
        """Update pages that are visible with aggressive memory management"""
        if not self.document:
            return

        # Get viewport rectangle
        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()

        # Find currently centered page and immediate neighbors only
        buffer_pages = 1  # Reduced buffer - only 1 page ahead/behind
        visible_pages = set()
        current_center_page = None

        # Find the page closest to center of viewport
        viewport_center_y = scroll_y + viewport_rect.height() // 2

        for i, widget in enumerate(self.page_widgets):
            widget_center_y = widget.y() + widget.height() // 2
            widget_y = widget.y() - scroll_y
            widget_bottom = widget_y + widget.height()

            # Check if page is actually visible
            if widget_bottom >= 0 and widget_y <= viewport_rect.height():
                visible_pages.add(i)

                # Check if this is the center page
                if current_center_page is None or abs(widget_center_y - viewport_center_y) < abs(
                        self.page_widgets[current_center_page].y() + self.page_widgets[
                            current_center_page].height() // 2 - viewport_center_y):
                    current_center_page = i

        # Add buffer pages around center page
        if current_center_page is not None:
            for offset in range(-buffer_pages, buffer_pages + 1):
                page_num = current_center_page + offset
                if 0 <= page_num < len(self.page_widgets):
                    visible_pages.add(page_num)

        # Aggressively clean up cache - keep only visible pages
        self.page_cache.keep_only_pages(visible_pages)

        # Reset widgets that are no longer visible
        for page_num in self.last_visible_pages - visible_pages:
            if page_num < len(self.page_widgets):
                widget = self.page_widgets[page_num]
                if widget.is_loaded:
                    # Reset to placeholder to free pixmap memory
                    widget.is_loaded = False
                    page_info = self.pages_info[widget.page_num]
                    display_width = int(page_info.width * self.zoom_level)
                    display_height = int(page_info.height * self.zoom_level)
                    widget.setFixedSize(display_width, display_height)
                    widget.clear()  # Clear pixmap
                    widget.setText(f"Page {widget.page_num + 1}")
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

        # Update last visible pages
        self.last_visible_pages = visible_pages.copy()

        # Emit page changed signal for status bar
        if current_center_page is not None:
            self.page_changed.emit(current_center_page)

        # Force garbage collection after cleanup
        gc.collect()

    def get_current_page(self) -> int:
        """Get the currently centered page number with proper handling of deleted/moved pages"""
        if not self.document or not self.page_widgets:
            return 0

        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()
        viewport_center_y = scroll_y + viewport_rect.height() // 2

        # Find visible page closest to viewport center
        current_page = 0
        min_distance = float('inf')

        for i in range(self.pages_layout.count()):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), 'page_num'):
                widget = item.widget()
                if widget.isHidden():  # Skip deleted pages
                    continue

                widget_center_y = widget.y() + widget.height() // 2
                distance = abs(widget_center_y - viewport_center_y)

                if distance < min_distance:
                    min_distance = distance
                    current_page = widget.page_num

        return current_page

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

        # Update rotation tracking
        current_rotation = self.page_rotations.get(current_page, 0)
        new_rotation = (current_rotation + rotation) % 360
        self.page_rotations[current_page] = new_rotation

        self.is_modified = True

        # Clear cached version of this page
        if current_page in self.page_cache.cache:
            del self.page_cache.cache[current_page]

        # Force re-render
        self.force_render_visible_pages()

        return True

    def delete_current_page(self):
        """Delete the current page (mark for deletion)"""
        if not self.document:
            return False

        current_page = self.get_current_page()

        # Check if it's the last remaining page
        remaining_pages = len(self.pages_info) - len(self.deleted_pages)
        if remaining_pages <= 1:
            QMessageBox.warning(None, "Cannot Delete", "Cannot delete the last remaining page.")
            return False

        # Mark page as deleted
        self.deleted_pages.add(current_page)
        self.is_modified = True

        # Hide the widget
        if current_page < len(self.page_widgets):
            widget = self.page_widgets[current_page]
            widget.hide()

        self.page_changed.emit(self.get_current_page())
        # Force re-render of visible pages
        self.force_render_visible_pages()

        # Update display
        self.update_visible_pages()
        return True

    def move_page_up(self):
        """Move current page up by one position (like move_page_down but inverted)"""
        if not self.document:
            return False

        current_page = self.get_current_page()

        # Find current widget
        current_widget = None
        current_layout_pos = -1

        for i in range(self.pages_layout.count()):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), 'page_num'):
                widget = item.widget()
                if widget.page_num == current_page and not widget.isHidden():
                    current_widget = widget
                    current_layout_pos = i
                    break

        if current_widget is None or current_layout_pos <= 0:
            return False  # Can't move up from first position

        # Find the previous visible widget
        prev_widget = None
        prev_layout_pos = -1

        for i in range(current_layout_pos - 1, -1, -1):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() and not item.widget().isHidden():
                prev_widget = item.widget()
                prev_layout_pos = i
                break

        if prev_widget is None:
            return False  # No previous visible page

        # Swap the widgets
        self.pages_layout.removeWidget(current_widget)
        self.pages_layout.removeWidget(prev_widget)

        self.pages_layout.insertWidget(prev_layout_pos, current_widget)
        self.pages_layout.insertWidget(current_layout_pos, prev_widget)

        self.is_modified = True
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
            if item and item.widget() and hasattr(item.widget(), 'page_num'):
                widget = item.widget()
                if widget.page_num == current_page and not widget.isHidden():
                    current_widget = widget
                    current_layout_pos = i
                    break

        if current_widget is None:
            return False

        # Find the next visible widget
        next_widget = None
        next_layout_pos = -1

        for i in range(current_layout_pos + 1, self.pages_layout.count()):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() and not item.widget().isHidden():
                next_widget = item.widget()
                next_layout_pos = i
                break

        if next_widget is None:
            return False  # No next visible page

        # Swap the widgets
        self.pages_layout.removeWidget(current_widget)
        self.pages_layout.removeWidget(next_widget)

        self.pages_layout.insertWidget(current_layout_pos, next_widget)
        self.pages_layout.insertWidget(next_layout_pos, current_widget)

        self.is_modified = True
        self.force_render_visible_pages()
        self.page_changed.emit(self.get_current_page())
        return True

    def save_changes(self, file_path: str = None) -> bool:
        """Save changes to file"""
        if not self.document or not self.is_modified:
            return True

        try:
            # Use current file path if none provided
            save_path = file_path if file_path else self.doc_path

            # Create new document with modifications
            new_doc = fitz.open()

            # Get current page order from layout (only visible pages)
            page_order = []
            for i in range(self.pages_layout.count()):
                item = self.pages_layout.itemAt(i)
                if item and item.widget() and hasattr(item.widget(), 'page_num'):
                    widget = item.widget()
                    if not widget.isHidden():  # Only non-deleted pages
                        page_order.append(widget.page_num)

            # Copy pages in the new order with rotations applied
            for page_num in page_order:
                if 0 <= page_num < len(self.document):
                    # Create a temporary document for this page with rotation
                    temp_doc = fitz.open()
                    temp_doc.insert_pdf(self.document, from_page=page_num, to_page=page_num)

                    # Apply rotation if needed
                    rotation = self.page_rotations.get(page_num, 0)
                    if rotation != 0:
                        temp_page = temp_doc[0]
                        temp_page.set_rotation(rotation)

                    # Insert into new document
                    new_doc.insert_pdf(temp_doc)
                    temp_doc.close()

            # Save the new document
            if save_path == self.doc_path:
                # Saving to same file - use temporary file approach
                import tempfile
                import shutil

                temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(temp_fd)

                new_doc.save(temp_path)
                new_doc.close()

                # Close original document before replacing
                self.document.close()

                # Replace original with temporary file
                shutil.move(temp_path, self.doc_path)

                # Reopen the document
                self.document = fitz.open(self.doc_path)
            else:
                # Saving to new file
                new_doc.save(save_path)
                new_doc.close()

            # Reset modification state
            self.is_modified = False
            self.deleted_pages.clear()
            self.page_rotations.clear()

            return True

        except Exception as e:
            QMessageBox.critical(None, "Save Error", f"Failed to save PDF: {e}")
            return False

    def has_unsaved_changes(self) -> bool:
        """Check if document has unsaved changes"""
        return self.is_modified

    def load_page(self, page_num: int):
        """Load a specific page with cancellation support"""
        if page_num >= len(self.page_widgets):
            return

        widget = self.page_widgets[page_num]
        if widget.is_loaded:
            return

        # Check cache first
        cached_pixmap = self.page_cache.get(page_num)
        if cached_pixmap:
            widget.set_pixmap(cached_pixmap)
            return

        # Generate unique render ID
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"render_{self.current_render_id}_{page_num}"

        # Get rotation for this page
        rotation = self.page_rotations.get(page_num, 0)

        # Create and start worker
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
        """Handle rendered page result with validation"""
        # Remove from active workers
        with self.render_lock:
            if render_id in self.active_workers:
                del self.active_workers[render_id]

        # Check if page is still relevant (user might have scrolled away)
        if page_num not in self.last_visible_pages:
            # Page is no longer visible, discard the result
            return

        if page_num < len(self.page_widgets):
            # Cache the pixmap
            self.page_cache.put(page_num, pixmap)

            # Update widget if still relevant
            widget = self.page_widgets[page_num]
            if not widget.is_loaded:  # Double check
                widget.set_pixmap(pixmap)

    def set_zoom(self, zoom: float):
        """Set zoom level and refresh pages"""
        if not self.document or zoom == self.zoom_level:
            return

        # Cancel all renders immediately
        self.cancel_all_renders()

        self.zoom_level = zoom

        # Clear cache as zoom changed
        self.page_cache.clear()

        # Mark all pages as not loaded and reset to placeholders
        for widget in self.page_widgets:
            widget.is_loaded = False
            # Reset to placeholder
            page_info = self.pages_info[widget.page_num]
            display_width = int(page_info.width * self.zoom_level)
            display_height = int(page_info.height * self.zoom_level)
            widget.setMinimumSize(display_width, display_height)
            widget.setFixedSize(display_width, display_height)
            widget.clear()  # Clear pixmap to free memory
            widget.setText(f"Page {widget.page_num + 1}")
            widget.setStyleSheet("""
                QLabel {
                    border: 1px solid #ccc;
                    background-color: #f5f5f5;
                    color: #666;
                }
            """)

        # Force garbage collection
        gc.collect()

        # Refresh visible pages
        QTimer.singleShot(50, self.update_visible_pages)

    def go_to_page(self, page_num: int):
        """Navigate to specific page"""
        if 0 <= page_num < len(self.page_widgets):
            # Cancel current renders when jumping to different page
            self.cancel_all_renders()
            widget = self.page_widgets[page_num]
            self.ensureWidgetVisible(widget)


class PDFEditor(QMainWindow):
    """Main PDF Editor window"""

    def __init__(self):
        super().__init__()

        self.pdf_viewer = None
        self.thumbnail_panel = None
        self.current_document_path = ""

        self.setup_ui()
        self.setup_menus()
        self.setup_toolbar()
        self.setup_status_bar()

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Window settings
        self.setWindowTitle("PDF Editor")
        self.resize(1400, 800)

        # Initialize toolbar state
        self.update_toolbar_state()

    def update_toolbar_state(self):
        """Update toolbar button states based on document status"""
        has_document = self.pdf_viewer.document is not None

        # Enable/disable page manipulation buttons
        self.delete_btn.setEnabled(has_document)
        self.move_up_btn.setEnabled(has_document)
        self.move_down_btn.setEnabled(has_document)
        self.rotate_cw_btn.setEnabled(has_document)
        self.rotate_ccw_btn.setEnabled(has_document)
        self.save_btn.setEnabled(has_document)
        self.save_as_btn.setEnabled(has_document)

        # Update menu actions
        if hasattr(self, 'delete_page_action'):
            self.delete_page_action.setEnabled(has_document)
            self.move_up_action.setEnabled(has_document)
            self.move_down_action.setEnabled(has_document)
            self.rotate_cw_action.setEnabled(has_document)
            self.rotate_ccw_action.setEnabled(has_document)

    def setup_ui(self):
        """Setup main UI layout with splitter"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)

        # Create splitter for thumbnail panel and main viewer
        splitter = QSplitter(Qt.Horizontal)

        # Thumbnail Panel
        self.thumbnail_panel = ThumbnailPanel()
        self.thumbnail_panel.page_clicked.connect(self.on_thumbnail_clicked)
        splitter.addWidget(self.thumbnail_panel)

        # PDF Viewer
        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.page_changed.connect(self.on_page_changed)
        splitter.addWidget(self.pdf_viewer)

        # Set initial splitter sizes (thumbnail panel smaller)
        splitter.setSizes([140, 1000])
        splitter.setCollapsible(0, True)  # Allow thumbnail panel to collapse
        splitter.setCollapsible(1, False)  # Don't allow main viewer to collapse

        layout.addWidget(splitter)

    def on_thumbnail_clicked(self, page_num: int):
        """Handle thumbnail click - navigate to that page"""
        self.pdf_viewer.go_to_page(page_num)

    def setup_menus(self):
        """Setup menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        close_action = QAction("Close", self)
        close_action.setShortcut(QKeySequence.Close)
        close_action.triggered.connect(self.close_file)
        file_menu.addAction(close_action)

        file_menu.addSeparator()

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")

        self.delete_page_action = QAction("Delete Current Page", self)
        self.delete_page_action.setShortcut("Delete")
        self.delete_page_action.triggered.connect(self.delete_current_page)
        edit_menu.addAction(self.delete_page_action)

        edit_menu.addSeparator()

        self.move_up_action = QAction("Move Page Up", self)
        self.move_up_action.setShortcut("Ctrl+Up")
        self.move_up_action.triggered.connect(self.move_page_up)
        edit_menu.addAction(self.move_up_action)

        self.move_down_action = QAction("Move Page Down", self)
        self.move_down_action.setShortcut("Ctrl+Down")
        self.move_down_action.triggered.connect(self.move_page_down)
        edit_menu.addAction(self.move_down_action)

        edit_menu.addSeparator()

        self.rotate_cw_action = QAction("Rotate Clockwise", self)
        self.rotate_cw_action.setShortcut("Ctrl+R")
        self.rotate_cw_action.triggered.connect(self.rotate_clockwise)
        edit_menu.addAction(self.rotate_cw_action)

        self.rotate_ccw_action = QAction("Rotate Counterclockwise", self)
        self.rotate_ccw_action.setShortcut("Ctrl+Shift+R")
        self.rotate_ccw_action.triggered.connect(self.rotate_counterclockwise)
        edit_menu.addAction(self.rotate_ccw_action)

    def setup_toolbar(self):
        """Setup toolbar with zoom and page manipulation controls"""
        toolbar = self.addToolBar("Main")

        # Zoom controls
        toolbar.addWidget(QLabel("Zoom:"))

        # Zoom out button
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedSize(30, 30)
        zoom_out_btn.clicked.connect(self.zoom_out)
        toolbar.addWidget(zoom_out_btn)

        # Zoom slider
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 500)  # 10% to 500%
        self.zoom_slider.setValue(100)  # 100%
        self.zoom_slider.setFixedWidth(200)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        toolbar.addWidget(self.zoom_slider)

        # Zoom in button
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(30, 30)
        zoom_in_btn.clicked.connect(self.zoom_in)
        toolbar.addWidget(zoom_in_btn)

        # Zoom percentage
        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        toolbar.addWidget(self.zoom_label)

        toolbar.addSeparator()

        # Page manipulation controls
        self.delete_btn = QPushButton("Delete Page")
        self.delete_btn.clicked.connect(self.delete_current_page)
        self.delete_btn.setEnabled(False)
        toolbar.addWidget(self.delete_btn)

        self.move_up_btn = QPushButton("Move Up")
        self.move_up_btn.clicked.connect(self.move_page_up)
        self.move_up_btn.setEnabled(False)
        toolbar.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("Move Down")
        self.move_down_btn.clicked.connect(self.move_page_down)
        self.move_down_btn.setEnabled(False)
        toolbar.addWidget(self.move_down_btn)

        toolbar.addSeparator()

        # Rotation controls
        self.rotate_cw_btn = QPushButton("Rotate ↻")
        self.rotate_cw_btn.clicked.connect(self.rotate_clockwise)
        self.rotate_cw_btn.setEnabled(False)
        toolbar.addWidget(self.rotate_cw_btn)

        self.rotate_ccw_btn = QPushButton("Rotate ↺")
        self.rotate_ccw_btn.clicked.connect(self.rotate_counterclockwise)
        self.rotate_ccw_btn.setEnabled(False)
        toolbar.addWidget(self.rotate_ccw_btn)

        toolbar.addSeparator()

        # Save controls
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_file)
        self.save_btn.setEnabled(False)
        toolbar.addWidget(self.save_btn)

        self.save_as_btn = QPushButton("Save As...")
        self.save_as_btn.clicked.connect(self.save_file_as)
        self.save_as_btn.setEnabled(False)
        toolbar.addWidget(self.save_as_btn)

    def setup_status_bar(self):
        """Setup status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.page_info_label = QLabel("No document")
        self.status_bar.addWidget(self.page_info_label)

    def open_file(self):
        """Open PDF file dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            "",
            "PDF Files (*.pdf)"
        )

        if file_path:
            # Check for unsaved changes
            if self.pdf_viewer.has_unsaved_changes():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "The current document has unsaved changes. Do you want to save them?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
                )

                if reply == QMessageBox.Save:
                    if not self.pdf_viewer.save_changes():
                        return  # Save failed, don't open new file
                elif reply == QMessageBox.Cancel:
                    return  # User cancelled

            # Reset zoom slider to 100% before opening new document
            self.zoom_slider.setValue(100)
            self.zoom_label.setText("100%")

            if self.pdf_viewer.open_document(file_path):
                self.current_document_path = file_path
                filename = os.path.basename(file_path)
                self.setWindowTitle(f"PDF Editor - {filename}")
                self.update_status_bar()

                # Update thumbnail panel
                self.thumbnail_panel.set_document(self.pdf_viewer.document, file_path)

                # Enable page manipulation actions
                self.update_toolbar_state()

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

    def close_file(self):
        """Close current document"""
        # Check for unsaved changes
        if self.pdf_viewer.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "The current document has unsaved changes. Do you want to save them?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )

            if reply == QMessageBox.Save:
                if not self.pdf_viewer.save_changes():
                    return  # Save failed, don't close
            elif reply == QMessageBox.Cancel:
                return  # User cancelled

        # Reset zoom slider to 100%
        self.zoom_slider.setValue(100)
        self.zoom_label.setText("100%")

        self.pdf_viewer.close_document()
        self.thumbnail_panel.clear_thumbnails()
        self.current_document_path = ""
        self.setWindowTitle("PDF Editor")
        self.page_info_label.setText("No document")

        # Disable page manipulation actions
        self.update_toolbar_state()

    def zoom_in(self):
        """Zoom in"""
        current_value = self.zoom_slider.value()
        self.zoom_slider.setValue(min(500, current_value + 25))

    def zoom_out(self):
        """Zoom out"""
        current_value = self.zoom_slider.value()
        self.zoom_slider.setValue(max(10, current_value - 25))

    def on_zoom_changed(self, value):
        """Handle zoom slider change"""
        zoom_percent = value
        zoom_factor = zoom_percent / 100.0

        self.zoom_label.setText(f"{zoom_percent}%")
        self.pdf_viewer.set_zoom(zoom_factor)

    def on_page_changed(self, page_num):
        """Handle page change in viewer"""
        self.update_status_bar(page_num)
        # Update thumbnail panel current page highlight
        self.thumbnail_panel.set_current_page(page_num)

    def delete_current_page(self):
        """Delete the current page"""
        if self.pdf_viewer.delete_current_page():
            current_page = self.pdf_viewer.get_current_page()
            self.thumbnail_panel.hide_page_thumbnail(current_page)
            self.update_status_bar()
            # Update window title to show unsaved changes
            if self.current_document_path and "*" not in self.windowTitle():
                filename = os.path.basename(self.current_document_path)
                self.setWindowTitle(f"PDF Editor - {filename}*")

    def move_page_up(self):
        """Move current page up"""
        if self.pdf_viewer.move_page_up():
            self.update_status_bar()
            # Update window title to show unsaved changes
            if self.current_document_path and "*" not in self.windowTitle():
                filename = os.path.basename(self.current_document_path)
                self.setWindowTitle(f"PDF Editor - {filename}*")

    def move_page_down(self):
        """Move current page down"""
        if self.pdf_viewer.move_page_down():
            self.update_status_bar()
            # Update window title to show unsaved changes
            if self.current_document_path and "*" not in self.windowTitle():
                filename = os.path.basename(self.current_document_path)
                self.setWindowTitle(f"PDF Editor - {filename}*")

    def rotate_clockwise(self):
        """Rotate current page clockwise"""
        if self.pdf_viewer.rotate_page_clockwise():
            current_page = self.pdf_viewer.get_current_page()
            self.thumbnail_panel.rotate_page_thumbnail(current_page, 90)
            self.update_status_bar()
            # Update window title to show unsaved changes
            if self.current_document_path and "*" not in self.windowTitle():
                filename = os.path.basename(self.current_document_path)
                self.setWindowTitle(f"PDF Editor - {filename}*")

    def rotate_counterclockwise(self):
        """Rotate current page counterclockwise"""
        if self.pdf_viewer.rotate_page_counterclockwise():
            current_page = self.pdf_viewer.get_current_page()
            self.thumbnail_panel.rotate_page_thumbnail(current_page, -90)
            self.update_status_bar()
            # Update window title to show unsaved changes
            if self.current_document_path and "*" not in self.windowTitle():
                filename = os.path.basename(self.current_document_path)
                self.setWindowTitle(f"PDF Editor - {filename}*")

    def save_file(self):
        """Save changes to current file"""
        if not self.current_document_path:
            self.save_file_as()
            return

        if self.pdf_viewer.save_changes():
            # Remove asterisk from title
            if "*" in self.windowTitle():
                filename = os.path.basename(self.current_document_path)
                self.setWindowTitle(f"PDF Editor - {filename}")

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
                self.setWindowTitle(f"PDF Editor - {filename}")

    def update_status_bar(self, current_page=0):
        """Update status bar with current visual page order"""
        if self.pdf_viewer.document:
            # Get visible pages in current order
            visible_pages = []
            for i in range(self.pdf_viewer.pages_layout.count()):
                item = self.pdf_viewer.pages_layout.itemAt(i)
                if item and item.widget() and not item.widget().isHidden():
                    visible_pages.append(item.widget())

            # Find which visible page is currently centered
            current_visible_index = 0
            if visible_pages:
                viewport_rect = self.pdf_viewer.viewport().rect()
                scroll_y = self.pdf_viewer.verticalScrollBar().value()
                viewport_center_y = scroll_y + viewport_rect.height() // 2

                min_distance = float('inf')
                for i, widget in enumerate(visible_pages):
                    widget_center_y = widget.y() + widget.height() // 2
                    distance = abs(widget_center_y - viewport_center_y)
                    if distance < min_distance:
                        min_distance = distance
                        current_visible_index = i

            self.page_info_label.setText(
                f"Page {current_visible_index + 1} of {len(visible_pages)}"
            )
        else:
            self.page_info_label.setText("No document")

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
                    self.setWindowTitle(f"PDF Editor - {filename}")
                    self.update_status_bar()
                    # Update thumbnail panel
                    self.thumbnail_panel.set_document(self.pdf_viewer.document, file_path)


def main():
    app = QApplication(sys.argv)

    # Set application properties
    app.setApplicationName("PDF Editor")
    app.setApplicationVersion("1.0")

    # Create and show main window
    editor = PDFEditor()
    editor.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
