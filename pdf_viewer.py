import os
import gc
import threading
from typing import Optional, Dict, Set
from dataclasses import dataclass
from collections import OrderedDict

from PySide6.QtWidgets import (
    QScrollArea, QVBoxLayout, QWidget, QLabel, QMessageBox, QInputDialog
)
from PySide6.QtCore import (
    Qt, QThread, QObject, Signal, QTimer, QSize, QRect,
    QRunnable, QThreadPool
)
from PySide6.QtGui import QPixmap

import fitz  # PyMuPDF


@dataclass
class PageInfo:
    """Information about a PDF page"""
    page_num: int
    width: int
    height: int
    rotation: int = 0


class PageCache:
    """Ultra-aggressive LRU Cache - keeps only 3-4 pages maximum"""

    def __init__(self, max_size: int = 3):
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
            # Aggressively remove old pages
            while len(self.cache) > self.max_size:
                oldest = next(iter(self.cache))
                del self.cache[oldest]
                gc.collect()

    def clear(self):
        self.cache.clear()
        gc.collect()


class PageRenderWorker(QRunnable):
    """Lightweight worker for rendering pages"""

    def __init__(self, doc_path: str, page_num: int, zoom: float, callback, render_id: str, rotation: int = 0,
                 password: str = ""):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num
        self.zoom = zoom
        self.callback = callback
        self.render_id = render_id
        self.rotation = rotation
        self.cancelled = False
        self.password = password

    def cancel(self):
        self.cancelled = True

    def run(self):
        if self.cancelled:
            return

        try:
            print(f"Rendering page {self.page_num} with zoom {self.zoom}")

            # Open document briefly
            doc = fitz.open(self.doc_path)

            # Handle password protection
            if doc.needs_pass and self.password:
                if not doc.authenticate(self.password):
                    doc.close()
                    return

            if self.cancelled:
                doc.close()
                return

            if self.page_num >= len(doc):
                print(f"Page {self.page_num} out of range (doc has {len(doc)} pages)")
                doc.close()
                return

            page = doc[self.page_num]
            if self.cancelled:
                doc.close()
                return

            # Apply rotation
            if self.rotation != 0:
                page.set_rotation(self.rotation)

            # Use moderate quality to balance memory and appearance
            matrix = fitz.Matrix(self.zoom, self.zoom)

            # Render with memory-conscious settings
            pix = page.get_pixmap(
                matrix=matrix,
                alpha=False,
                colorspace=fitz.csRGB,
                clip=None
            )

            if self.cancelled:
                doc.close()
                return

            # Convert to QPixmap
            img_data = pix.tobytes("ppm")
            pixmap = QPixmap()
            success = pixmap.loadFromData(img_data)

            # Close immediately to free memory
            doc.close()

            if not self.cancelled and success:
                print(f"Successfully rendered page {self.page_num} ({pixmap.width()}x{pixmap.height()})")
                self.callback(self.page_num, pixmap, self.render_id)
            else:
                print(f"Failed to render page {self.page_num} or was cancelled")

        except Exception as e:
            if not self.cancelled:
                print(f"Error rendering page {self.page_num}: {e}")


class PDFViewer(QScrollArea):
    """Memory-optimized PDF viewer that only loads visible pages"""

    page_changed = Signal(int)
    document_modified = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        print("Initializing PDFViewer")

        # Core properties
        self.document = None
        self.doc_path = ""
        self.document_password = ""
        self.pages_info = []
        self.page_widgets = []
        self.zoom_level = 1.0

        # Document modification tracking
        self.is_modified = False
        self.deleted_pages = set()
        self.page_order = []
        self.page_rotations = {}

        # Ultra-conservative caching
        self.page_cache = PageCache(max_size=3)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)  # Single thread to prevent memory spikes

        # Track active render tasks
        self.active_workers: Dict[str, PageRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # UI setup
        self.setup_ui()

        # Conservative scroll handling
        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.update_visible_pages)

        self.verticalScrollBar().valueChanged.connect(self.on_scroll)
        self.last_visible_pages = set()

        print("PDFViewer initialization complete")

    def setup_ui(self):
        """Setup the scrollable area"""
        print("Setting up PDFViewer UI")

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QScrollArea {
                background-color: #f0f0f0;
                border: none;
            }
        """)

        # Container widget for pages
        self.pages_container = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setSpacing(10)
        self.pages_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.setWidget(self.pages_container)
        print("PDFViewer UI setup complete")

    def authenticate_document(self, file_path: str) -> Optional[str]:
        """Handle password authentication for encrypted PDFs"""
        try:
            temp_doc = fitz.open(file_path)

            if temp_doc.needs_pass:
                password, ok = QInputDialog.getText(
                    self,
                    "Password Required",
                    f"File {os.path.basename(file_path)} is password protected.\nEnter password:",
                    QInputDialog.Password
                )

                if ok and password:
                    if temp_doc.authenticate(password):
                        temp_doc.close()
                        return password
                    else:
                        QMessageBox.warning(self, "Authentication Failed", "Invalid password!")
                        temp_doc.close()
                        return None
                else:
                    temp_doc.close()
                    return None
            else:
                temp_doc.close()
                return ""
        except Exception as e:
            print(f"Error during authentication: {e}")
            return None

    def open_document(self, file_path: str) -> bool:
        """Open PDF document with immediate optimization"""
        try:
            print(f"PDFViewer: Opening document: {file_path}")
            self.close_document()
            self.zoom_level = 1.0

            # Handle password authentication
            password = self.authenticate_document(file_path)
            if password is None:
                temp_doc = fitz.open(file_path)
                if temp_doc.needs_pass:
                    temp_doc.close()
                    print("Password required but not provided")
                    return False
                temp_doc.close()

            self.document_password = password or ""

            # Quick document info extraction WITHOUT loading pages
            temp_doc = fitz.open(file_path)
            if temp_doc.needs_pass:
                temp_doc.authenticate(self.document_password)

            page_count = len(temp_doc)
            print(f"Document has {page_count} pages")

            self.doc_path = file_path
            self.pages_info = []

            # Extract page info quickly without rendering
            for page_num in range(page_count):
                page = temp_doc[page_num]
                rect = page.rect
                page_info = PageInfo(
                    page_num=page_num,
                    width=int(rect.width),
                    height=int(rect.height)
                )
                self.pages_info.append(page_info)

            # Close immediately after info extraction
            temp_doc.close()

            # Re-open for actual use (PyMuPDF requirement)
            self.document = fitz.open(file_path)
            if self.document.needs_pass:
                self.document.authenticate(self.document_password)

            # Reset modification tracking
            self.is_modified = False
            self.deleted_pages = set()
            self.page_order = list(range(len(self.document)))
            self.page_rotations = {}

            # Create lightweight placeholder widgets
            self.create_placeholder_widgets()

            # Scroll to top
            self.verticalScrollBar().setValue(0)

            # Force an immediate update to show the document
            self.update()
            self.repaint()

            # Delay initial page loading to prevent freeze
            QTimer.singleShot(100, self.update_visible_pages)

            print(f"Document opened successfully: {page_count} pages")
            return True

        except Exception as e:
            print(f"Error opening document: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open PDF: {e}")
            return False

    def close_document(self):
        """Close document and aggressively free resources"""
        print("Closing document")

        self.cancel_all_renders()

        if self.document:
            self.document.close()
            self.document = None

        self.doc_path = ""
        self.document_password = ""
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

        # Force garbage collection
        gc.collect()
        print("Document closed")

    def create_placeholder_widgets(self):
        """Create lightweight placeholder widgets - NO RENDERING"""
        print(f"Creating {len(self.pages_info)} placeholder widgets")
        self.page_widgets = []

        for page_info in self.pages_info:
            display_width = int(page_info.width * self.zoom_level)
            display_height = int(page_info.height * self.zoom_level)

            # Ensure minimum readable size
            display_width = max(display_width, 200)
            display_height = max(display_height, 200)

            # Simple placeholder label
            page_widget = QLabel(f"Page {page_info.page_num + 1}\nLoading...")
            page_widget.setMinimumSize(display_width, display_height)
            page_widget.setFixedSize(display_width, display_height)
            page_widget.setAlignment(Qt.AlignCenter)
            page_widget.setStyleSheet("""
                QLabel {
                    border: 2px solid #ddd;
                    background-color: white;
                    color: #666;
                    font-size: 14px;
                    margin: 5px;
                }
            """)

            self.page_widgets.append(page_widget)
            self.pages_layout.addWidget(page_widget)

        print(f"Created {len(self.page_widgets)} placeholder widgets")

        # Force layout update
        self.pages_container.updateGeometry()
        self.update()

    def cancel_all_renders(self):
        """Cancel all active rendering tasks"""
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

    def on_scroll(self):
        """Handle scroll events with delay"""
        self.cancel_all_renders()
        # Longer delay to prevent excessive rendering during scrolling
        self.scroll_timer.start(200)

    def update_visible_pages(self):
        """Ultra-conservative visible page management"""
        if not self.document:
            print("No document loaded, skipping visible page update")
            return

        print("Updating visible pages")

        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()

        # Find currently visible pages with minimal buffer
        visible_pages = set()
        current_center_page = None
        viewport_center_y = scroll_y + viewport_rect.height() // 2

        for i, widget in enumerate(self.page_widgets):
            if widget.isHidden():
                continue

            widget_y = widget.y() - scroll_y
            widget_bottom = widget_y + widget.height()

            # Only consider truly visible pages with small buffer
            if widget_bottom >= -100 and widget_y <= viewport_rect.height() + 100:
                visible_pages.add(i)

                # Find center page
                widget_center_y = widget.y() + widget.height() // 2
                if current_center_page is None or abs(widget_center_y - viewport_center_y) < abs(
                        self.page_widgets[current_center_page].y() +
                        self.page_widgets[current_center_page].height() // 2 - viewport_center_y):
                    current_center_page = i

        print(f"Visible pages: {visible_pages}, center page: {current_center_page}")

        # Only load 1-2 pages at most
        if len(visible_pages) > 2:
            # Keep only center page and one adjacent
            if current_center_page is not None:
                visible_pages = {current_center_page}
                # Add one adjacent page
                if current_center_page > 0 and current_center_page - 1 not in self.deleted_pages:
                    visible_pages.add(current_center_page - 1)
                elif current_center_page < len(
                        self.page_widgets) - 1 and current_center_page + 1 not in self.deleted_pages:
                    visible_pages.add(current_center_page + 1)

        # Clear non-visible pages immediately
        for page_num in self.last_visible_pages - visible_pages:
            if 0 <= page_num < len(self.page_widgets):
                self.clear_page_widget(page_num)

        # Load only visible pages
        for page_num in visible_pages:
            if 0 <= page_num < len(self.page_widgets):
                self.load_page_if_needed(page_num)

        self.last_visible_pages = visible_pages.copy()

        if current_center_page is not None:
            self.page_changed.emit(current_center_page)

        # Force garbage collection after page updates
        gc.collect()

    def clear_page_widget(self, page_num: int):
        """Clear a page widget and reset to placeholder"""
        if page_num >= len(self.page_widgets) or page_num >= len(self.pages_info):
            return

        widget = self.page_widgets[page_num]
        page_info = self.pages_info[page_num]

        display_width = int(page_info.width * self.zoom_level)
        display_height = int(page_info.height * self.zoom_level)

        # Ensure minimum readable size
        display_width = max(display_width, 200)
        display_height = max(display_height, 200)

        widget.setFixedSize(display_width, display_height)
        widget.clear()
        widget.setText(f"Page {page_num + 1}\nLoading...")
        widget.setStyleSheet("""
            QLabel {
                border: 2px solid #ddd;
                background-color: white;
                color: #666;
                font-size: 14px;
                margin: 5px;
            }
        """)

    def load_page_if_needed(self, page_num: int):
        """Load page only if not already loaded"""
        if page_num >= len(self.page_widgets):
            return

        widget = self.page_widgets[page_num]

        # Check if already loaded (has pixmap)
        if hasattr(widget, 'pixmap') and widget.pixmap() and not widget.pixmap().isNull():
            print(f"Page {page_num} already loaded")
            return

        # Check cache
        cached_pixmap = self.page_cache.get(page_num)
        if cached_pixmap:
            print(f"Using cached pixmap for page {page_num}")
            widget.setPixmap(cached_pixmap)
            widget.setFixedSize(cached_pixmap.size())
            widget.setStyleSheet("border: 2px solid #ccc; margin: 5px;")
            return

        # Start rendering
        print(f"Starting render for page {page_num}")
        self.start_page_render(page_num)

    def start_page_render(self, page_num: int):
        """Start rendering a page"""
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"render_{self.current_render_id}_{page_num}"

        rotation = self.page_rotations.get(page_num, 0)

        worker = PageRenderWorker(
            self.doc_path,
            page_num,
            self.zoom_level,
            self.on_page_rendered,
            render_id,
            rotation,
            self.document_password
        )

        with self.render_lock:
            self.active_workers[render_id] = worker

        self.thread_pool.start(worker)

    def on_page_rendered(self, page_num: int, pixmap: QPixmap, render_id: str):
        """Handle rendered page result"""
        with self.render_lock:
            if render_id in self.active_workers:
                del self.active_workers[render_id]

        print(f"Page {page_num} rendered successfully")

        # Only update if page is still visible
        if page_num in self.last_visible_pages and page_num < len(self.page_widgets):
            self.page_cache.put(page_num, pixmap)
            widget = self.page_widgets[page_num]

            widget.setPixmap(pixmap)
            widget.setFixedSize(pixmap.size())
            widget.setStyleSheet("border: 2px solid #ccc; margin: 5px;")
            widget.update()

    def set_zoom(self, zoom: float):
        """Set zoom level and refresh"""
        if not self.document or zoom == self.zoom_level:
            return

        print(f"Setting zoom to {zoom}")
        self.cancel_all_renders()
        self.zoom_level = zoom
        self.page_cache.clear()

        # Update all widget sizes without rendering
        for i, widget in enumerate(self.page_widgets):
            if i >= len(self.pages_info):
                continue

            page_info = self.pages_info[i]
            display_width = int(page_info.width * self.zoom_level)
            display_height = int(page_info.height * self.zoom_level)

            # Ensure minimum readable size
            display_width = max(display_width, 200)
            display_height = max(display_height, 200)

            widget.setFixedSize(display_width, display_height)
            widget.clear()
            widget.setText(f"Page {i + 1}\nLoading...")
            widget.setStyleSheet("""
                QLabel {
                    border: 2px solid #ddd;
                    background-color: white;
                    color: #666;
                    font-size: 14px;
                    margin: 5px;
                }
            """)

        gc.collect()
        QTimer.singleShot(150, self.update_visible_pages)

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

    def get_visible_page_count(self) -> int:
        """Get count of visible (non-deleted) pages"""
        if not self.page_widgets:
            return 0

        count = 0
        for widget in self.page_widgets:
            if not widget.isHidden():
                count += 1
        return count

    def go_to_page(self, page_num: int):
        """Navigate to specific page"""
        if 0 <= page_num < len(self.page_widgets):
            self.cancel_all_renders()
            widget = self.page_widgets[page_num]
            if not widget.isHidden():
                self.ensureWidgetVisible(widget, 50, 50)
                QTimer.singleShot(100, self.update_visible_pages)

    # Page manipulation methods
    def rotate_page_clockwise(self):
        """Rotate current page clockwise"""
        return self._rotate_page(90)

    def rotate_page_counterclockwise(self):
        """Rotate current page counterclockwise"""
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

        # Force re-render
        if current_page in self.page_cache.cache:
            del self.page_cache.cache[current_page]

        self.clear_page_widget(current_page)
        QTimer.singleShot(50, self.update_visible_pages)
        return True

    def delete_current_page(self):
        """Delete the current page"""
        if not self.document:
            return False

        current_page = self.get_current_page()
        remaining_pages = self.get_visible_page_count()

        if remaining_pages <= 1:
            QMessageBox.warning(None, "Cannot Delete", "Cannot delete the last remaining page.")
            return False

        self.deleted_pages.add(current_page)
        self.is_modified = True
        self.document_modified.emit(True)

        # Hide the widget
        widget = self.page_widgets[current_page]
        widget.hide()

        self.page_changed.emit(self.get_current_page())
        return True

    def move_page_up(self):
        """Move current page up"""
        return self._move_page(-1)

    def move_page_down(self):
        """Move current page down"""
        return self._move_page(1)

    def _move_page(self, direction: int):
        """Internal method to move pages"""
        if not self.document:
            return False

        current_page = self.get_current_page()

        # Find current position in layout
        current_widget = self.page_widgets[current_page]
        current_layout_pos = -1

        for i in range(self.pages_layout.count()):
            item = self.pages_layout.itemAt(i)
            if item and item.widget() == current_widget:
                current_layout_pos = i
                break

        if current_layout_pos == -1:
            return False

        # Find target position (skip hidden widgets)
        target_pos = current_layout_pos
        step = 1 if direction > 0 else -1

        while True:
            target_pos += step
            if target_pos < 0 or target_pos >= self.pages_layout.count():
                return False

            target_item = self.pages_layout.itemAt(target_pos)
            if target_item and target_item.widget() and not target_item.widget().isHidden():
                break

        target_widget = target_item.widget()

        # Swap widgets
        self.pages_layout.removeWidget(current_widget)
        self.pages_layout.removeWidget(target_widget)

        if direction > 0:  # Moving down
            self.pages_layout.insertWidget(current_layout_pos, target_widget)
            self.pages_layout.insertWidget(target_pos, current_widget)
        else:  # Moving up
            self.pages_layout.insertWidget(target_pos, current_widget)
            self.pages_layout.insertWidget(current_layout_pos, target_widget)

        self.is_modified = True
        self.document_modified.emit(True)
        return True

    def save_changes(self, file_path: str = None) -> bool:
        """Save changes to file"""
        if not self.document or not self.is_modified:
            return True

        try:
            save_path = file_path if file_path else self.doc_path
            new_doc = fitz.open()

            # Get page order from layout (only visible pages)
            page_order = []
            for i in range(self.pages_layout.count()):
                item = self.pages_layout.itemAt(i)
                if item and item.widget() and not item.widget().isHidden():
                    widget = item.widget()
                    # Find original page number
                    for j, page_widget in enumerate(self.page_widgets):
                        if page_widget == widget:
                            page_order.append(j)
                            break

            # Copy pages in new order with rotations
            for page_num in page_order:
                if 0 <= page_num < len(self.document):
                    temp_doc = fitz.open()
                    temp_doc.insert_pdf(self.document, from_page=page_num, to_page=page_num)

                    rotation = self.page_rotations.get(page_num, 0)
                    if rotation != 0:
                        temp_page = temp_doc[0]
                        temp_page.set_rotation(rotation)

                    new_doc.insert_pdf(temp_doc)
                    temp_doc.close()

            # Save
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
                if self.document.needs_pass:
                    self.document.authenticate(self.document_password)
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

    def fit_to_width(self):
        """Fit document to width"""
        if not self.document or not self.page_widgets:
            return

        # Calculate zoom to fit page width to viewport width
        viewport_width = self.viewport().width() - 50  # Some margin
        if self.pages_info:
            page_width = self.pages_info[0].width
            new_zoom = viewport_width / page_width
            self.set_zoom(new_zoom)

    def fit_to_height(self):
        """Fit document to height"""
        if not self.document or not self.page_widgets:
            return

        # Calculate zoom to fit page height to viewport height
        viewport_height = self.viewport().height() - 50  # Some margin
        if self.pages_info:
            page_height = self.pages_info[0].height
            new_zoom = viewport_height / page_height
            self.set_zoom(new_zoom)
