import os
import gc
import threading
from typing import Optional, Dict, Set
from dataclasses import dataclass
from collections import OrderedDict

from drawing_overlay import PageWidget

from PySide6.QtWidgets import (
    QScrollArea, QVBoxLayout, QWidget, QLabel, QMessageBox, QInputDialog, QFrame, QPushButton
)
from PySide6.QtCore import (
    Qt, QRunnable, QThreadPool, QTimer, Signal
)
from PySide6.QtGui import QPixmap, QColor

import fitz  # PyMuPDF


@dataclass
class PageInfo:
    """Information about a PDF page"""
    page_num: int         # original document page index
    width: int
    height: int
    rotation: int = 0


class PageCache:
    """Ultra-aggressive LRU Cache - keys are original page numbers"""
    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self.cache: OrderedDict[int, QPixmap] = OrderedDict()

    def get(self, orig_page_num: int) -> Optional[QPixmap]:
        if orig_page_num in self.cache:
            self.cache.move_to_end(orig_page_num)
            return self.cache[orig_page_num]
        return None

    def put(self, orig_page_num: int, pixmap: QPixmap):
        if orig_page_num in self.cache:
            self.cache.move_to_end(orig_page_num)
        else:
            self.cache[orig_page_num] = pixmap
            while len(self.cache) > self.max_size:
                oldest = next(iter(self.cache))
                del self.cache[oldest]
                gc.collect()

    def clear(self):
        self.cache.clear()
        gc.collect()


class PageRenderWorker(QRunnable):
    """Lightweight worker for rendering pages (page_num here is ORIGINAL page number)"""
    def __init__(self, doc_path: str, page_num: int, zoom: float, callback, render_id: str, rotation: int = 0,
                 password: str = ""):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num  # ORIGINAL document page index
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
            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB, clip=None)

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
                # callback receives original page number, pixmap and render_id
                self.callback(self.page_num, pixmap, self.render_id)
            else:
                print(f"Failed to render page {self.page_num} or was cancelled")

        except Exception as e:
            if not self.cancelled:
                print(f"Error rendering page {self.page_num}: {e}")


class PDFViewer(QScrollArea):
    """Memory-optimized PDF viewer that keeps layout order in pages_info list,
       but uses PageInfo.page_num as the stable original page identifier.
    """

    page_changed = Signal(int)         # emits ORIGINAL page number
    document_modified = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QTimer

        self._center_timer = QTimer(self)
        self._center_timer.setSingleShot(True)
        self._center_timer.timeout.connect(lambda: self._do_pending_center())

        self._pending_center_index = None
        self._last_center_time = 0

        print("Initializing PDFViewer")

        # Core properties
        self.document = None
        self.doc_path = ""
        self.document_password = ""
        self.pages_info: list[PageInfo] = []   # layout order list; each entry has .page_num (original)
        self.page_widgets: list[QLabel] = []   # same order as pages_info
        self.zoom_level = 1.0

        # Document modification tracking
        self.is_modified = False
        self.deleted_pages: Set[int] = set()  # set of ORIGINAL page numbers
        self.page_rotations: Dict[int, int] = {}  # keyed by ORIGINAL page numbers

        # Caching/rendering
        self.page_cache = PageCache(max_size=3)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)  # Single thread to prevent memory spikes

        # Track active render tasks
        self.active_workers: Dict[str, PageRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # UI
        self.setup_ui()

        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.update_visible_pages)

        self.verticalScrollBar().valueChanged.connect(self.on_scroll)
        self.last_visible_layout_indices: Set[int] = set()

    def setup_ui(self):
        """Setup the scrollable area"""
        print("Setting up PDFViewer UI")

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("QScrollArea { background-color: #f0f0f0; border: none; }")
        self.pages_container = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setSpacing(10)
        self.pages_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.setWidget(self.pages_container)
        print("PDFViewer UI setup complete")

    # ---------------- Document open/close ----------------
    def authenticate_document(self, file_path: str) -> Optional[str]:
        """Handle password authentication for encrypted PDFs"""
        try:
            temp_doc = fitz.open(file_path)

            if temp_doc.needs_pass:
                password, ok = QInputDialog.getText(self, "Password Required", f"File {os.path.basename(file_path)} is password protected.\nEnter password:", QInputDialog.Password)
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
                rect = temp_doc[page_num].rect
                self.pages_info.append(PageInfo(page_num=page_num, width=int(rect.width), height=int(rect.height)))
            temp_doc.close()

            # keep a persistent document handle for operations
            self.document = fitz.open(file_path)
            if self.document.needs_pass:
                self.document.authenticate(self.document_password)

            # Reset state and build placeholders
            self.is_modified = False
            self.deleted_pages = set()
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
        self.last_visible_layout_indices.clear()
        self.is_modified = False
        self.deleted_pages = set()
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

    # ---------------- Helpers ----------------
    def layout_index_for_original(self, orig_page_num: int) -> Optional[int]:
        for idx, info in enumerate(self.pages_info):
            if info.page_num == orig_page_num:
                return idx
        return None

    def get_display_page_number(self, layout_index: int) -> int:
        """1-based display number for a layout index (skips deleted original page ids)"""
        if layout_index >= len(self.pages_info):
            return 1
        display = 1
        for i, info in enumerate(self.pages_info):
            if info.page_num in self.deleted_pages:
                continue
            if i == layout_index:
                return display
            display += 1
        return display

    def create_placeholder_widgets(self):
        """Create lightweight placeholder PageWidget instances (no rendering yet)."""
        print(f"Creating {len(self.pages_info)} placeholder widgets")
        self.page_widgets = []
        # clear existing layout
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, page_info in enumerate(self.pages_info):
            display_w = int(page_info.width * self.zoom_level)
            display_h = int(page_info.height * self.zoom_level)
            display_w = max(display_w, 200)
            display_h = max(display_h, 200)

            display_num = self.get_display_page_number(i)
            page_widget = PageWidget(display_w, display_h)
            page_widget.setMinimumSize(display_w, display_h)
            page_widget.setFixedSize(display_w, display_h)
            page_widget.base_label.setText(f"Page {display_num}\nLoading...")
            page_widget.base_label.setAlignment(Qt.AlignCenter)
            page_widget.base_label.setStyleSheet("""
                QLabel { border: 2px solid #ddd; background-color: white; color: #666; font-size: 14px; margin: 5px; }
            """)

            # store original id as property for easier debugging if needed
            page_widget.setProperty("orig_page_num", page_info.page_num)

            # connect overlay change signal so viewer knows document is modified
            try:
                page_widget.overlay.annotation_changed.connect(self.on_annotation_changed)
            except Exception:
                pass

            self.page_widgets.append(page_widget)
            self.pages_layout.addWidget(page_widget)

        print(f"Created {len(self.page_widgets)} placeholder widgets")

        # Force layout update
        self.pages_container.updateGeometry()
        self.update()

    def update_all_page_labels(self):
        """Update all page labels to reflect current order and visibility"""
        if not self.page_widgets:
            return
        display = 1
        for i, widget in enumerate(self.page_widgets):
            orig = self.pages_info[i].page_num
            if orig in self.deleted_pages:
                continue

            # Update the widget's display text if it's showing placeholder text
            current_text = widget.text()
            if "Page " in current_text and "Loading" in current_text:
                widget.setText(f"Page {display}\nLoading...")
            display += 1

    def cancel_all_renders(self):
        """Cancel all active rendering tasks"""
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

    # ---------------- Scrolling & visible pages ----------------
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
        visible_layout_indices: Set[int] = set()
        current_center_layout_index = None
        viewport_center_y = scroll_y + viewport_rect.height() // 2

        for i, widget in enumerate(self.page_widgets):
            orig = self.pages_info[i].page_num
            if orig in self.deleted_pages:
                continue

            widget_y = widget.y() - scroll_y
            widget_bottom = widget_y + widget.height()

            # Only consider truly visible pages with small buffer
            if widget_bottom >= -100 and widget_y <= viewport_rect.height() + 100:
                visible_layout_indices.add(i)
                widget_center_y = widget.y() + widget.height() // 2
                if current_center_layout_index is None or abs(widget_center_y - viewport_center_y) < abs(
                        self.page_widgets[current_center_layout_index].y() + self.page_widgets[current_center_layout_index].height() // 2 - viewport_center_y):
                    current_center_layout_index = i

        # limit to centre + one neighbor
        if len(visible_layout_indices) > 2 and current_center_layout_index is not None:
            visible_layout_indices = {current_center_layout_index}
            if current_center_layout_index > 0:
                left = current_center_layout_index - 1
                if self.pages_info[left].page_num not in self.deleted_pages:
                    visible_layout_indices.add(left)
            if current_center_layout_index < len(self.page_widgets) - 1:
                right = current_center_layout_index + 1
                if self.pages_info[right].page_num not in self.deleted_pages:
                    visible_layout_indices.add(right)

        # clear those that are no longer visible
        for layout_idx in self.last_visible_layout_indices - visible_layout_indices:
            if 0 <= layout_idx < len(self.page_widgets):
                self.clear_page_widget(layout_idx)

        # load visible
        for layout_idx in visible_layout_indices:
            if 0 <= layout_idx < len(self.page_widgets):
                self.load_page_if_needed(layout_idx)

        self.last_visible_layout_indices = visible_layout_indices.copy()

        if current_center_layout_index is not None:
            orig_center = self.pages_info[current_center_layout_index].page_num
            self.page_changed.emit(orig_center)

        gc.collect()

    def clear_page_widget(self, layout_index: int):
        if layout_index >= len(self.page_widgets) or layout_index >= len(self.pages_info):
            return

        widget = self.page_widgets[layout_index]
        page_info = self.pages_info[layout_index]
        display_w = int(page_info.width * self.zoom_level)
        display_h = int(page_info.height * self.zoom_level)
        display_w = max(display_w, 200)
        display_h = max(display_h, 200)

        # Clear base image and annotations
        try:
            widget.clear_base()
        except Exception:
            # legacy QLabel fallback
            try:
                widget.clear()
            except Exception:
                pass

        # Reset placeholder text and size if possible
        try:
            display_page_num = self.get_display_page_number(layout_index)
            widget.setFixedSize(display_w, display_h)
            # if has base_label show placeholder text
            if hasattr(widget, 'base_label'):
                widget.base_label.setText(f"Page {display_page_num}\nLoading...")
                widget.base_label.setAlignment(Qt.AlignCenter)
                widget.base_label.setStyleSheet(
                    "\nQLabel { border: 2px solid #ddd; background-color: white; color: #666; font-size: 14px; margin: 5px; }"
                )
        except Exception:
            pass

    def load_page_if_needed(self, layout_index: int):
        if layout_index >= len(self.page_widgets):
            return

        widget = self.page_widgets[layout_index]
        # if widget already has a base_pixmap, assume loaded
        if getattr(widget, "base_pixmap", None) is not None:
            return

        orig_page = self.pages_info[layout_index].page_num
        cached = self.page_cache.get(orig_page)
        if cached:
            widget.set_base_pixmap(cached)
            widget.setFixedSize(cached.size())
            # style could be adjusted
            return

        self.start_page_render(layout_index)

    def start_page_render(self, layout_index: int):
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"render_{self.current_render_id}_{layout_index}"

        orig_page = self.pages_info[layout_index].page_num
        rotation = self.page_rotations.get(orig_page, 0)

        worker = PageRenderWorker(
            self.doc_path,
            orig_page,             # pass ORIGINAL page number to worker
            self.zoom_level,
            self.on_page_rendered,
            render_id,
            rotation,
            self.document_password
        )

        with self.render_lock:
            self.active_workers[render_id] = worker

        self.thread_pool.start(worker)

    def on_page_rendered(self, orig_page_num: int, pixmap: QPixmap, render_id: str):
        with self.render_lock:
            if render_id in self.active_workers:
                del self.active_workers[render_id]

        # put into cache keyed by original page number
        self.page_cache.put(orig_page_num, pixmap)

        # find current layout index for that original page
        layout_index = self.layout_index_for_original(orig_page_num)
        if layout_index is None:
            return

        # only set pixmap if still visible
        if layout_index in self.last_visible_layout_indices and layout_index < len(self.page_widgets):
            widget = self.page_widgets[layout_index]
            # set base pixmap on our PageWidget
            try:
                widget.set_base_pixmap(pixmap)
                widget.setFixedSize(pixmap.size())
            except Exception:
                # fallback for legacy QLabel
                try:
                    widget.setPixmap(pixmap)
                    widget.setFixedSize(pixmap.size())
                except Exception:
                    pass
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
            display_w = int(page_info.width * self.zoom_level)
            display_h = int(page_info.height * self.zoom_level)
            display_w = max(display_w, 200)
            display_h = max(display_h, 200)
            widget.setFixedSize(display_w, display_h)
            widget.clear()

            # Use correct display page number
            display_page_num = self.get_display_page_number(i)
            widget.setText(f"Page {display_page_num}\nLoading...")

            widget.setStyleSheet("""
                QLabel { border: 2px solid #ddd; background-color: white; color: #666; font-size: 14px; margin: 5px; }
            """)

        gc.collect()
        QTimer.singleShot(150, self.update_visible_pages)

    # ---------------- Navigation helpers ----------------
    def get_current_page(self) -> int:
        """Return ORIGINAL page number for the currently centered page (stable id)."""
        if not self.document or not self.page_widgets:
            return 0

        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()
        viewport_center_y = scroll_y + viewport_rect.height() // 2
        current_layout_idx = 0
        min_distance = float('inf')

        for i, widget in enumerate(self.page_widgets):
            orig = self.pages_info[i].page_num
            if orig in self.deleted_pages:
                continue

            widget_center_y = widget.y() + widget.height() // 2
            distance = abs(widget_center_y - viewport_center_y)

            if distance < min_distance:
                min_distance = distance
                current_layout_idx = i
        return self.pages_info[current_layout_idx].page_num

    def get_visible_page_count(self) -> int:
        count = 0
        for info in self.pages_info:
            if info.page_num not in self.deleted_pages:
                count += 1
        return count

    def request_center_on_layout_index(self, layout_index: int, delay_ms: int = 80):
        """
        Request centering on a layout index. Multiple requests are debounced so only the
        last request within `delay_ms` will actually perform the scroll.
        Use this from code that might call centering many times (e.g. during batch ops).
        """
        if layout_index is None:
            return
        # remember last requested (we always keep the newest)
        self._pending_center_index = int(layout_index)
        # restart timer (coalesce multiple calls)
        try:
            self._center_timer.start(delay_ms)
        except Exception:
            # fallback: call synchronously
            self._do_pending_center()

    def _do_pending_center(self):
        """Called by the single-shot timer to perform the actual centering once."""
        idx = self._pending_center_index
        self._pending_center_index = None
        if idx is None:
            return
        try:
            self.center_on_layout_index(idx)
        except Exception as e:
            # swallow errors — centering is best-effort
            print(f"[PDFViewer] center error: {e}")

    def center_on_layout_index(self, layout_index: int):
        """
        Center the viewport on the widget at layout_index deterministically by setting the scrollbar value.
        This is the actual centering operation — kept idempotent where possible.
        """
        if not self.page_widgets or layout_index is None:
            return

        # clamp index
        layout_index = max(0, min(layout_index, len(self.page_widgets) - 1))

        widget = self.page_widgets[layout_index]
        if widget is None:
            return

        try:
            # compute widget center Y in the container coordinates
            widget_y = widget.y()
            widget_center = widget_y + widget.height() // 2
            viewport_h = self.viewport().height() or 1

            desired_scroll = max(0, widget_center - viewport_h // 2)

            sb = self.verticalScrollBar()
            desired_scroll = max(0, min(desired_scroll, sb.maximum()))

            # Idempotent set: avoid setting the same value repeatedly (reduces noise and avoids side-effects)
            current = sb.value()
            if int(current) == int(desired_scroll):
                return

            # set the scrollbar synchronously
            sb.setValue(int(desired_scroll))
        except Exception:
            # fallback safe call
            try:
                self.ensureWidgetVisible(widget, 50, 50)
            except Exception:
                pass

        # schedule visible-pages update once scroll settles
        from PySide6.QtCore import QTimer
        QTimer.singleShot(80, self.update_visible_pages)

    def go_to_page(self, layout_index: int):
        """
        Public navigation entrypoint; request a centered scroll rather than doing many immediate scrolls.
        Use request_center_on_layout_index to coalesce repeated nav requests.
        """
        if not self.page_widgets:
            return
        if layout_index < 0 or layout_index >= len(self.page_widgets):
            return

        # cancel renders but DO NOT center synchronously; request debounced centering
        self.cancel_all_renders()
        self.request_center_on_layout_index(layout_index, delay_ms=60)

    # ---------------- Page manipulation ----------------
    def _rotate_page(self, rotation: int):
        """Internal method to rotate a page"""
        if not self.document:
            return False
        # get original page id for current center
        orig_current = self.get_current_page()
        # update rotation keyed by original id
        current_rotation = self.page_rotations.get(orig_current, 0)
        new_rotation = (current_rotation + rotation) % 360
        self.page_rotations[orig_current] = new_rotation
        self.is_modified = True
        self.document_modified.emit(True)

        # clear cache for that original id
        if orig_current in self.page_cache.cache:
            del self.page_cache.cache[orig_current]

        # clear placeholder and force re-render
        layout_idx = self.layout_index_for_original(orig_current)
        if layout_idx is not None:
            self.clear_page_widget(layout_idx)
        self.update_all_page_labels()

        QTimer.singleShot(50, self.update_visible_pages)
        return True

    def rotate_page_clockwise(self):
        return self._rotate_page(90)

    def rotate_page_counterclockwise(self):
        return self._rotate_page(-90)

    def delete_current_page(self):
        """Delete the current page (remove placeholder/widget and page_info entry)."""
        if not self.document:
            return False

        orig_current = self.get_current_page()
        if self.get_visible_page_count() <= 1:
            QMessageBox.warning(None, "Cannot Delete", "Cannot delete the last remaining page.")
            return False

        # Mark original page as deleted for persistence/undo tracking
        self.deleted_pages.add(orig_current)
        self.is_modified = True
        self.document_modified.emit(True)

        # Find layout index and REMOVE the widget + pages_info entry so we don't keep hidden placeholders
        layout_idx = self.layout_index_for_original(orig_current)
        if layout_idx is not None:
            # remove widget and its layout entry
            try:
                widget = self.page_widgets.pop(layout_idx)
                widget.deleteLater()
            except Exception:
                pass

            try:
                self.pages_info.pop(layout_idx)
            except Exception:
                pass

            # Remove any cached pixmap for that original page
            self.page_cache.cache.pop(orig_current, None)

        # Force labels and lazy loader to recompute
        self.update_all_page_labels()

        # clear last visible set so the lazy loader doesn't think old indices are still visible
        self.last_visible_layout_indices.clear()

        # schedule visible-pages update (debounced)
        QTimer.singleShot(50, self.update_visible_pages)

        # emit new centered page (original id)
        new_center = self.get_current_page()
        if new_center is not None:
            self.page_changed.emit(new_center)
        return True

    def _move_page(self, direction: int):
        """Move the currently centered page in layout (direction: -1 up, +1 down)"""
        if not self.document:
            return False

        orig_current = self.get_current_page()
        current_layout_idx = self.layout_index_for_original(orig_current)
        if current_layout_idx is None:
            return False

        # find target layout pos (skip hidden original pages)
        target_layout_pos = current_layout_idx
        step = 1 if direction > 0 else -1

        while True:
            target_layout_pos += step
            if target_layout_pos < 0 or target_layout_pos >= self.pages_layout.count():
                return False
            if target_layout_pos >= len(self.page_widgets):
                return False
            target_widget = self.pages_layout.itemAt(target_layout_pos).widget()
            if target_widget and not target_widget.isHidden():
                break

        # compute layout index of target_widget
        target_layout_idx = None
        for idx, w in enumerate(self.page_widgets):
            if w == target_widget:
                target_layout_idx = idx
                break
        if target_layout_idx is None:
            return False

        # swap widgets in layout (preserve visual order)
        current_widget = self.page_widgets[current_layout_idx]
        target_widget = self.page_widgets[target_layout_idx]

        # Remove and re-insert using layout positions
        self.pages_layout.removeWidget(current_widget)
        self.pages_layout.removeWidget(target_widget)

        if direction > 0:  # moving down: insert target first then current
            self.pages_layout.insertWidget(current_layout_idx, target_widget)
            self.pages_layout.insertWidget(target_layout_idx, current_widget)
        else:  # moving up
            self.pages_layout.insertWidget(target_layout_idx, current_widget)
            self.pages_layout.insertWidget(current_layout_idx, target_widget)

        # swap entries in page_widgets and pages_info to keep lists reflect layout order
        self.page_widgets[current_layout_idx], self.page_widgets[target_layout_idx] = (
            self.page_widgets[target_layout_idx],
            self.page_widgets[current_layout_idx],
        )
        self.pages_info[current_layout_idx], self.pages_info[target_layout_idx] = (
            self.pages_info[target_layout_idx],
            self.pages_info[current_layout_idx],
        )

        self.is_modified = True
        self.document_modified.emit(True)

        # Update labels to match new order
        self.update_all_page_labels()

        # Clear cached visible indices so update_visible_pages will reload appropriate pages
        self.last_visible_layout_indices.clear()

        # Coalesce and trigger a visible-pages update
        QTimer.singleShot(50, self.update_visible_pages)

        # Emit the currently-centered page (original id) so UI syncs
        try:
            self.page_changed.emit(self.get_current_page())
        except Exception:
            pass

        return True

    def move_page_up(self):
        return self._move_page(-1)

    def move_page_down(self):
        return self._move_page(1)

    def save_changes(self, file_path: str = None) -> bool:
        """Save changes to file: build page_order by iterating layout and using ORIGINAL page numbers.
        This version inserts the original page content and then overlays annotation PNG (if present) on top.
        """
        if not self.document or not self.is_modified:
            return True
        try:
            save_path = file_path if file_path else self.doc_path
            new_doc = fitz.open()
            # page_order: list of original page numbers in current layout (skip deleted originals)
            page_order = []
            for i in range(self.pages_layout.count()):
                item = self.pages_layout.itemAt(i)
                if item and item.widget() and not item.widget().isHidden():
                    widget = item.widget()
                    # find layout idx
                    for j, page_widget in enumerate(self.page_widgets):
                        if page_widget == widget:
                            orig = self.pages_info[j].page_num
                            page_order.append(orig)
                            break

            for orig_page_num in page_order:
                if 0 <= orig_page_num < len(self.document):
                    # create a new page with original size
                    src_page = self.document[orig_page_num]
                    rect = src_page.rect
                    new_page = new_doc.new_page(width=rect.width, height=rect.height)
                    # render original page to pixmap and insert as background image
                    pix = src_page.get_pixmap(alpha=False)
                    base_bytes = pix.tobytes("png")
                    new_page.insert_image(rect, stream=base_bytes)

                    # if we have annotations for layout index of orig_page_num, draw them on top
                    layout_idx = self.layout_index_for_original(orig_page_num)
                    if layout_idx is not None and 0 <= layout_idx < len(self.page_widgets):
                        pw = self.page_widgets[layout_idx]
                        if pw.has_annotations():
                            # export annotation PNG scaled to page size
                            ann_bytes = pw.export_annotations_png(int(rect.width), int(rect.height))
                            if ann_bytes:
                                # insert annotation PNG on the same rect as overlay (overlay=True)
                                try:
                                    new_page.insert_image(rect, stream=ann_bytes, overlay=True)
                                except Exception:
                                    # fallback: still continue without overlay
                                    pass

            # Save (atomic replace if saving to original path)
            if save_path == self.doc_path:
                import tempfile, shutil
                temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf")
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

            # Reset modification state (we consider drawings saved)
            self.is_modified = False
            # After save, clear per-page overlay dirty flags
            for w in self.page_widgets:
                try:
                    w.overlay._dirty = False
                except Exception:
                    pass
            self.deleted_pages.clear()
            self.page_rotations.clear()
            self.document_modified.emit(False)
            return True

        except Exception as e:
            QMessageBox.critical(None, "Save Error", f"Failed to save PDF: {e}")
            return False

    def on_annotation_changed(self):
        """Called when any overlay emits a change (user drew something)."""
        try:
            self.is_modified = True
            self.document_modified.emit(True)
        except Exception:
            pass

    def any_annotations_dirty(self) -> bool:
        """Return True if any page overlay has unsaved annotations."""
        return any((getattr(w, "overlay", None) and w.overlay.is_dirty()) for w in self.page_widgets)

    def set_drawing_mode(self, enabled: bool):
        """Enable or disable drawing mode for all page widgets and show tools panel."""
        self._drawing_mode = bool(enabled)
        for w in self.page_widgets:
            try:
                w.overlay.set_enabled(enabled)
            except Exception:
                pass
        if enabled:
            if not hasattr(self, "drawing_tools"):
                self._create_drawing_tools()
            try:
                self.drawing_tools.show()
            except Exception:
                pass
        else:
            if hasattr(self, "drawing_tools"):
                try:
                    self.drawing_tools.hide()
                except Exception:
                    pass

    def _create_drawing_tools(self):
        """Create a small floating tools panel at top-right of viewport."""
        panel = QFrame(self.viewport())
        panel.setObjectName("drawingTools")
        panel.setStyleSheet("QFrame { background: rgba(255,255,255,0.92); border: 1px solid #bbb; padding:4px; }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        brush_btn = QPushButton("Brush", panel)
        rect_btn = QPushButton("Rect", panel)
        color_btn = QPushButton("Black/White", panel)
        clear_btn = QPushButton("Clear page", panel)
        layout.addWidget(brush_btn)
        layout.addWidget(rect_btn)
        layout.addWidget(color_btn)
        layout.addWidget(clear_btn)
        panel.adjustSize()

        def place_panel():
            vp = self.viewport()
            x = max(8, vp.width() - panel.width() - 8)
            y = 8
            panel.move(x, y)

        place_panel()
        # reconnect placement on resize via viewer's resizeEvent (we add one below)
        brush_btn.clicked.connect(lambda: self._set_tool_for_all("brush"))
        rect_btn.clicked.connect(lambda: self._set_tool_for_all("rect"))
        color_btn.clicked.connect(self._toggle_color_for_all)
        clear_btn.clicked.connect(self._clear_current_page_overlay)

        self.drawing_tools = panel

    def _set_tool_for_all(self, tool: str):
        for w in self.page_widgets:
            try:
                w.overlay.set_tool(tool)
            except Exception:
                pass

    def _toggle_color_for_all(self):
        for w in self.page_widgets:
            try:
                cur = w.overlay.color
                new = QColor(Qt.white) if cur == QColor(Qt.black) else QColor(Qt.black)
                w.overlay.set_color(new)
            except Exception:
                pass

    def _clear_current_page_overlay(self):
        cur_page = self.get_current_page()
        layout_idx = self.layout_index_for_original(cur_page)
        if layout_idx is not None and 0 <= layout_idx < len(self.page_widgets):
            try:
                self.page_widgets[layout_idx].overlay.clear_annotations()
            except Exception:
                pass

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        try:
            if hasattr(self, "drawing_tools") and self.drawing_tools.isVisible():
                vp = self.viewport()
                x = max(8, vp.width() - self.drawing_tools.width() - 8)
                y = 8
                self.drawing_tools.move(x, y)
        except Exception:
            pass

    # ---------------- Fit helpers ----------------
    def fit_to_width(self):
        """Fit document to width"""
        if not self.document or not self.page_widgets:
            return
        viewport_width = self.viewport().width() - 50
        if self.pages_info:
            page_width = self.pages_info[0].width
            new_zoom = viewport_width / page_width
            self.set_zoom(new_zoom)

    def fit_to_height(self):
        """Fit document to height"""
        if not self.document or not self.page_widgets:
            return
        viewport_height = self.viewport().height() - 50
        if self.pages_info:
            page_height = self.pages_info[0].height
            new_zoom = viewport_height / page_height
            self.set_zoom(new_zoom)
