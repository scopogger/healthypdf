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


class PageRenderWorker(QRunnable):
    """Worker for rendering pages in background with cancellation support"""

    def __init__(self, doc_path: str, page_num: int, zoom: float, callback, render_id: str):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num
        self.zoom = zoom
        self.callback = callback
        self.render_id = render_id
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
            # Clear existing document
            self.close_document()

            # Open new document
            self.document = fitz.open(file_path)
            self.doc_path = file_path

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

            # Start loading visible pages
            QTimer.singleShot(50, self.update_visible_pages)  # Faster initial load

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

        # Create and start worker
        worker = PageRenderWorker(
            self.doc_path,
            page_num,
            self.zoom_level,
            self.on_page_rendered,
            render_id
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
        self.current_document_path = ""

        self.setup_ui()
        self.setup_menus()
        self.setup_toolbar()
        self.setup_status_bar()

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Window settings
        self.setWindowTitle("PDF Editor")
        self.resize(1200, 800)

    def setup_ui(self):
        """Setup main UI layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # PDF Viewer
        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.page_changed.connect(self.on_page_changed)
        layout.addWidget(self.pdf_viewer)

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

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def setup_toolbar(self):
        """Setup toolbar with zoom controls"""
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
            if self.pdf_viewer.open_document(file_path):
                self.current_document_path = file_path
                filename = os.path.basename(file_path)
                self.setWindowTitle(f"PDF Editor - {filename}")
                self.update_status_bar()

    def close_file(self):
        """Close current document"""
        self.pdf_viewer.close_document()
        self.current_document_path = ""
        self.setWindowTitle("PDF Editor")
        self.page_info_label.setText("No document")

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

    def update_status_bar(self, current_page=0):
        """Update status bar information"""
        if self.pdf_viewer.document:
            total_pages = len(self.pdf_viewer.document)
            self.page_info_label.setText(
                f"Page {current_page + 1} of {total_pages}"
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
