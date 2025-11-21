import fitz  # PyMuPDF
import threading
from collections import OrderedDict
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QSlider
)
from PySide6.QtCore import (
    Qt, Signal, QSize, QTimer, QRunnable, QThreadPool, QObject)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QImage

BUFFER_SIZE = 15
MAX_CACHE_SIZE = 20
DEFAULT_THUMB_SIZE = 150
SCROLL_DEBOUNCE_MS = 100


class WorkerSignals(QObject):
    result = Signal(int, object, int)  # page_num, qimage, thumb_size


class ThumbnailRenderWorker(QRunnable):
    def __init__(self, doc_path, page_num, size, password="", rotation=0):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num
        self.size = size
        self.password = password
        self.rotation = rotation
        self.signals = WorkerSignals()
        self.is_cancelled = False

    def run(self):
        if self.is_cancelled:
            return

        doc = None
        try:
            doc = fitz.open(self.doc_path)
            if self.password and doc.needs_pass:
                doc.authenticate(self.password)

            page = doc.load_page(self.page_num)

            # Apply rotation if needed
            if self.rotation != 0:
                page.set_rotation(self.rotation)

            # Calculate zoom to match requested thumbnail size
            zoom = self.size / page.rect.width
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Convert to QImage
            fmt = QImage.Format_RGB888
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            qimg = qimg.copy()

            if not self.is_cancelled:
                self.signals.result.emit(self.page_num, qimg, self.size)

        except Exception as e:
            print(f"Thumbnail render error on page {self.page_num}: {e}")
        finally:
            if doc:
                doc.close()


class ThumbnailManager(QObject):
    thumbnail_loaded = Signal(int, QImage, int)

    def __init__(self, thread_pool, parent=None):
        super().__init__(parent)
        self.thread_pool = thread_pool

        # State
        self.doc_path = None
        self.password = ""
        self.total_pages = 0
        self.current_size = DEFAULT_THUMB_SIZE
        self.page_rotations = {}  # Track page rotations

        # Cache & Queues
        self.cache = OrderedDict()
        self.pending_requests = set()
        self.tasks = {}

        self.render_lock = threading.Lock()

    def set_document(self, doc_path, password, total_pages):
        self.cancel_all()
        self.doc_path = doc_path
        self.password = password
        self.total_pages = total_pages
        self.cache.clear()
        self.pending_requests.clear()
        self.page_rotations.clear()  # Clear on new document

    def set_page_rotation(self, page_num: int, rotation: int):
        self.page_rotations[page_num] = rotation

    def get_page_rotation(self, page_num: int) -> int:
        return self.page_rotations.get(page_num, 0)

    def cancel_all(self):
        with self.render_lock:
            for task in self.tasks.values():
                task.is_cancelled = True
            self.tasks.clear()
            self.pending_requests.clear()

    def update_visible_range(self, first_visible, last_visible):
        if not self.doc_path:
            return

        load_start = max(0, first_visible - BUFFER_SIZE)
        load_end = min(self.total_pages - 1, last_visible + BUFFER_SIZE)
        target_range = range(load_start, load_end + 1)
        target_set = set(target_range)

        keep_margin = BUFFER_SIZE * 2
        keep_start = max(0, first_visible - keep_margin)
        keep_end = min(self.total_pages - 1, last_visible + keep_margin)
        keep_set = set(range(keep_start, keep_end + 1))

        self._cancel_irrelevant_tasks(keep_set)
        self._manage_cache_memory(target_set)

        missing_pages = [p for p in target_range
                         if p not in self.cache and p not in self.pending_requests]

        if not missing_pages:
            return

        center = (first_visible + last_visible) / 2
        missing_pages.sort(key=lambda p: abs(p - center))

        for page_num in missing_pages:
            self._load_thumbnail_async(page_num)

    def _load_thumbnail_async(self, page_num):
        if page_num in self.pending_requests:
            return

        self.pending_requests.add(page_num)

        rotation = self.get_page_rotation(page_num)

        worker = ThumbnailRenderWorker(
            self.doc_path, page_num, self.current_size, self.password, rotation
        )
        worker.signals.result.connect(self._on_worker_finished)

        with self.render_lock:
            self.tasks[page_num] = worker

        self.thread_pool.start(worker)

    def _on_worker_finished(self, page_num, qimage, thumb_size):
        with self.render_lock:
            self.pending_requests.discard(page_num)
            if page_num in self.tasks:
                del self.tasks[page_num]

        pixmap = QPixmap.fromImage(qimage)

        if page_num in self.cache:
            del self.cache[page_num]
        self.cache[page_num] = pixmap

        self.thumbnail_loaded.emit(page_num, qimage, thumb_size)

    def _manage_cache_memory(self, required_range):
        if len(self.cache) <= MAX_CACHE_SIZE:
            return

        candidates = [p for p in self.cache if p not in required_range]
        for page_num in candidates:
            if len(self.cache) <= MAX_CACHE_SIZE:
                break
            self._cleanup_thumbnail(page_num)

    def _cancel_irrelevant_tasks(self, keep_set):
        with self.render_lock:
            for page_num in list(self.tasks.keys()):
                if page_num not in keep_set:
                    self.tasks[page_num].is_cancelled = True
                    del self.tasks[page_num]
                    self.pending_requests.discard(page_num)

    def _cleanup_thumbnail(self, page_num):
        if page_num in self.cache:
            pixmap = self.cache[page_num]
            if not pixmap.isNull():
                pixmap = QPixmap()
            del self.cache[page_num]

    def get_thumbnail(self, page_num):
        if page_num in self.cache:
            self.cache.move_to_end(page_num)
            return self.cache[page_num]
        return None

    def remove_page(self, page_num):
        self._cleanup_thumbnail(page_num)
        with self.render_lock:
            if page_num in self.tasks:
                self.tasks[page_num].is_cancelled = True
                del self.tasks[page_num]
                self.pending_requests.discard(page_num)


class ThumbnailWidget(QWidget):
    page_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(max(1, QThreadPool.globalInstance().maxThreadCount() - 1))

        self.manager = ThumbnailManager(self.thread_pool)
        self.manager.thumbnail_loaded.connect(self._on_thumbnail_loaded)

        self.document = None
        self.doc_path = ""
        self.document_password = ""
        self.page_rotations = {}
        self.deleted_pages = set()
        self.display_order = []

        self.thumbnail_size = DEFAULT_THUMB_SIZE
        self.page_number_font_size = 10

        self.setup_ui()

        self.load_timer = QTimer()
        self.load_timer.setSingleShot(True)
        self.load_timer.timeout.connect(self._process_visible_area)

        self.placeholder_cache = {}

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

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

        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(100, 300)
        self.size_slider.setValue(self.thumbnail_size)
        self.size_slider.setTickPosition(QSlider.TicksBelow)
        self.size_slider.setTickInterval(50)
        self.size_slider.valueChanged.connect(self.on_size_changed)

        self.thumbnail_list.itemClicked.connect(self._on_item_clicked)
        self.thumbnail_list.currentItemChanged.connect(self._on_current_item_changed)
        self.thumbnail_list.verticalScrollBar().valueChanged.connect(
            lambda: self.load_timer.start(SCROLL_DEBOUNCE_MS)
        )

        layout.addWidget(self.thumbnail_list)
        layout.addWidget(self.size_slider)

        self.setMinimumWidth(150)

    def set_document(self, document, doc_path: str, password: str = ""):
        self.manager.cancel_all()

        self.document = document
        self.doc_path = doc_path
        self.document_password = password
        self.page_rotations.clear()
        self.deleted_pages.clear()

        if document:
            try:
                total_pages = len(document)
                self.display_order = list(range(total_pages))

                # Initialize manager
                self.manager.set_document(doc_path, password, total_pages)
                self.manager.current_size = self.thumbnail_size

                for page_num, rotation in self.page_rotations.items():
                    self.manager.set_page_rotation(page_num, rotation)

                self._create_placeholder_items(total_pages)
                self.load_timer.start(300)

            except Exception as e:
                print(f"Error setting document: {e}")

    def _create_placeholder_items(self, total_pages: int):
        self.thumbnail_list.clear()

        for page_num in range(total_pages):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, page_num)
            item.setSizeHint(QSize(self.thumbnail_size + 12, self.thumbnail_size + 12))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

            placeholder = self._create_placeholder_with_number(page_num)
            item.setIcon(QIcon(placeholder))

            self.thumbnail_list.addItem(item)

        self._update_grid_size()

    def _create_placeholder_with_number(self, page_num: int) -> QPixmap:
        placeholder = QPixmap(self.thumbnail_size, self.thumbnail_size)
        placeholder.fill(Qt.white)

        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.Antialiasing)

        h = placeholder.height()
        bar_h = max(18, int(h * 0.14))
        painter.fillRect(0, h - bar_h, placeholder.width(), bar_h, QColor(0, 0, 0, 150))

        display_num = self._get_display_number(page_num)
        if display_num:
            f = painter.font()
            f.setBold(True)
            f.setPointSize(self.page_number_font_size)
            painter.setFont(f)
            painter.setPen(Qt.white)
            painter.drawText(placeholder.rect().adjusted(0, 0, 0, -2),
                             Qt.AlignHCenter | Qt.AlignBottom, str(display_num))
        painter.end()

        return placeholder

    def _get_display_number(self, page_num: int) -> Optional[int]:
        if page_num in self.deleted_pages:
            return None

        try:
            if page_num in self.display_order:
                return self.display_order.index(page_num) + 1
        except (ValueError, AttributeError):
            pass

        count = 1
        for i in range(page_num):
            if i not in self.deleted_pages:
                count += 1
        return count if page_num not in self.deleted_pages else None

    def clear_thumbnails(self):
        self.manager.cancel_all()
        self.thumbnail_list.clear()
        self.placeholder_cache.clear()

        self.document = None
        self.doc_path = ""
        self.document_password = ""
        self.display_order.clear()
        self.page_rotations.clear()
        self.deleted_pages.clear()

        self.manager.page_rotations.clear()

    def set_current_page(self, page_num: int):
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and item.data(Qt.UserRole) == page_num:
                self.thumbnail_list.setCurrentItem(item)
                self.thumbnail_list.scrollToItem(item)
                break

    def hide_page_thumbnail(self, page_num: int):
        self.deleted_pages.add(page_num)
        self.manager.remove_page(page_num)

        if page_num in self.page_rotations:
            del self.page_rotations[page_num]

        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and item.data(Qt.UserRole) == page_num:
                self.thumbnail_list.takeItem(i)
                break

        if page_num in self.display_order:
            self.display_order.remove(page_num)

    def rotate_page_thumbnail(self, page_num: int, rotation: int):
        current_rotation = self.page_rotations.get(page_num, 0)
        new_rotation = (current_rotation + rotation) % 360
        self.page_rotations[page_num] = new_rotation

        self.manager.set_page_rotation(page_num, new_rotation)

        # Remove from cache to force reload
        self.manager.remove_page(page_num)

        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and item.data(Qt.UserRole) == page_num:
                placeholder = self._create_placeholder_with_number(page_num)
                item.setIcon(QIcon(placeholder))
                break

        # Trigger reload with updated rotation
        self.load_timer.start(100)

    def update_thumbnails_order(self, visible_order: List[int]):
        self.display_order = visible_order.copy()
        self.thumbnail_list.clear()

        for page_num in visible_order:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, page_num)
            item.setSizeHint(QSize(self.thumbnail_size + 12, self.thumbnail_size + 12))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

            cached = self.manager.get_thumbnail(page_num)
            if cached:
                final_pixmap = self._add_page_number_overlay(cached, page_num)
                item.setIcon(QIcon(final_pixmap))
            else:
                placeholder = self._create_placeholder_with_number(page_num)
                item.setIcon(QIcon(placeholder))

            self.thumbnail_list.addItem(item)

        self.load_timer.start(50)

    def _add_page_number_overlay(self, pixmap: QPixmap, page_num: int) -> QPixmap:
        display_num = self._get_display_number(page_num)
        if not display_num:
            return pixmap

        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        h = result.height()
        bar_h = max(18, int(h * 0.14))
        painter.fillRect(0, h - bar_h, result.width(), bar_h, QColor(0, 0, 0, 150))

        f = painter.font()
        f.setBold(True)
        f.setPointSize(self.page_number_font_size)
        painter.setFont(f)
        painter.setPen(Qt.white)
        painter.drawText(result.rect().adjusted(0, 0, 0, -2),
                         Qt.AlignHCenter | Qt.AlignBottom, str(display_num))
        painter.end()

        return result

    def _process_visible_area(self):
        first_visible, last_visible = self._calculate_visible_indices()
        if first_visible is not None and last_visible is not None:
            self.manager.update_visible_range(first_visible, last_visible)

    def _calculate_visible_indices(self):
        viewport_rect = self.thumbnail_list.viewport().rect()
        first_visible = None
        last_visible = None

        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and not item.isHidden():
                item_rect = self.thumbnail_list.visualItemRect(item)
                if item_rect.intersects(viewport_rect):
                    if first_visible is None:
                        first_visible = i
                    last_visible = i

        return first_visible, last_visible

    def _on_thumbnail_loaded(self, page_num: int, qimage: QImage, thumb_size: int):
        if thumb_size != self.thumbnail_size:
            return

        pixmap = QPixmap.fromImage(qimage)
        final_pixmap = self._add_page_number_overlay(pixmap, page_num)

        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item and item.data(Qt.UserRole) == page_num:
                item.setIcon(QIcon(final_pixmap))
                break

    def on_size_changed(self, value):
        self.placeholder_cache.clear()

        if value == self.thumbnail_size:
            return

        self.thumbnail_size = value
        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))

        self.manager.current_size = value
        self.manager.cancel_all()

        self._update_grid_size()
        self._refresh_all_thumbnails()
        self.load_timer.start(200)

    def _update_grid_size(self):
        if self.thumbnail_list.count() == 0:
            return

        item_width = self.thumbnail_size + 12
        item_height = self.thumbnail_size + 12

        self.thumbnail_list.setGridSize(QSize(item_width, item_height))
        self.thumbnail_list.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))

        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item:
                item.setSizeHint(QSize(item_width, item_height))

    def _refresh_all_thumbnails(self):
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            if item:
                page_num = item.data(Qt.UserRole)
                cached = self.manager.get_thumbnail(page_num)
                if cached:
                    final_pixmap = self._add_page_number_overlay(cached, page_num)
                    item.setIcon(QIcon(final_pixmap))
                else:
                    placeholder = self._create_placeholder_with_number(page_num)
                    item.setIcon(QIcon(placeholder))

    def _on_item_clicked(self, item):
        if item:
            page_num = item.data(Qt.UserRole)
            if page_num is not None and page_num not in self.deleted_pages:
                self.page_clicked.emit(page_num)

    def _on_current_item_changed(self, current, previous):
        if current:
            page_num = current.data(Qt.UserRole)
            if page_num is not None and page_num not in self.deleted_pages:
                self.page_clicked.emit(page_num)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.load_timer.start(300)

    def showEvent(self, event):
        super().showEvent(event)
        if self.document:
            self.load_timer.start(200)

    def wheelEvent(self, event):
        super().wheelEvent(event)
        self.load_timer.start(300)
