import copy
import math
import os
import gc
import threading
from settings_manager import SettingsManager
from typing import Optional, Dict, Set, List
from classes.document import Document, PageInfo
from classes.cache import PageCache
from classes.rendering import PageRenderWorker

from classes.page_widget_stack import PageWidgetStack
from classes.page_widget import PageWidget

from PySide6.QtWidgets import (
    QScrollArea, QVBoxLayout, QWidget, QLabel, QMessageBox, QInputDialog, QFrame, QPushButton, QLineEdit, QApplication,
    QSpacerItem, QSizePolicy, QButtonGroup, QAbstractButton, QHBoxLayout, QColorDialog
)
from PySide6.QtCore import (
    Qt, QRunnable, QThreadPool, QTimer, Signal, QSize
)
from PySide6.QtGui import QPixmap, QColor, QWheelEvent, QMouseEvent, QIcon, QPainter

import fitz  # PyMuPDF
from fitz import Page, Point


# TODO: Миниатюры прикрутить к текущей странице


class PDFViewer(QScrollArea):
    """Memory-optimized PDF viewer that keeps layout order in pages_info list,
       but uses PageInfo.page_num as the stable original page identifier.
    """

    page_changed = Signal(int)  # emits ORIGINAL page number
    document_modified = Signal(bool)
    set_zoom_signal = Signal(float)

    zoom_type_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_loaded_pages = 15  # Maximum rendered pages in memory
        self.visible_page_limit = 10  # Initial number of placeholders to create
        from PySide6.QtCore import QTimer

        self._center_timer = QTimer(self)
        self._center_timer.setSingleShot(True)
        self._center_timer.timeout.connect(lambda: self._do_pending_center())

        self._pending_center_index = None
        self._last_center_time = 0
        # per-original-page annotation storage (orig_page_num => PNG bytes)
        self.page_annotations = {}
        # per-original-page vector storage (orig_page_num => {"strokes":[...], "rects":[...]})
        self.page_vectors = {}

        print("Initializing PDFViewer")

        # Core properties
        self.document: Document = None
        self.doc_path = ""
        self.document_password = ""
        # self.pages_info: list[PageInfo] = []  # layout order list; each entry has .page_num (original)
        # self.page_widgets: list[PageWidget] = []  # same order as pages_info
        self.pages_container = QWidget()
        self.page_widget_controller: PageWidgetStack = PageWidgetStack(self.pages_container)
        self.page_widget_controller.pagePainted.connect(lambda: self.document_modified.emit(True))

        self.pages_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.zoom_level = 1.0
        self._zoom_type = 0
        # 0 - свободный режим
        # 1 - fit_to_width
        # 2 - fit_to_height
        self.zoom_action = dict([(0, lambda: None),
                                 (1, lambda: QTimer.singleShot(200, self.fit_to_width)),
                                 (2, lambda: QTimer.singleShot(200, self.fit_to_height))])

        self.CtrlPressed = False

        # Document modification tracking
        self.is_modified = False
        self.deleted_pages: Set[int] = set()  # set of ORIGINAL page numbers
        self.page_rotations: Dict[int, int] = {}  # keyed by ORIGINAL page numbers

        self.rotate_view_deg = 0

        # Caching/rendering
        self.page_cache = PageCache(max_size=5)
        # per-original-page annotation storage (orig_page_num => PNG bytes)
        self.page_annotations: Dict[int, bytes] = {}
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(5)  # Single thread to prevent memory spikes

        # Track active render tasks
        self.active_workers: Dict[str, PageRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # UI
        self.setup_ui()

        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.update_visible_pages)

        # self.resize_window_timer = QTimer()
        # self.resize_window_timer.setSingleShot(True)
        # self.resize_window_timer.timeout.connect(self.refresh_render)

        self.verticalScrollBar().valueChanged.connect(self.on_scroll)
        self.last_visible_layout_indices: Set[int] = set()

        self.main_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # auto-zoom properties
    ###
    @property
    def zoom_type(self):
        return self._zoom_type

    @zoom_type.setter
    def zoom_type(self, value):
        if self._zoom_type != value:
            self._zoom_type = value
            self.zoom_action[self._zoom_type]()

    ###

    def setup_ui(self):
        """Setup the scrollable area"""
        print("Setting up PDFViewer UI")

        self.setWidgetResizable(True)
        # self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # self.pages_layout = QVBoxLayout(self.pages_container)
        # self.pages_layout.setSpacing(10)
        # self.pages_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        # self.pages_layout.setContentsMargins(10, 10, 10, 10)  # Add margins
        self.setWidget(self.pages_container)
        print("PDFViewer UI setup complete")

    def _calculate_display_size(self, page_info: PageInfo) -> QSize:
        """Calculate the actual display size for a page at current zoom.
        This matches what PyMuPDF will render."""
        # PyMuPDF uses the matrix to scale, resulting in dimensions = original * zoom
        # We need to ensure we're calculating the exact same dimensions
        width = int(page_info.width * self.zoom_level + 0.5)  # Round to nearest
        height = int(page_info.height * self.zoom_level + 0.5)

        # Ensure minimum size for visibility
        width = max(width, 100)
        height = max(height, 100)

        return QSize(width, height)

    # ---------------- Document open/close ----------------
    def authenticate_document(self) -> Optional[str]:
        """Handle password authentication for encrypted PDFs"""
        try:
            # temp_doc = fitz.open(file_path)
            if self.document.need_auth():
                password, ok = QInputDialog.getText(self, "Password Required",
                                                    f"File {os.path.basename(self.document.file_path)} is password protected.\nEnter password:",
                                                    QLineEdit.Password)
                if ok and password:
                    if self.document.auth(password):
                        return password
                    else:
                        QMessageBox.warning(self, "Authentication Failed", "Invalid password!")
                        self.document.close()
                        return None
                else:
                    self.document.close()
                    return None
            else:
                return ""
        except Exception as e:
            print(f"Error during authentication: {e}")
            return None

    def reinitializePageWidgets(self):
        pages_info = [self.document.get_page_info(i) for i in range(self.document.get_page_count())]
        self.page_widget_controller.initPageInfoList(pages_info)

    def open_document(self, file_path: str) -> bool:
        """Open PDF document with immediate optimization"""

        try:
            print(f"PDFViewer: Opening document: {file_path}")

            self.close_document()
            self.document = Document(file_path)

            self.zoom_level = 1.0

            # Handle password authentication
            password = self.authenticate_document()

            self.document_password = password or ""

            # Quick document info extraction WITHOUT loading pages

            print(f"Document has {self.document.get_page_count()} pages")

            self.doc_path = file_path
            self.page_widget_controller.clear()

            self.reinitializePageWidgets()

            # Reset state and build placeholders
            self.is_modified = False
            self.deleted_pages = set()
            self.page_rotations = {}

            # Dynamic placeholder management
            self.total_page_count = self.page_widget_controller.countTotalPagesInfo  # Store total pages ???

            self.page_widget_controller.calculateMapPagesByIndex(0)

            self.zoom_type = SettingsManager.DEFAULT_ZOOM_TYPE
            # Scroll to top
            self.verticalScrollBar().setValue(0)
            # Force an immediate update to show the document
            self.update()
            self.repaint()

            self.update_container_full_size()
            # Delay initial page loading to prevent freeze
            QTimer.singleShot(100, self.update_visible_pages)

            print(f"Document opened successfully: {self.total_page_count} pages")
            return True

        except Exception as e:
            print(f"Error opening document: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open PDF: {e}")
            return False

    def close_document(self):
        """Close document and aggressively free resources"""
        print("Closing document - aggressive cleanup")

        # Cancel all active renders first
        self.cancel_all_renders()

        # Wait for thread pool to finish current tasks
        self.thread_pool.waitForDone()

        # Close and delete document
        if self.document:
            try:
                self.document.close()
                self.document = None
            except Exception as e:
                print(f"Error closing document: {e}")

        # Clear all caches and collections with proper cleanup
        self.page_cache.clear()
        self.last_visible_layout_indices.clear()

        # Clear all stored data
        # self.pages_info.clear()
        self.page_widget_controller.clear()
        self.deleted_pages.clear()
        self.page_rotations.clear()

        # Clear annotation storage with proper cleanup
        if hasattr(self, 'page_annotations'):
            for key in list(self.page_annotations.keys()):
                # Ensure bytes are properly dereferenced
                self.page_annotations[key] = b''
            self.page_annotations.clear()

        if hasattr(self, 'page_vectors'):
            for key in list(self.page_vectors.keys()):
                self.page_vectors[key] = None
            self.page_vectors.clear()

        # Reset document properties
        self.doc_path = ""
        self.document_password = ""
        self.is_modified = False
        self.zoom_level = 1.0

        # Clear any active worker references
        with self.render_lock:
            # Ensure all worker references are cleared
            for worker_id in list(self.active_workers.keys()):
                worker = self.active_workers[worker_id]
                if hasattr(worker, 'cancel'):
                    worker.cancel()
                del self.active_workers[worker_id]
            self.active_workers.clear()

        # Notify thumbnail widget to clear before final cleanup
        try:
            # If we have a reference to thumbnail widget, tell it to clear
            if hasattr(self, 'parent') and self.parent():
                main_window = self.parent()
                while main_window and not isinstance(main_window, QWidget):
                    main_window = main_window.parent()
                if main_window and hasattr(main_window, 'thumbnail_widget'):
                    main_window.thumbnail_widget.clear_thumbnails()
        except Exception as e:
            print(f"Error clearing thumbnails during document close: {e}")

        # Force multiple garbage collections to ensure cleanup
        for _ in range(3):
            gc.collect()

        print("Document closed and memory cleaned")

    # ---------------- Helpers ----------------
    def layout_index_for_original(self, orig_page_num: int) -> Optional[int]:
        for idx, info in enumerate(self.page_widget_controller.pages_info):
            if info.page_num == orig_page_num:
                return idx
        return None

    def reload_document_after_edit(self):
        """Refresh viewer widgets after the underlying fitz.Document was modified."""
        if not getattr(self, "doc_path", None):
            print("reload_document_after_edit: no doc_path set")
            return False

        self.close_document()
        return self.open_document(self.doc_path)

    def _save_vector_immediate(self, widget, orig_page_num: int):
        """
        Immediately export the widget.overlay vector shapes and store them in self.page_vectors.
        """
        try:
            if not hasattr(self, "page_vectors") or self.page_vectors is None:
                self.page_vectors = {}

            if widget is None or not getattr(widget, "overlay", None):
                return

            try:
                vec = widget.overlay.get_vector_shapes()
            except Exception as e:
                print(f"[PDFViewer] _save_vector_immediate: get_vector_shapes failed for orig {orig_page_num}: {e}")
                vec = {"strokes": [], "rects": []}

            strokes = vec.get("strokes") or []
            rects = vec.get("rects") or []

            if (len(strokes) > 0) or (len(rects) > 0):
                self.page_vectors[orig_page_num] = {"strokes": list(strokes), "rects": list(rects)}
                print(f"[PDFViewer] _save_vector_immediate: saved vector for orig {orig_page_num}")

            else:
                if orig_page_num in self.page_vectors:
                    self.page_vectors.pop(orig_page_num, None)

        except Exception as e:
            print(f"[PDFViewer] _save_vector_immediate error for orig {orig_page_num}: {e}")

    def save_widget_vector(self, widget: PageWidget):
        """Save overlay vector shapes for widget at layout_index into self.page_vectors."""
        try:
            # page_info = self.pages_info[widget.layout_index]
            page_info = widget.page_info
            orig = page_info.page_num

            if not getattr(widget, "overlay", None):
                return

            try:
                vec = widget.overlay.get_vector_shapes()
            except Exception as e:
                print(f"[PDFViewer] save_widget_vector: get_vector_shapes failed: {e}")
                vec = {"strokes": [], "rects": []}

            strokes = vec.get("strokes") or []
            rects = vec.get("rects") or []

            if (len(strokes) > 0) or (len(rects) > 0):
                self.page_vectors[orig] = {"strokes": list(strokes), "rects": list(rects)}
            else:
                if orig in self.page_vectors:
                    self.page_vectors.pop(orig, None)
        except Exception as e:
            print(f"[PDFViewer] save_widget_vector error for layout {widget.layout_index}: {e}")

    def save_widget_annotation(self, widget: PageWidget):
        """Export overlay PNG bytes for the widget at layout_index."""
        try:
            page_info = self.page_widget_controller.getPageInfoByIndex(widget.layout_index)
            orig = page_info.page_num

            if getattr(widget, "base_pixmap", None) is not None:
                tw = widget.base_pixmap.width()
                th = widget.base_pixmap.height()
            else:
                tw = max(1, widget.width())
                th = max(1, widget.height())

            ann_bytes = widget.export_annotations_png(int(tw), int(th))
            if ann_bytes:
                self.page_annotations[orig] = ann_bytes
        except Exception as e:
            print(f"[PDFViewer] save_widget_annotation error for layout {widget.layout_index}: {e}")

    def get_display_page_number(self, layout_index: int) -> int:
        """1-based display number for a layout index (skips deleted original page ids)"""
        if layout_index >= self.page_widget_controller.countTotalPagesInfo:
            return 1
        display = 1
        for i, info in enumerate(self.page_widget_controller.pages_info):
            if info.page_num in self.deleted_pages:
                continue
            if i == layout_index:
                return display
            display += 1
        return display

    def scroll_to_page(self, page_index: int):
        """
        Smoothly scroll the viewer to make the specified page visible,
        loading it first if necessary.
        """

        if page_index < 0 \
                or page_index >= self.page_widget_controller.countTotalPagesInfo \
                or page_index == self.get_current_pageInfo_index():
            return

        new_chunk = self.page_widget_controller.getChunkByPageIndex(page_index)

        if new_chunk != self.page_widget_controller.current_chunk_index:
            self.page_widget_controller.setCurrentChunk(new_chunk)
            self.update_container_full_size()

        target_y = self.page_widget_controller.getTotalHeightByCountPages(page_index, True)

        self.verticalScrollBar().setValue(target_y)

        # 04.02.2026 - убрано в рамках теста
        # Функция просто переводит на нужный уровень скролла - тогда отрисовка, возможно, излишняя
        # QTimer.singleShot(100, self.update_visible_pages)

    def update_all_page_labels(self):
        """Update all page labels to reflect current order and visibility"""
        if not self.page_widget_controller:
            return
        display = 1
        for i, widget in enumerate(self.page_widget_controller):
            orig = self.page_widget_controller.getPageInfoByIndex(i).page_num
            if orig in self.deleted_pages:
                continue

            # Update the widget's display text if it's showing placeholder text
            if hasattr(widget, 'base_label'):
                current_text = widget.base_label.text()
                if "Страница " in current_text and "Загрузка" in current_text:
                    widget.base_label.setText(f"Страница {display}\nЗагрузка...")
            display += 1

    def cancel_all_renders(self):
        """Cancel all active rendering tasks"""
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

    # ---------------- Scrolling & visible pages ----------------
    def on_scroll(self, value):
        """Handle scroll events with delay"""
        if self.CtrlPressed:
            return
        self.cancel_all_renders()
        self.scroll_timer.start(200)

    def update_visible_pages(self):
        """Ultra-conservative visible page management with dynamic placeholder loading"""
        if not self.document:
            return
        # Guard against re-entrant calls (rapid scroll + timer firing simultaneously)
        if getattr(self, '_updating_visible', False):
            return
        self._updating_visible = True
        try:
            self._do_update_visible_pages()
        except Exception as e:
            print(f"[PDFViewer] update_visible_pages error: {e}")
        finally:
            self._updating_visible = False
        gc.collect()

    def _do_update_visible_pages(self):
        """Inner implementation called by update_visible_pages."""
        value = self.verticalScrollBar().value()
        max_scroll = self.verticalScrollBar().maximum()

        if value >= max_scroll - 10 \
                and not self.page_widget_controller.isLastChunk():
            self.page_widget_controller.nextChunk()
            self.update_container_full_size()
            self.verticalScrollBar().setValue(150)

        elif value <= 10 and not self.page_widget_controller.isFirstChunk():
            self.page_widget_controller.prevChunk()
            self.update_container_full_size()
            self.verticalScrollBar().setValue(max_scroll - 150)

        viewport_rect = self.viewport().rect()
        # Re-read scroll value after potential setValue() calls above
        scroll_y = self.verticalScrollBar().value()
        viewport_center_y = scroll_y + viewport_rect.height() // 2

        isNeedCalculateMap = self.page_widget_controller.needCalculateByScrollHeight(viewport_center_y)
        curIndex = self.page_widget_controller.getCurrPageIndexByHeightScroll(viewport_center_y)

        if not self.document:
            return

        self.page_changed.emit(self.page_widget_controller.getPageInfoByIndex(curIndex).page_num)

        if isNeedCalculateMap:
            self.page_widget_controller.calculateMapPagesByIndex(curIndex)

        # Snapshot before iterating: calculateMapPagesByIndex may mutate page_widgets,
        # and rapid scrolling can cause widget deletion between calls.
        widgets_snapshot = list(self.page_widget_controller.page_widgets)
        for widget in widgets_snapshot:
            if not self.document:
                break
            try:
                if widget.isVisibleByViewport(scroll_y - viewport_rect.height() * 2, viewport_rect.height() * 3):
                    self.load_page_if_needed(widget)
            except RuntimeError:
                # Widget was deleted between snapshot and this call (rapid chunk switch)
                pass

    def update_container_full_size(self):
        """Update container size to account for ALL pages (even not-yet-created ones)"""
        # total_pages = len(self.pages_info)
        total_pages = self.page_widget_controller.countTotalPagesInfo
        total_height = 0
        # spacing = self.pages_layout.spacing()
        # TODO: На последнем чанке задавать высоту вьюпорта равной высоте чанка
        total_height = self.page_widget_controller.getTotalHeightByCountPages(total_pages, True)

        # Calculate total height based on all pages
        # for i in range(total_pages):
        #     page_info = self.pages_info[i]
        #     display_size = self._calculate_display_size(page_info)
        #     total_height += display_size.height()
        #     if i < total_pages - 1:
        #         total_height += spacing

        # Add margins
        # margins = self.pages_layout.contentsMargins()
        # total_height += margins.top() + margins.bottom()
        # Set container minimum size to ensure scrollbar works correctly

        # print(f"TtH: {total_height}")

        # if total_height >= self.page_widget_controller.MAX_HEIGHT_CHUNK:
        #     self.pages_container.setMinimumHeight(self.page_widget_controller.MAX_HEIGHT_CHUNK)
        # else:

        print(f"Set Height Container: {min(total_height, self.page_widget_controller.MAX_HEIGHT_CHUNK)}")

        self.pages_container.setMinimumHeight(min(total_height, self.page_widget_controller.MAX_HEIGHT_CHUNK))

        # print(f"Set h: {self.pages_container.height()}")
        # Force layout update
        self.pages_container.adjustSize()

        # self.go_to_page(self.get_current_pageInfo_index())

    def clear_page_widget(self, widget: PageWidget):
        # if layout_index >= self.page_widgets[-1:][0].layout_index or layout_index >= len(self.pages_info):
        #     return

        # widget = list(filter(lambda w: w.layout_index == layout_index, self.page_widgets))[0]
        # widget = next((w for w in self.page_widgets if w.layout_index == layout_index), None)
        # if widget is None: return
        # page_info = self.pages_info[layout_index]

        page_info = widget.page_info

        # Calculate proper display size

        # Save vector shapes before clearing
        try:
            if self.page_vectors is not {}:
                self.save_widget_vector(widget)
        except Exception as e:
            print(f"Save Widget Vector Error: {e}")

        # Save raster overlay if needed
        try:
            orig = page_info.page_num
            if hasattr(widget, "overlay") and widget.overlay.is_dirty():
                if getattr(widget, "base_pixmap", None) is not None:
                    tw = widget.base_pixmap.width()
                    th = widget.base_pixmap.height()
                else:
                    tw = max(1, widget.width())
                    th = max(1, widget.height())
                ann_bytes = widget.export_annotations_png(int(tw), int(th))
                if ann_bytes:
                    self.page_annotations[orig] = ann_bytes
        except Exception:
            pass

        # Clear base image WITHOUT emitting signals and properly cleanup pixmap
        try:
            if hasattr(widget, 'base_pixmap') and widget.base_pixmap:
                widget.base_pixmap = QPixmap()  # Explicitly clear
            widget.clear_base(emit=False)
        except Exception:
            try:
                widget.clear()
            except Exception:
                pass

        # Reset placeholder with proper size
        try:
            display_page_num = self.get_display_page_number(widget.layout_index)
            if hasattr(widget, 'base_label'):
                widget.base_label.setText(f"Страница {display_page_num}\nЗагрузка...")
                widget.base_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception:
            pass

    def load_page_if_needed(self, widget: PageWidget):
        # if layout_index > self.page_widgets[-1:][0].layout_index or layout_index >= len(self.pages_info):
        #     return

        # widget = next((w for w in self.page_widgets if w.layout_index == layout_index), None)
        # if widget already has a base_pixmap, assume loaded
        # 24.12.2025 - убрал для бесшовного зуммирования
        if getattr(widget, "base_pixmap", None) is not None:
            return
        # if not widget.is_empty:
        #     return
        # if widget.base_pixmap is not None:  # getattr(widget, "base_pixmap", None) is not None:
        #     return

        # orig_page = self.pages_info[layout_index].page_num
        orig_page = widget.orig_page_num
        cached = self.page_cache.get(orig_page)
        if cached:
            try:
                widget.set_base_pixmap(cached)
                # Ensure widget size matches pixmap exactly
                widget.setMinimumSize(cached.size())
                widget.setMaximumSize(cached.size())
            except Exception:
                try:
                    widget.setPixmap(cached)
                    widget.setMinimumSize(cached.size())
                    widget.setMaximumSize(cached.size())
                except Exception:
                    pass

            # Restore vectors or raster annotations
            restored = False
            try:
                restored = self._restore_vectors_for_widget(widget, orig_page)
            except Exception:
                restored = False

            if not restored:
                try:
                    ann_bytes = self.page_annotations.get(orig_page)
                    if ann_bytes:
                        loaded = QPixmap()
                        ok = loaded.loadFromData(ann_bytes)
                        if ok and not loaded.isNull():
                            target_sz = cached.size()
                            scaled = loaded.scaled(target_sz, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                            if getattr(widget, "overlay", None):
                                widget.overlay.annot_pixmap = scaled
                                widget.overlay._dirty = True
                                widget.overlay.update()
                except Exception as e:
                    print(f"[PDFViewer] load_page_if_needed: raster restore error: {e}")

            return

        # not cached – do the normal render flow
        self.start_page_render(widget.layout_index)

    def start_page_render(self, layout_index: int):
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"render_{self.current_render_id}_{layout_index}"

        orig_page = self.page_widget_controller.getPageInfoByIndex(layout_index).page_num
        # rotation = self.page_rotations.get(orig_page, 0)

        rotation = self.rotate_view_deg

        worker = PageRenderWorker(
            self.document.get_page(orig_page),
            orig_page,
            self.zoom_level,
            self.on_page_rendered,
            render_id,
            rotation
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
        # if layout_index in self.last_visible_layout_indices and layout_index <= self.page_widget_controller.getLastPageWidget().layout_index:

        if layout_index <= self.page_widget_controller.getLastPageWidget().layout_index:
            # widget = next((w for w in self.page_widgets if w.layout_index == layout_index), None)
            # if widget is None: return

            widget = self.page_widget_controller.getPageWidgetByIndex(layout_index)

            # set base pixmap on our PageWidget and ensure size matches exactly
            try:
                widget.set_base_pixmap(pixmap)
                widget.setMinimumSize(pixmap.size())
                widget.setMaximumSize(pixmap.size())
            except Exception as e:
                print(f"[PDFViewer] on_page_rendered: set_base_pixmap failed: {e}")
                try:
                    widget.setPixmap(pixmap)
                    widget.setMinimumSize(pixmap.size())
                    widget.setMaximumSize(pixmap.size())
                except Exception as e2:
                    print(f"[PDFViewer] on_page_rendered: fallback setPixmap failed: {e2}")

            # Restore vectors or raster
            restored = False
            try:
                restored = self._restore_vectors_for_widget(widget, orig_page_num)
            except Exception:
                restored = False

            if not restored:
                try:
                    ann_bytes = self.page_annotations.get(orig_page_num)
                    if ann_bytes:
                        loaded = QPixmap()
                        ok = loaded.loadFromData(ann_bytes)
                        if ok and not loaded.isNull():
                            target_sz = pixmap.size()
                            scaled = loaded.scaled(target_sz, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                            if getattr(widget, "overlay", None):
                                widget.overlay.annot_pixmap = scaled
                                widget.overlay._dirty = True
                                widget.overlay.update()
                except Exception as e:
                    print(f"[PDFViewer] on_page_rendered: raster restore error: {e}")

            widget.update()

    def set_zoom(self, zoom: float, margin_x: float = 0.5, margin_y: float = 0.5):
        """Set zoom level and refresh."""
        zoom = round(zoom, 2)
        if not self.document or zoom == self.zoom_level:
            return

        print(f"Setting zoom to {zoom}")
        # old_center = self.calculateCenter()

        self.cancel_all_renders()
        total_height = self.page_widget_controller.getTotalHeightByCountPages(
            self.page_widget_controller.countTotalPagesInfo)
        p0 = self.verticalScrollBar().value()

        # На этом моменте self.zoom_level получает новый зум, а zoom - сохраняет старый
        self.zoom_level, zoom = zoom, self.zoom_level
        self.page_cache.clear()

        if self.zoom_level < 1:
            newSizeCache = round(3.2 - 2.95 * math.log(self.zoom_level))
        else:
            newSizeCache = 3

        self.page_cache.max_size = newSizeCache
        old_current_page = self.get_current_pageInfo_index()

        self.page_widget_controller.setZoom(self.zoom_level)
        self.page_widget_controller.setCurrentChunkByPageIndex(old_current_page)
        self.update_container_full_size()

        # Update all widget sizes and clear them
        for i, widget in enumerate(self.page_widget_controller.page_widgets):
            # if i >= len(self.pages_info):
            #     continue

            # Save annotations before clearing
            try:
                if widget.overlay.is_dirty():
                    self.save_widget_annotation(widget)
            except Exception as e:
                print(f"Error in save annotations before clearing: {e}")

            # Resize and clear
            try:
                widget.setZoom(self.zoom_level)
                # 24.12.2025 - убрал для бесшовного зуммирования
                widget.clear_base(emit=False)
            except Exception as e:
                print(f"Error set zoom, widget cleaning. {e}")
                try:
                    widget.clear()
                except Exception as ee:
                    print(f"Error Clean Widget Exception {ee}")

            # old_height_spacer = self.main_spacer.minimumSize().height()
            # self.pages_layout.removeItem(self.main_spacer)
            # self.pages_layout.insertSpacerItem(0, QSpacerItem(0, int(old_height_spacer * self.zoom_level),
            #                                                   QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))

            # 24.12.2025 - убрал для бесшовного зуммирования
            # # Update placeholder text
            # try:
            #     display_page_num = self.get_display_page_number(i)
            #     if hasattr(widget, 'base_label'):
            #         widget.base_label.setText(f"Страница {display_page_num}\nЗагрузка...")
            #         # widget.base_label.setStyleSheet("""
            #         #     QLabel { border: 2px solid #ddd; background-color: white; color: #666; font-size: 14px; margin: -100px; }
            #         # """)
            # except Exception:
            #     pass

        # Update container size
        self.pages_container.adjustSize()
        self.pages_container.updateGeometry()

        gc.collect()
        QTimer.singleShot(100, self.update_visible_pages)  # было 150 ms

        # Смещение ползунков QScrollArea
        new_pos_y = self.calcMargin(p0,
                                    self.viewport().height(),
                                    zoom,
                                    self.zoom_level,
                                    total_height,
                                    self.page_widget_controller.getTotalHeightByCountPages(
                                        self.page_widget_controller.countTotalPagesInfo),
                                    margin_y)

        new_pos_x = self.calcMargin(self.horizontalScrollBar().value(),
                                    self.viewport().width(),
                                    zoom,
                                    self.zoom_level,
                                    self.viewport().width() * zoom,
                                    self.viewport().width() * self.zoom_level,
                                    margin_x)

        self.verticalScrollBar().setValue(new_pos_y)
        self.horizontalScrollBar().setValue(new_pos_x)
        self.set_zoom_signal.emit(self.zoom_level)

    @staticmethod
    def calcMargin(p: int, v: int, k0: float, k1: float, t1: int, t2: int, m: float) -> int:
        # p - позиция скролла, v - viewport (например, высота)
        # k0, k1 - старый/новый зум
        # t1, t2 - макс длина документа до/после зума

        p1 = p / t1 * t2
        d = 2 * v * (k1 - k0) / (k1 + k0)
        return p1 + d * m

    # def mousePressEvent(self, ev: QMouseEvent):
    #     pass
    #     print(f"x: {ev.position().x()}, y: {ev.position().y()}")
    #     print(f"V POS: {self.verticalScrollBar().value() / (self.verticalScrollBar().maximum())}")

    def wheelEvent(self, event: QWheelEvent):
        if QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            self.CtrlPressed = True

            self.zoom_type = 0
            angle = event.angleDelta().y()
            factor = 1.25 if angle > 0 else 0.8
            old_zoom = self.zoom_level
            new_zoom = max(0.25, min(5.0, old_zoom * factor))

            if abs(new_zoom - old_zoom) < 0.001:
                event.accept()
                return

            mouse_pos = event.position().toPoint()
            mouse_pos_x = mouse_pos.x()
            mouse_pos_y = mouse_pos.x()
            viewport = self.viewport()
            viewport_width = viewport.width()
            viewport_height = viewport.height()

            v_scrollbar = self.verticalScrollBar()
            h_scrollbar = self.horizontalScrollBar()
            old_v_scroll = v_scrollbar.value()
            old_h_scroll = h_scrollbar.value()

            content_widget = self.pages_container
            if content_widget:
                content_rect = content_widget.rect()
                mouse_in_content_x = old_h_scroll + mouse_pos_x  # mouse_pos.x()
                mouse_in_content_y = old_v_scroll + mouse_pos_y  # mouse_pos.y()

                if (mouse_in_content_x < 0 or mouse_in_content_x >= content_rect.width() or
                        mouse_in_content_y < 0 or mouse_in_content_y >= content_rect.height()):
                    target_x = old_h_scroll + viewport_width / 2
                    target_y = old_v_scroll + viewport_height / 2
                else:
                    target_x = mouse_in_content_x
                    target_y = mouse_in_content_y
            else:
                target_x = old_h_scroll + viewport_width / 2
                target_y = old_v_scroll + viewport_height / 2

            self.set_zoom(new_zoom)
            # для зума к курсору (потестировать)
            # self.set_zoom(new_zoom, mouse_pos_x / viewport_width, mouse_pos_y / viewport_height)
            QApplication.processEvents()

            zoom_ratio = new_zoom / old_zoom
            new_target_x = target_x * zoom_ratio
            new_target_y = target_y * zoom_ratio

            new_h_scroll = new_target_x - (viewport_width / 2)
            new_v_scroll = new_target_y - (viewport_height / 2)

            v_max = v_scrollbar.maximum()
            h_max = h_scrollbar.maximum()

            if new_h_scroll < 0 and h_max > 0:
                new_h_scroll = max(0, min(h_max * 0.1, new_target_x * 0.5))
            elif new_h_scroll > h_max:
                new_h_scroll = h_max
            else:
                new_h_scroll = max(0, new_h_scroll)

            if new_v_scroll < 0 and v_max > 0:
                new_v_scroll = max(0, min(v_max * 0.1, new_target_y * 0.5))
            elif new_v_scroll > v_max:
                new_v_scroll = v_max
            else:
                new_v_scroll = max(0, new_v_scroll)

            # TODO: Оптимизировать под новую систему с чанками (вероятно, уже не пригодится)
            # h_scrollbar.setValue(int(new_h_scroll))
            # v_scrollbar.setValue(int(new_v_scroll))

            self.update()
            event.accept()
            self.CtrlPressed = False
            # self.set_zoom_signal.emit(new_zoom)
        else:
            super().wheelEvent(event)

    def previous_page(self):
        cur_page = self.get_current_pageInfo_index()
        if cur_page == 0:
            return
        self.scroll_to_page(cur_page - 1)

    def next_page(self):
        cur_page = self.get_current_pageInfo_index()
        if cur_page == self.page_widget_controller.countTotalPagesInfo - 1:
            return
        self.scroll_to_page(cur_page + 1)

    def rotate_view(self, deg):
        self.cancel_all_renders()
        self.page_cache.clear()
        if abs(self.rotate_view_deg + deg) == 360:
            self.rotate_view_deg = 0
        else:
            self.rotate_view_deg += deg

        cur_page = self.get_current_page()
        self.page_widget_controller.setRotationView(self.rotate_view_deg)
        self.update_container_full_size()
        self.scroll_to_page(cur_page)
        # 15.01.2026 - добавил вызов расчета для spacer
        self.page_widget_controller.updateSpacerWithZoom()
        self.refresh_render()

    # ---------------- Navigation helpers ----------------
    def get_total_page_count(self) -> int:
        """Return total pages count in the document"""

        return self.total_page_count

    def get_current_page(self) -> int:
        """Return ORIGINAL page number for the currently centered page."""
        current_layout_idx = self.get_current_pageInfo_index()

        # return self.pages_info[current_layout_idx].
        return self.page_widget_controller.getPageInfoByIndex(current_layout_idx).page_num

    def get_current_pageInfo_index(self) -> int:
        """Return ORIGINAL page number for the currently centered page."""
        if not self.document:
            return 0

        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()
        viewport_center_y = scroll_y + viewport_rect.height() // 2

        return self.page_widget_controller.getCurrPageIndexByHeightScroll(viewport_center_y)

    def get_current_page_object(self) -> PageInfo:
        """Return ORIGINAL page number for the currently centered page."""

        current_layout_idx = self.get_current_pageInfo_index()

        # return self.pages_info[current_layout_idx]
        return self.page_widget_controller.getPageInfoByIndex(current_layout_idx)

    def _restore_vectors_for_widget(self, widget, orig_page):
        """Restore vector primitives from self.page_vectors."""
        try:
            if widget is None or not getattr(widget, "overlay", None):
                return False
            if not hasattr(self, "page_vectors") or self.page_vectors is None:
                return False
            vec = self.page_vectors.get(orig_page)
            if not vec:
                return False

            try:
                widget.overlay.strokes = list(vec.get("strokes", []))
                widget.overlay.rects = list(vec.get("rects", []))
                widget.overlay._dirty = True
                widget.overlay.update()
                return True
            except Exception as e:
                print(f"[PDFViewer] _restore_vectors_for_widget: apply failed: {e}")
                return False
        except Exception as e:
            print(f"[PDFViewer] _restore_vectors_for_widget error: {e}")
            return False

    def get_visible_page_count(self) -> int:
        count = 0
        for info in self.page_widget_controller.pages_info:
            if info.page_num not in self.deleted_pages:
                count += 1
        return count

    def request_center_on_layout_index(self, layout_index: int, delay_ms: int = 80):
        """Request centering on a layout index with debouncing."""
        if layout_index is None:
            return
        self._pending_center_index = int(layout_index)
        try:
            self._center_timer.start(delay_ms)
        except Exception:
            self._do_pending_center()

    def _do_pending_center(self):
        """Perform the actual centering once."""
        idx = self._pending_center_index
        self._pending_center_index = None
        if idx is None:
            return
        try:
            self.center_on_layout_index(idx)
        except Exception as e:
            print(f"[PDFViewer] center error: {e}")

    def center_on_layout_index(self, layout_index: int):
        """Center the viewport on the widget at layout_index."""
        # if not self.page_widgets or layout_index is None:
        #     return

        layout_index = max(0, min(layout_index, self.page_widget_controller.getLastPageWidget().layout_index - 1))

        # widget = next((w for w in self.page_widget_controller.page_widgets if w.layout_index == layout_index), None)
        widget = self.page_widget_controller.getPageWidgetByIndex(layout_index)
        if widget is None:
            return

        try:
            widget_y = widget.y()
            widget_center = widget_y + widget.height() // 2
            viewport_h = self.viewport().height() or 1

            desired_scroll = max(0, widget_center - viewport_h // 2)

            sb = self.verticalScrollBar()
            desired_scroll = max(0, min(desired_scroll, sb.maximum()))

            current = sb.value()
            if int(current) == int(desired_scroll):
                return

            sb.setValue(int(desired_scroll))
        except Exception:
            try:
                self.ensureWidgetVisible(widget, 50, 50)
            except Exception:
                pass
        QTimer.singleShot(80, self.update_visible_pages)

    def go_to_page(self, layout_index: int):
        """Public navigation entrypoint."""
        if not self.page_widget_controller.countTotalPagesInfo < 1:
            return

        if layout_index < 0 or layout_index >= self.page_widget_controller.countTotalPagesInfo:
            return
        self.page_widget_controller.calculateMapPagesByIndex(layout_index)
        self.cancel_all_renders()
        self.request_center_on_layout_index(layout_index, delay_ms=60)

    # ---------------- Page manipulation ----------------
    def _rotate_page(self, rotation: int):
        """Internal method to rotate a page"""
        if not self.document:
            return False
        orig_current = self.get_current_page()
        # current_rotation = self.page_rotations.get(orig_current, 0)
        current_rotation = self.document.get_page(orig_current).rotation
        new_rotation = (current_rotation + rotation) % 360
        # self.page_rotations[orig_current] = new_rotation
        self.page_widget_controller.getPageWidgetByIndex(orig_current).page_info.rotation = new_rotation
        self.document.get_page(orig_current).set_rotation(new_rotation)

        self.reinitializePageWidgets()

        self.doc_changing()

        if orig_current in self.page_cache.cache:
            del self.page_cache.cache[orig_current]

        # layout_idx = self.layout_index_for_original(orig_current)

        widget = self.page_widget_controller.getPageWidgetByIndex(self.get_current_pageInfo_index())

        if widget is not None:
            self.clear_page_widget(widget)
        self.update_all_page_labels()
        QTimer.singleShot(50, self.update_visible_pages)
        return True

    def rotate_page_clockwise(self):
        return self._rotate_page(90)

    def rotate_page_counterclockwise(self):
        return self._rotate_page(-90)

    def delete_current_page(self):
        """Delete the current page."""
        if not self.document:
            return False

        orig_current = self.get_current_page()

        if self.get_visible_page_count() <= 1:
            QMessageBox.warning(None, "Ошибка удаления", "Нельзя удалить все страницы в документе.")
            return False

        self.page_widget_controller.removePageWidget(self.page_widget_controller.getLastPageWidget())
        self.document.delete_page(orig_current)

        self.reinitializePageWidgets()
        self.doc_changing()

        return True

    def delete_pages_by_range(self, pages_to_delete: List[int]) -> bool:
        """Delete pages: either the current page only, or a user-specified range."""

        total_pages = self.page_widget_controller.countTotalPagesInfo

        if len(pages_to_delete) >= total_pages:
            QMessageBox.warning(self, "Ошибка", "Нельзя удалить все страницы.")
            return False

        sorted_pages_to_delete = sorted(set(pages_to_delete), reverse=True)

        try:
            for page in sorted_pages_to_delete:
                self.document.delete_page(page)
                if self.page_widget_controller.getPageWidgetByIndex(page) is not None:
                    self.page_widget_controller.removePageWidget(self.page_widget_controller.getLastPageWidget())

        except Exception as e:
            QMessageBox.critical(self, "Ошибка удаления", f"Не удалось удалить страницы:\n{e}")
            return False

        self.reinitializePageWidgets()
        self.doc_changing()

        return True

    def _move_page(self, direction: int):
        # TODO: При перемещении страниц - обновлять миниатюры
        """Move the currently centered page in layout."""
        orig_current = self.get_current_pageInfo_index()
        orig_target = orig_current + direction

        countTotal = self.page_widget_controller.countTotalPagesInfo

        if orig_target < 0 or orig_target > countTotal:
            return False

        orig_target += (direction > 0)
        # Если перенос на место последней страницы, то -1 (для указания конца документа)
        orig_target = orig_target if orig_target != countTotal else -1

        self.document.move_page(orig_current, orig_target)

        self.doc_changing()

        return True

    def doc_changing(self):
        self.is_modified = True
        self.document_modified.emit(True)

        self.update_all_page_labels()
        print("DELETING")
        self.last_visible_layout_indices.clear()
        QTimer.singleShot(50, self.update_visible_pages)

        try:
            self.page_changed.emit(self.get_current_page())
        except Exception:
            pass
        self.refresh_render()

    def refresh_render_by_index(self, index):
        pass

    def refresh_render(self):

        # self.set_zoom(self.zoom_level + 0.000001)

        self.cancel_all_renders()
        self.page_cache.clear()
        for i, widget in enumerate(self.page_widget_controller.page_widgets):
            # if i >= len(self.pages_info):
            #     continue

            # Save annotations before clearing
            try:
                if widget.overlay.is_dirty():
                    self.save_widget_annotation(widget)
            except Exception as e:
                print(f"Error in save annotations before clearing: {e}")

            # Resize and clear
            try:
                # widget.setZoom(self.zoom_level)
                widget.clear_base(emit=False)
            except Exception as e:
                print(f"Error set zoom, widget cleaning. {e}")
                try:
                    widget.clear()
                except Exception as ee:
                    print(f"Error Clean Widget Exception {ee}")

            # old_height_spacer = self.main_spacer.minimumSize().height()
            # self.pages_layout.removeItem(self.main_spacer)
            # self.pages_layout.insertSpacerItem(0, QSpacerItem(0, int(old_height_spacer * self.zoom_level),
            #                                                   QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))

            # Update placeholder text
            try:
                display_page_num = self.get_display_page_number(i)
                if hasattr(widget, 'base_label'):
                    widget.base_label.setText(f"Страница {display_page_num}\nЗагрузка...")
                    # widget.base_label.setStyleSheet("""
                    #     QLabel { border: 2px solid #ddd; background-color: white; color: #666; font-size: 14px; margin: -100px; }
                    # """)
            except Exception:
                pass

        # Update container size
        self.pages_container.adjustSize()
        self.pages_container.updateGeometry()

        gc.collect()
        QTimer.singleShot(150, self.update_visible_pages)
        self.update_container_full_size()

    def move_page_up(self):
        return self._move_page(-1)

    def move_page_down(self):
        return self._move_page(1)

    def overlay_render(self, new_page: Page, width: int, height: int, layout_idx: int):

        vec = self.page_widget_controller.dict_vectors.vectors[layout_idx]

        print(f"vec {vec}")
        # Этот блок избыточен - страница здесь полюбому с пометками
        # if overlay empty but stored vectors exist, use them
        # if (not vec.get("strokes") and not vec.get("rects")) and (
        #         layout_idx in self.page_vectors):
        #     vec = self.page_vectors.get(layout_idx, {"strokes": [], "rects": []})
        # if vec and (vec.get("strokes") or vec.get("rects")):
        #     # draw each primitive into the PDF page as vector shapes
        #     pass

        shape = new_page.new_shape()
        # page_rect = rect  # src_page.rect mapped to new_page
        # If the PageWidget has a base_pixmap, compute mapping factors
        widget_w = int(self.document.get_page_size(layout_idx)[0] * self.zoom_level)
        # widget_w = pw.base_pixmap.width() if getattr(pw, "base_pixmap",
        #                                              None) is not None else pw.width() or 1
        # widget_h = pw.base_pixmap.height() if getattr(pw, "base_pixmap",
        #                                               None) is not None else pw.height() or 1
        pdf_w = float(width)
        pdf_h = float(height)

        # draw strokes: points are normalized (0..1) in overlay
        for s in vec.get("strokes", []):
            pts = s.get("points", [])
            if not pts or len(pts) < 2:
                continue
            stroke_color = s.get("color", (0, 0, 0))
            stroke_width_px = float(s.get("width", 1))
            # convert width px -> pdf units (use pdf_w/widget_w scale)
            stroke_width = (stroke_width_px / max(1.0, widget_w)) * pdf_w

            last_point = None
            for nx, ny in pts:
                x = nx * pdf_w
                y = ny * pdf_h
                if last_point is None:
                    last_point = Point(x, y) * new_page.derotation_matrix
                else:
                    shape.draw_line(last_point, Point(x, y) * new_page.derotation_matrix)
                    last_point = Point(x, y) * new_page.derotation_matrix

            # finish this stroke with stroke_color and stroke_width
            r, g, b = stroke_color
            # map 0-255 -> 0..1
            shape.finish(color=(r / 255.0, g / 255.0, b / 255.0), fill=None,
                         width=stroke_width, closePath=False)
            shape.commit()
            # create a fresh shape object for next primitive
            shape = new_page.new_shape()

        # draw rects (filled)
        for rdef in vec.get("rects", []):
            x0, y0, x1, y1 = rdef.get("rect", (0, 0, 0, 0))
            # normalized -> pdf coords
            x_a = x0 * pdf_w
            y_a = y0 * pdf_h
            x_b = x1 * pdf_w
            y_b = y1 * pdf_h
            rcol = rdef.get("color", (0, 0, 0))
            rr, rg, rb = rcol
            shape.draw_rect(fitz.Rect(x_a, y_a, x_b, y_b) * new_page.derotation_matrix)
            shape.finish(color=(rr / 255.0, rg / 255.0, rb / 255.0),
                         fill=(rr / 255.0, rg / 255.0, rb / 255.0), width=0)
            shape.commit()
            shape = new_page.new_shape()

    def save_changes(self, file_path: str = None) -> bool:

        """Save changes to file: build page_order by iterating layout and using ORIGINAL page numbers.
        This version inserts the original page content and then overlays annotation PNG (if present) on top.
        """
        # print(f"obj {self.dict_vectors.vectors}")  # page_widget_controller.page_vectors

        # for i in self.dict_vectors.vectors.keys():
        #     print(f"item {self.dict_vectors.vectors[i]}")
        # return False

        if not self.document:  # or not self.is_modified
            return True
        try:
            # Determine save path - use original if we have it (for enumeration case)
            if file_path:
                save_path = file_path
            elif hasattr(self, '_original_doc_path') and self._original_doc_path:
                save_path = self._original_doc_path
            else:
                save_path = self.doc_path

            try:
                # внести черкаши в текущий объект self.document
                for key in self.page_widget_controller.dict_vectors.vectors.keys():
                    src_page = self.document.get_page(key)

                    # Нужно или нет - пока непонятно, оставлю комментарием
                    # Apply rotation if it exists BEFORE rendering
                    # rotation = self.page_rotations.get(layout_idx, 0)
                    # if rotation != 0:
                    #     src_page.set_rotation(rotation)

                    # Для определения штампов и прочего
                    # annotations = list(src_page.annots())
                    # print(f"ANNOTATIONS:{annotations}")
                    # for ann in annotations:
                    #     print(f"TYPE:{ann.type}")

                    rect = src_page.rect

                    # Render original page with rotation applied to pixmap
                    # zoom = 2.5
                    # mat = fitz.Matrix(a=zoom, d=zoom)  # ,
                    # pix = src_page.get_pixmap(alpha=False, matrix=mat)
                    # base_bytes = pix.tobytes("jpg")
                    # new_page = self.document.current_doc.new_page(pno=key, width=rect.width, height=rect.height)
                    # new_page.insert_image(rect, stream=base_bytes)

                    # Рисуем поверх страницы
                    self.overlay_render(src_page, rect.width, rect.height, key)

                # в конце сохраняем
                self.document.save(save_path, save_path == self.doc_path)
                return True
            except Exception as e:
                print(f"ERROR {e}")
                return False

            # new_doc = fitz.open()
            new_doc = Document()
            # new_new_doc = copy.deepcopy(self.document.current_doc)
            # page_order: list of original page numbers in current layout (skip deleted originals)
            page_order = []
            for i in range(self.page_widget_controller.count()):
                item = self.page_widget_controller.itemAt(i)
                if item and item.widget() and not item.widget().isHidden():
                    widget = item.widget()
                    # find layout idx
                    for j, page_widget in enumerate(self.page_widget_controller):
                        if page_widget == widget:
                            orig = self.page_widget_controller.getPageInfoByIndex(j).page_num
                            page_order.append(orig)
                            break

            for orig_page_num in page_order:
                if 0 <= orig_page_num < self.document.get_page_count():
                    # Get source page
                    src_page = self.document.get_page(orig_page_num)

                    # Apply rotation if it exists BEFORE rendering
                    rotation = self.page_rotations.get(orig_page_num, 0)
                    if rotation != 0:
                        src_page.set_rotation(rotation)

                    rect = src_page.rect
                    new_page = new_doc.current_doc.new_page(width=rect.width, height=rect.height)

                    # Render original page with rotation applied to pixmap
                    zoom = 2.5
                    mat = fitz.Matrix(a=zoom, d=zoom)  # ,
                    pix = src_page.get_pixmap(alpha=False, matrix=mat)
                    base_bytes = pix.tobytes("jpg")
                    new_page.insert_image(rect, stream=base_bytes)

                    # if we have annotations for layout index of orig_page_num, draw them on top
                    layout_idx = self.layout_index_for_original(orig_page_num)
                    if layout_idx is not None and 0 <= layout_idx < self.page_widget_controller.getLastPageWidget().layout_index:
                        # pw = next((w for w in self.page_widgets if w.layout_index == layout_idx), None)
                        pw = self.page_widget_controller.getPageWidgetByIndex(layout_idx)
                        # Prefer vector annotations if present
                        try:
                            # Vector path handling
                            vec = {}
                            try:
                                vec = pw.overlay.get_vector_shapes()
                            except Exception:
                                vec = {"strokes": [], "rects": []}
                            # if overlay empty but stored vectors exist, use them
                            if (not vec.get("strokes") and not vec.get("rects")) and (
                                    orig_page_num in self.page_vectors):
                                vec = self.page_vectors.get(orig_page_num, {"strokes": [], "rects": []})

                            if vec and (vec.get("strokes") or vec.get("rects")):
                                # draw each primitive into the PDF page as vector shapes
                                try:
                                    shape = new_page.new_shape()
                                    page_rect = rect  # src_page.rect mapped to new_page
                                    # If the PageWidget has a base_pixmap, compute mapping factors
                                    widget_w = pw.base_pixmap.width() if getattr(pw, "base_pixmap",
                                                                                 None) is not None else pw.width() or 1
                                    widget_h = pw.base_pixmap.height() if getattr(pw, "base_pixmap",
                                                                                  None) is not None else pw.height() or 1
                                    pdf_w = float(page_rect.width)
                                    pdf_h = float(page_rect.height)

                                    # draw strokes: points are normalized (0..1) in overlay
                                    for s in vec.get("strokes", []):
                                        pts = s.get("points", [])
                                        if not pts or len(pts) < 2:
                                            continue
                                        stroke_color = s.get("color", (0, 0, 0))
                                        stroke_width_px = float(s.get("width", 1))
                                        # convert width px -> pdf units (use pdf_w/widget_w scale)
                                        stroke_width = (stroke_width_px / max(1.0, widget_w)) * pdf_w

                                        last_point = None
                                        for nx, ny in pts:
                                            x = nx * pdf_w
                                            y = ny * pdf_h
                                            if last_point is None:
                                                last_point = (x, y)
                                            else:
                                                shape.draw_line(last_point, (x, y))
                                                last_point = (x, y)

                                        # finish this stroke with stroke_color and stroke_width
                                        r, g, b = stroke_color
                                        # map 0-255 -> 0..1
                                        shape.finish(color=(r / 255.0, g / 255.0, b / 255.0), fill=None,
                                                     width=stroke_width)
                                        shape.commit()
                                        # create a fresh shape object for next primitive
                                        shape = new_page.new_shape()

                                    # draw rects (filled)
                                    for rdef in vec.get("rects", []):
                                        x0, y0, x1, y1 = rdef.get("rect", (0, 0, 0, 0))
                                        # normalized -> pdf coords
                                        x_a = x0 * pdf_w
                                        y_a = y0 * pdf_h
                                        x_b = x1 * pdf_w
                                        y_b = y1 * pdf_h
                                        rcol = rdef.get("color", (0, 0, 0))
                                        rr, rg, rb = rcol
                                        shape.draw_rect(fitz.Rect(x_a, y_a, x_b, y_b))
                                        shape.finish(color=(rr / 255.0, rg / 255.0, rb / 255.0),
                                                     fill=(rr / 255.0, rg / 255.0, rb / 255.0), width=0)
                                        shape.commit()
                                        shape = new_page.new_shape()

                                except Exception as e:
                                    # fallback to raster overlay if vector commit fails
                                    print(f"[PDFViewer] vector overlay commit failed for orig {orig_page_num}: {e}")
                                    try:
                                        ann_bytes = pw.export_annotations_png(int(page_rect.width),
                                                                              int(page_rect.height))
                                        if ann_bytes:
                                            new_page.insert_image(page_rect, stream=ann_bytes, overlay=True)
                                    except Exception:
                                        pass

                            else:
                                # no vector shapes — fallback to PNG overlay if overlay has raster
                                try:
                                    ann_bytes = pw.export_annotations_png(int(rect.width), int(rect.height))
                                    if ann_bytes:
                                        new_page.insert_image(rect, stream=ann_bytes, overlay=True)
                                except Exception:
                                    pass
                        except Exception:
                            # if anything goes wrong, keep going (do not abort entire save)
                            try:
                                ann_bytes = pw.export_annotations_png(int(rect.width), int(rect.height))
                                if ann_bytes:
                                    new_page.insert_image(rect, stream=ann_bytes, overlay=True)
                            except Exception:
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
                # self.document = fitz.open(self.doc_path)
                self.document = Document(self.doc_path)
                if self.document.need_auth():  # self.document.needs_pass:
                    self.document.auth(self.document_password)  # self.document.authenticate(self.document_password)
            else:
                new_doc.save(save_path)
                new_doc.close()

            # clean up temp file and restore path
            if hasattr(self, '_original_doc_path') and self._original_doc_path:
                # Remove temp file if it exists
                if self.doc_path != self._original_doc_path:
                    try:
                        # import os
                        if os.path.exists(self.doc_path):
                            os.remove(self.doc_path)
                    except Exception as e:
                        print(f"Failed to remove temp file: {e}")

                # Restore original path
                self.doc_path = self._original_doc_path
                delattr(self, '_original_doc_path')

            # Remove stored annotation bytes for pages we saved (or just clear all for simplicity)
            try:
                # If we have a local page_order list used during save, we can delete per-page:
                # for orig in page_order:
                #     self.page_annotations.pop(orig, None)

                # after saving succeeded for the document:
                try:
                    # remove entries for pages that were saved (page_order)
                    for orig in page_order:
                        self.page_vectors.pop(orig, None)
                except Exception:
                    pass

                self.page_annotations.clear()
            except Exception:
                self.page_annotations = {}

            # Reset modification state (we consider drawings saved)
            self.is_modified = False
            # After save, clear per-page overlay dirty flags
            for w in self.page_widget_controller:
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

    def on_annotation_changed(self, orig_page_num=None):
        """
        Slot called when an overlay signals a change.
        Accepts either:
          - orig_page_num (int) if connected with a lambda capturing it, or
          - no args (Qt sender() used to find which overlay emitted).
        Saves annotation PNG bytes into self.page_annotations and marks document modified.
        """
        try:
            # Determine which original page this update belongs to
            layout_idx = None
            if orig_page_num is None:
                sender = self.sender()  # overlay widget that emitted
                if sender is None:
                    return
                # find overlay owner
                for idx, w in enumerate(self.page_widget_controller):
                    if getattr(w, "overlay", None) is sender:
                        layout_idx = idx
                        orig_page_num = self.page_widget_controller.getPageInfoByIndex(idx).page_num
                        break
            else:
                layout_idx = self.layout_index_for_original(orig_page_num)

            if layout_idx is None or not (
                    0 <= layout_idx < self.page_widget_controller.getLastPageWidget().layout_index):
                # nothing we can do
                return

            # pw = next((w for w in self.page_widgets if w.layout_index == layout_idx), None)
            pw = self.page_widget_controller.getPageWidgetByIndex(layout_idx)

            # choose export size: prefer base_pixmap (actual rendered page size), fallback to widget size
            if getattr(pw, "base_pixmap", None) is not None:
                tw = pw.base_pixmap.width()
                th = pw.base_pixmap.height()
            else:
                tw = max(1, pw.width())
                th = max(1, pw.height())

            ann_bytes = pw.export_annotations_png(int(tw), int(th))
            if ann_bytes:
                self.page_annotations[orig_page_num] = ann_bytes

            # mark as modified and notify UI
            self.is_modified = True
            try:
                self.document_modified.emit(True)
            except Exception:
                pass

        except Exception as e:
            print(f"[PDFViewer] on_annotation_changed error: {e}")

    def any_annotations_dirty(self) -> bool:
        """Return True if any page overlay has unsaved annotations."""
        return any(
            (getattr(w, "overlay", None) and w.overlay.is_dirty()) for w in self.page_widget_controller.page_widgets)

    def set_drawing_mode(self, enabled: bool):
        """Enable or disable drawing mode for all page widgets and show tools panel."""
        self._drawing_mode = bool(enabled)
        for w in self.page_widget_controller:
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
        panel = QFrame(self.viewport())
        panel.setObjectName("drawingTools")
        panel.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.92);
                border: 1px solid #bbb;
                padding: 4px;
            }
            QPushButton {
                padding: 4px 8px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: #f0f0f0;
            }
            QPushButton:checked {
                background: #e0e0e0;
                border: 2px solid #0078d7;
                font-weight: bold;
            }
            QPushButton#colorBtn {
                border: 2px solid #333;
                min-width: 28px;
            }
        """)

        main_layout = QVBoxLayout(panel)
        main_layout.setContentsMargins(4, 4, 4, 4)

        tool_layout = QHBoxLayout()
        tool_layout.setSpacing(2)
        tool_layout.setContentsMargins(0, 0, 0, 0)

        self._tool_group = QButtonGroup(panel)
        self._tool_group.setExclusive(True)

        brush_btn = QPushButton("", panel)
        brush_btn.setCheckable(True)
        brush_btn.setObjectName("brushBtn")
        # brush_btn.setMinimumWidth(80)
        brush_btn.setIcon(QIcon(f":/light_theme_v2/brush.png"))
        brush_btn.setIconSize(QSize(24, 24))

        rect_btn = QPushButton("", panel)
        rect_btn.setCheckable(True)
        rect_btn.setObjectName("rectBtn")
        # rect_btn.setMinimumWidth(120)
        rect_btn.setIcon(QIcon(f":/light_theme_v2/rectangle.png"))
        rect_btn.setIconSize(QSize(24, 24))

        self._current_draw_color = QColor(Qt.black)

        preview_btn = QPushButton("", panel)
        preview_btn.setCheckable(False)
        preview_btn.setObjectName("colorBtn")
        preview_btn.setToolTip("Select drawing color")
        self._update_color_button_icon(preview_btn)

        self._tool_group.addButton(brush_btn)
        self._tool_group.addButton(rect_btn)

        brush_btn.setChecked(True)

        tool_layout.addWidget(brush_btn)
        tool_layout.addWidget(rect_btn)
        tool_layout.addWidget(preview_btn)

        main_layout.addLayout(tool_layout)

        clear_btn = QPushButton("Очистить холст", panel)
        all_clear_btn = QPushButton("Очистить все страницы", panel)

        main_layout.addWidget(clear_btn)
        main_layout.addWidget(all_clear_btn)

        panel.adjustSize()

        def place_panel():
            vp = self.viewport()
            x = max(8, vp.width() - panel.width() - 8)
            y = 8
            panel.move(x, y)

        place_panel()

        self._tool_group.buttonToggled.connect(self._on_tool_toggled)

        preview_btn.clicked.connect(self._open_color_dialog)

        clear_btn.clicked.connect(self._clear_current_page_overlay)
        all_clear_btn.clicked.connect(self._clear_all_pages_overlay)

        self.drawing_tools = panel

    def _update_color_button_icon(self, btn: QPushButton):
        pixmap = QPixmap(24, 24)
        pixmap.fill(self._current_draw_color)

        btn.setIcon(QIcon(pixmap))
        btn.setIconSize(QSize(24, 24))

    def _on_tool_toggled(self, button: QAbstractButton, checked: bool):
        if not checked:
            return

        name = button.objectName()
        if name == "brushBtn":
            self._set_tool_for_all("brush")
        elif name == "rectBtn":
            self._set_tool_for_all("rect")

    def _open_color_dialog(self):
        color = QColorDialog.getColor(
            self._current_draw_color,
            self,
            "Выберите цвет рисования",
            options=QColorDialog.DontUseNativeDialog
        )
        if color.isValid():
            self._current_draw_color = color
            self._update_color_button_icon(self.drawing_tools.findChild(QPushButton, "colorBtn"))
            self._set_color_for_all(color)

    def _set_color_for_all(self, color: QColor):
        """Apply the given color to all page overlays."""
        for w in self.page_widget_controller:
            try:
                w.overlay.set_color(color)
            except Exception as e:
                print(f"[PDFViewer] Failed to set color: {e}")

    def _set_tool_for_all(self, tool: str):
        for w in self.page_widget_controller:
            try:
                w.overlay.set_tool(tool)
            except Exception:
                pass

    def _toggle_color_for_all(self):
        for w in self.page_widget_controller:
            try:
                cur = w.overlay.color
                new = QColor(Qt.white) if cur == QColor(Qt.black) else QColor(Qt.black)
                w.overlay.set_color(new)
            except Exception:
                pass

    def _clear_current_page_overlay(self):
        cur_page = self.get_current_page()
        layout_idx = self.layout_index_for_original(cur_page)
        if layout_idx is not None and 0 <= layout_idx < self.page_widget_controller.getLastPageWidget().layout_index:
            try:
                self.page_widget_controller.getPageWidgetByIndex(layout_idx).overlay.clear_annotations()
                self.page_widget_controller.dict_vectors.Remove(layout_idx)
            except Exception:
                pass

    def _clear_all_pages_overlay(self):
        for i, widget_unit in enumerate(self.page_widget_controller):
            widget_unit.overlay.clear_annotations()
        self.page_widget_controller.dict_vectors.Clear()

    def resizeEvent(self, ev):
        # Событие при изменении ширины миниатюр
        super().resizeEvent(ev)
        try:
            # self.resize_window_timer.start(400)
            if hasattr(self, "drawing_tools") and self.drawing_tools.isVisible():
                vp = self.viewport()
                x = max(8, vp.width() - self.drawing_tools.width() - 8)
                y = 8
                self.drawing_tools.move(x, y)
        except Exception:
            pass

    # ---------------- Fit helpers ----------------
    def toggle_fit_to_width(self):
        self.toggling_fit(1)  # int(isPressed) * 1

    def toggle_fit_to_height(self):
        self.toggling_fit(2)  # int(isPressed) * 2

    def toggling_fit(self, val: int):
        # value = int(isPressed) * val
        # if self.zoom_type != value:
        #     self.zoom_type = value
        self.zoom_type = 0
        self.zoom_type = val

    def fit_to_width(self):
        """Fit current page to width of the PDF viewer panel"""
        viewport_width = self.viewport().width() - 20  # Subtract padding
        current_layout_idx = self.get_current_pageInfo_index()  # get_current_page()
        page_height = self.page_widget_controller.getPageInfoByIndex(current_layout_idx).width
        self.fit_to_generic(viewport_width, page_height)

    def fit_to_height(self):
        """Fit document to height"""
        viewport_height = self.viewport().height() - 50
        current_layout_idx = self.get_current_pageInfo_index() # get_current_page()
        page_height = self.page_widget_controller.getPageInfoByIndex(current_layout_idx).height
        self.fit_to_generic(viewport_height, page_height)

    def fit_to_generic(self, viewport_var: int, orig_var: int):

        if not self.document or not self.page_widget_controller.page_widgets \
                or viewport_var <= 0 or orig_var <= 0:
            return

        new_zoom = viewport_var / orig_var
        new_zoom = max(0.25, min(5.0, new_zoom))

        self.set_zoom(new_zoom, margin_y=0)
        QTimer.singleShot(100, self.center_horizontal_scrollbar)

    def center_horizontal_scrollbar(self):
        h_scrollbar = self.horizontalScrollBar()
        center_scroll = h_scrollbar.maximum() // 2
        h_scrollbar.setValue(center_scroll)
