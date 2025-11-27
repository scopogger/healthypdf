import gc
import os
import math
import threading
from typing import Optional, Dict, List
from collections import OrderedDict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSlider, QLabel, QScrollArea, QFrame,
    QInputDialog, QMessageBox, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRunnable, QThreadPool, QRect
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QFont, QMouseEvent, QPaintEvent, QPen

import fitz  # PyMuPDF


class ThumbnailCache:
    """LRU Cache for thumbnail images with size-aware storage"""

    def __init__(self, max_size: int = 20):
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
            # LRU eviction when cache exceeds max size
            while len(self.cache) > self.max_size:
                oldest = next(iter(self.cache))
                # Properly clean up the oldest pixmap
                oldest_pixmap = self.cache[oldest]
                if not oldest_pixmap.isNull():
                    oldest_pixmap = QPixmap()
                del self.cache[oldest]
                gc.collect()

    def clear(self):
        """Thoroughly clear all cached thumbnails"""
        keys_to_delete = list(self.cache.keys())
        for key in keys_to_delete:
            pixmap = self.cache[key]
            # Proper pixmap cleanup
            if not pixmap.isNull():
                # Force Qt to release the pixmap data
                self.cache[key] = QPixmap()
            del self.cache[key]
        self.cache.clear()
        gc.collect()

    def remove_page(self, page_num: int):
        """Remove all cached thumbnails for a specific page"""
        keys_to_remove = [key for key in self.cache.keys() if key[0] == page_num]
        for key in keys_to_remove:
            pixmap = self.cache[key]
            if not pixmap.isNull():
                pixmap = QPixmap()
            del self.cache[key]


class ThumbnailRenderWorker(QRunnable):
    """Worker for rendering thumbnails in background"""

    def __init__(self, doc_path: str, page_num: int, callback, render_id: str,
                 thumbnail_size: int = 100, rotation: int = 0, password: str = ""):
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

        doc = None
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

            # Close document and clean up PyMuPDF objects
            doc.close()
            doc = None

            # Force cleanup
            del pix
            del matrix
            del page

            if not self.cancelled:
                # Pass raw pixmap WITHOUT page number
                self.callback(self.page_num, pixmap, self.render_id, self.thumbnail_size)
            else:
                # Clean up pixmap if cancelled
                if not pixmap.isNull():
                    pixmap = QPixmap()

        except Exception as e:
            if not self.cancelled:
                print(f"Error rendering thumbnail {self.page_num}: {e}")
        finally:
            # Ensure document is always closed
            if doc is not None:
                try:
                    doc.close()
                except:
                    pass


class ThumbnailWidget(QWidget):
    """Individual thumbnail widget for a single page"""

    clicked = Signal(int)  # Emits original page number
    selected = Signal(int)  # Emits original page number when selected

    def __init__(self, page_info, layout_index: int, zoom: float = 1.0, parent=None):
        super().__init__(parent)
        self.page_info = page_info
        self.layout_index = layout_index
        self.zoom = zoom
        self.is_selected = False

        # Calculate size based on page dimensions and zoom
        self.base_width = page_info.width
        self.base_height = page_info.height
        self.thumbnail_size = int(max(self.base_width, self.base_height) * zoom)

        self.setFixedSize(self.thumbnail_size + 12, self.thumbnail_size + 12)
        self.setStyleSheet("""
            ThumbnailWidget {
                border: 2px solid transparent;
                border-radius: 6px;
                background-color: white;
            }
            ThumbnailWidget:hover {
                border: 2px solid #90caf9;
                background-color: #f0f8ff;
            }
            ThumbnailWidget:selected {
                border: 2px solid #0078d4;
                background-color: #e3f2fd;
            }
        """)

        # Thumbnail pixmap
        self.thumbnail_pixmap = None
        self.placeholder_pixmap = self._create_placeholder()

    def _create_placeholder(self) -> QPixmap:
        """Create a placeholder pixmap with page number"""
        pixmap = QPixmap(self.thumbnail_size, self.thumbnail_size)
        pixmap.fill(Qt.white)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw page border
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(0, 0, self.thumbnail_size - 1, self.thumbnail_size - 1)

        # Draw page number
        painter.setPen(QColor(100, 100, 100))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        # Calculate display number (1-based)
        display_num = self.layout_index + 1
        painter.drawText(pixmap.rect(), Qt.AlignCenter, str(display_num))
        painter.end()

        return pixmap

    def set_thumbnail(self, pixmap: QPixmap):
        """Set the thumbnail pixmap"""
        self.thumbnail_pixmap = pixmap
        self.update()

    def set_selected(self, selected: bool):
        """Set selection state"""
        self.is_selected = selected
        self.update()

    def paintEvent(self, event: QPaintEvent):
        """Paint the thumbnail"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw background based on state
        if self.is_selected:
            painter.fillRect(self.rect(), QColor(227, 242, 253))
        elif self.underMouse():
            painter.fillRect(self.rect(), QColor(240, 248, 255))
        else:
            painter.fillRect(self.rect(), QColor(248, 248, 248))

        # Draw border based on state
        border_rect = QRect(2, 2, self.width() - 4, self.height() - 4)
        if self.is_selected:
            painter.setPen(QPen(QColor(0, 120, 212), 2))
        elif self.underMouse():
            painter.setPen(QPen(QColor(144, 202, 249), 2))
        else:
            painter.setPen(QPen(QColor(200, 200, 200), 2))
        painter.drawRoundedRect(border_rect, 4, 4)

        # Draw thumbnail image centered
        thumb_rect = QRect(6, 6, self.thumbnail_size, self.thumbnail_size)
        if self.thumbnail_pixmap and not self.thumbnail_pixmap.isNull():
            # Scale pixmap to fit while maintaining aspect ratio
            scaled_pixmap = self.thumbnail_pixmap.scaled(
                self.thumbnail_size, self.thumbnail_size,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            # Center the pixmap
            x = thumb_rect.center().x() - scaled_pixmap.width() // 2
            y = thumb_rect.center().y() - scaled_pixmap.height() // 2
            painter.drawPixmap(x, y, scaled_pixmap)
        else:
            # Draw placeholder
            painter.drawPixmap(thumb_rect, self.placeholder_pixmap)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.page_info.page_num)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        """Handle mouse enter"""
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leave"""
        self.update()
        super().leaveEvent(event)


class ThumbnailContainer(QWidget):
    """Container widget that holds ThumbnailWidgetStack and handles scrolling"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Create container for thumbnails
        self.thumbnail_container = QWidget()
        self.thumbnail_stack = ThumbnailWidgetStack(self.thumbnail_container)

        self.scroll_area.setWidget(self.thumbnail_container)
        self.layout.addWidget(self.scroll_area)

        # Connect scroll signal
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_scroll(self, value):
        """Handle scroll events"""
        self.thumbnail_stack.handle_scroll(value)


class ThumbnailWidgetStack(QVBoxLayout):
    """Main thumbnail container using QVBoxLayout similar to PageWidgetStack"""

    page_clicked = Signal(int)  # Emits original page number

    def __init__(self, mainWidget: QWidget, spacing: int = 5, all_margins: int = 5, map_step: int = 10):
        super(ThumbnailWidgetStack, self).__init__(mainWidget)
        self.setSpacing(spacing)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.setContentsMargins(all_margins, all_margins, all_margins, all_margins)

        # Document and caching
        self.document = None
        self.doc_path = ""
        self.document_password = ""
        self.thumbnail_cache = ThumbnailCache(max_size=20)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)

        # Track active render tasks
        self.active_workers: Dict[str, ThumbnailRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # Page modifications tracking
        self.page_rotations = {}
        self.deleted_pages = set()

        # Thumbnail data
        self.pages_info: list = []  # List of PageInfo objects
        self.countTotalPagesInfo: int = 0
        self.thumbnail_widgets: list[ThumbnailWidget] = []

        # Layout management
        self.spacer: QSpacerItem = QSpacerItem(0, 0)
        self.isSpacer = False

        # Zoom and sizing
        self.zoom = 0.15  # Default thumbnail zoom factor
        self._map_step: int = map_step
        self._map_max: int = (self._map_step * 2) + 1
        self._map_size_tail = 3

        # Scroll tracking
        self.last_scroll_position = 0
        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self._on_scroll_timeout)

        # Visible tracking for lazy loading
        self.visible_thumbnails: OrderedDict[int, bool] = OrderedDict()
        self.max_visible_thumbnails = 20

        # Timer for delayed loading
        self.load_timer = QTimer()
        self.load_timer.setSingleShot(True)
        self.load_timer.timeout.connect(self.load_visible_thumbnails)

        # Current selection
        self.current_selected_widget = None

    def handle_scroll(self, scroll_position: int):
        """Handle scroll events - this is where needCalculateByScrollHeight is called"""
        self.last_scroll_position = scroll_position
        self.scroll_timer.start(50)  # Delay to avoid too frequent calculations

    def _on_scroll_timeout(self):
        """Process scroll after a short delay"""
        if self.needCalculateByScrollHeight(self.last_scroll_position):
            current_index = self.getCurrPageIndexByHeightScroll(self.last_scroll_position)
            if current_index >= 0:
                self.calculateMapPagesByIndex(current_index)

    def set_document(self, document, doc_path: str, password: str = ""):
        """Set the document to display thumbnails for"""
        self.cancel_all_renders()
        self.clear_thumbnails()

        self.document = document
        self.doc_path = doc_path
        self.document_password = password
        self.page_rotations.clear()
        self.deleted_pages.clear()
        self.visible_thumbnails.clear()

        if document:
            # Create page info list
            self.pages_info = []
            for page_num in range(len(document)):
                page = document[page_num]
                rect = page.rect
                page_info = type('PageInfo', (), {
                    'page_num': page_num,
                    'width': rect.width,
                    'height': rect.height,
                    'rotation': 0
                })()
                self.pages_info.append(page_info)

            self.countTotalPagesInfo = len(self.pages_info)

            # Initialize with first batch of thumbnails
            self.calculateMapPagesByIndex(0)

    def clear_thumbnails(self):
        """Clear all thumbnails and reset state"""
        self.cancel_all_renders()

        # Remove all widgets
        for widget in self.thumbnail_widgets:
            self.removeWidget(widget)
            widget.deleteLater()

        self.thumbnail_widgets.clear()

        # Clear cache
        self.thumbnail_cache.clear()

        # Clear data
        self.pages_info.clear()
        self.countTotalPagesInfo = 0
        self.deleted_pages.clear()
        self.page_rotations.clear()
        self.visible_thumbnails.clear()

        # Remove spacer
        if self.isSpacer:
            self.removeItem(self.spacer)
            self.isSpacer = False

        # Reset document references
        self.document = None
        self.doc_path = ""
        self.document_password = ""

        # Force garbage collection
        gc.collect()

    def cancel_all_renders(self):
        """Cancel all active rendering tasks"""
        with self.render_lock:
            for worker_id, worker in list(self.active_workers.items()):
                worker.cancel()
            self.active_workers.clear()
        self.thread_pool.waitForDone()

    def setZoom(self, newZoom):
        """Set zoom level for thumbnails"""
        self.zoom = newZoom

        # Update map step based on zoom
        if newZoom < 0.1:
            newStep = round(3.2 - 2.95 * math.log(newZoom))
        else:
            newStep = 3

        self._map_step = newStep + 3
        self._map_size_tail = newStep

        # Update all existing widgets
        for widget in self.thumbnail_widgets:
            page_info = self.pages_info[widget.layout_index]
            thumbnail_size = int(max(page_info.width, page_info.height) * self.zoom)
            widget.thumbnail_size = thumbnail_size
            widget.setFixedSize(thumbnail_size + 12, thumbnail_size + 12)
            widget.placeholder_pixmap = widget._create_placeholder()
            widget.update()

        # Reload thumbnails with new size
        self.load_timer.start(200)

    def getThumbnailWidgetByIndex(self, index: int) -> ThumbnailWidget:
        """Get thumbnail widget by layout index"""
        widgets = list(filter(lambda x: x.layout_index == index, self.thumbnail_widgets))
        if len(widgets) == 0:
            return None
        return widgets[0]

    def getPageInfoByIndex(self, index: int):
        """Get page info by index"""
        if 0 <= index < len(self.pages_info):
            return self.pages_info[index]
        return None

    def getTotalHeightByCountPages(self, count: int):
        """Calculate total height for given number of pages"""
        spacing = self.spacing()
        total_height = self.contentsMargins().top() + spacing

        for i in range(count):
            page_info = self.pages_info[i]
            thumb_height = int(max(page_info.width, page_info.height) * self.zoom) + 12
            total_height += thumb_height
            total_height += spacing

        if count == self.countTotalPagesInfo:
            total_height += self.contentsMargins().bottom()

        return total_height

    def getCurrPageIndexByHeightScroll(self, heightScroll):
        """Get current page index based on scroll height"""
        spacing = self.spacing()
        total_height = self.contentsMargins().top() + spacing

        for i in range(self.countTotalPagesInfo):
            page_info = self.pages_info[i]
            thumb_height = int(max(page_info.width, page_info.height) * self.zoom) + 12
            total_height += thumb_height
            total_height += spacing

            if heightScroll < total_height:
                return i

        if heightScroll > total_height:
            return self.countTotalPagesInfo - 1

        return -1

    def needCalculateByScrollHeight(self, scroll: int):
        """Check if we need to recalculate based on scroll position"""
        index = self.getCurrPageIndexByHeightScroll(scroll)
        if index == -1:
            return False

        widget = self.getThumbnailWidgetByIndex(index)
        if widget is None:
            return True

        indexInList = self.thumbnail_widgets.index(widget) if widget in self.thumbnail_widgets else -1
        if indexInList == -1:
            return False

        topTail = min(index - 1, self._map_size_tail) + 1
        bottomTail = len(self.thumbnail_widgets) - min(self._map_size_tail, self.countTotalPagesInfo - index)

        return not (topTail <= indexInList <= bottomTail)

    def calculateMapPagesByIndex(self, index: int):
        """Calculate which thumbnails to show based on current index"""
        if self.countTotalPagesInfo == 0:
            return

        map_pages = []
        cur_min = index - min(self._map_step, index)
        cur_max = index + min(self._map_step, self.countTotalPagesInfo - index - 1)

        try:
            # Create or get widgets for the current range
            for i in range(cur_min, cur_max + 1):
                if i in self.deleted_pages:
                    continue

                widget = self.getThumbnailWidgetByIndex(i)
                if widget:
                    map_pages.append(widget)
                else:
                    page_info = self.pages_info[i]
                    new_widget = ThumbnailWidget(
                        page_info,
                        i,
                        zoom=self.zoom
                    )
                    new_widget.clicked.connect(self._on_thumbnail_clicked)
                    map_pages.append(new_widget)

            # Find widgets to remove and add
            widgets_to_delete = list((set(self.thumbnail_widgets) - set(map_pages)))
            widgets_to_add = list((set(map_pages) - set(self.thumbnail_widgets)))

            # Remove old widgets
            for widget in widgets_to_delete:
                self.removeWidget(widget)
                self.thumbnail_widgets.remove(widget)
                widget.deleteLater()

            # Add new widgets
            for widget in widgets_to_add:
                self.thumbnail_widgets.append(widget)

                # Insert in correct position
                insert_index = 0
                for i, existing_widget in enumerate(self.thumbnail_widgets):
                    if existing_widget.layout_index > widget.layout_index:
                        insert_index = i
                        break
                    insert_index = i + 1

                if insert_index < len(self.thumbnail_widgets):
                    self.insertWidget(insert_index, widget)
                else:
                    self.addWidget(widget)

            # Update spacer
            if self.thumbnail_widgets and self.thumbnail_widgets[0].layout_index > 0:
                self.addSpacer(self.getTotalHeightByCountPages(self.thumbnail_widgets[0].layout_index))
            else:
                self.removeSpacer()

            # Load thumbnails for visible widgets
            self.load_timer.start(100)

        except Exception as e:
            print(f"Error calculating thumbnail map: {e}")

    def addSpacer(self, height):
        """Add spacer to layout"""
        try:
            if self.isSpacer:
                self.removeItem(self.spacer)
            self.spacer = QSpacerItem(0, height, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.insertSpacerItem(0, self.spacer)
            self.isSpacer = True
        except Exception as e:
            print(f"Error adding spacer: {e}")

    def removeSpacer(self):
        """Remove spacer from layout"""
        try:
            if not self.isSpacer:
                return
            self.removeItem(self.spacer)
            self.isSpacer = False
        except Exception as e:
            print(f"Error removing spacer: {e}")

    def load_visible_thumbnails(self):
        """Load thumbnails for currently visible widgets"""
        if not self.thumbnail_widgets:
            return

        # Update LRU tracking
        visible_pages = set()
        for widget in self.thumbnail_widgets:
            original_page = widget.page_info.page_num
            visible_pages.add(original_page)
            if original_page in self.visible_thumbnails:
                self.visible_thumbnails.move_to_end(original_page)
            else:
                self.visible_thumbnails[original_page] = True

        # LRU eviction
        while len(self.visible_thumbnails) > self.max_visible_thumbnails:
            oldest_page, _ = self.visible_thumbnails.popitem(last=False)
            self.thumbnail_cache.remove_page(oldest_page)

        # Load thumbnails for visible pages
        for original_page in visible_pages:
            self.load_thumbnail(original_page)

    def load_thumbnail(self, original_page_num: int):
        """Load thumbnail for specific page"""
        if original_page_num >= len(self.pages_info):
            return

        # Find the widget for this page
        widget = None
        for thumb_widget in self.thumbnail_widgets:
            if thumb_widget.page_info.page_num == original_page_num:
                widget = thumb_widget
                break

        if not widget:
            return

        # Check cache first
        thumbnail_size = int(max(widget.base_width, widget.base_height) * self.zoom)
        cached_raw = self.thumbnail_cache.get_raw(original_page_num, thumbnail_size)
        if cached_raw:
            widget.set_thumbnail(cached_raw)
            return

        # Generate unique render ID
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"thumb_{self.current_render_id}_{original_page_num}_{thumbnail_size}"

        # Get rotation for this page
        rotation = self.page_rotations.get(original_page_num, 0)

        # Create worker
        worker = ThumbnailRenderWorker(
            self.doc_path,
            original_page_num,
            self.on_thumbnail_rendered,
            render_id,
            thumbnail_size,
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

        # Store in cache
        self.thumbnail_cache.put_raw(original_page_num, size, raw_pixmap)

        # Update LRU tracking
        if original_page_num in self.visible_thumbnails:
            self.visible_thumbnails.move_to_end(original_page_num)

        # Find and update the widget
        for widget in self.thumbnail_widgets:
            if widget.page_info.page_num == original_page_num:
                widget.set_thumbnail(raw_pixmap)
                break

    def _on_thumbnail_clicked(self, original_page_num: int):
        """Handle thumbnail click"""
        # Clear previous selection
        if self.current_selected_widget:
            self.current_selected_widget.set_selected(False)

        # Set new selection
        for widget in self.thumbnail_widgets:
            if widget.page_info.page_num == original_page_num:
                widget.set_selected(True)
                self.current_selected_widget = widget
                break

        self.page_clicked.emit(original_page_num)

    def set_current_page(self, original_page_num: int):
        """Highlight the thumbnail for the given original page number"""
        # Clear previous selection
        if self.current_selected_widget:
            self.current_selected_widget.set_selected(False)

        # Set new selection
        for widget in self.thumbnail_widgets:
            if widget.page_info.page_num == original_page_num:
                widget.set_selected(True)
                self.current_selected_widget = widget

                # Ensure this thumbnail is in the current map
                if widget.layout_index not in [w.layout_index for w in self.thumbnail_widgets]:
                    self.calculateMapPagesByIndex(widget.layout_index)
                break

    def hide_page_thumbnail(self, original_page_num: int):
        """Hide thumbnail for deleted page"""
        self.deleted_pages.add(original_page_num)

        # Remove from cache and tracking
        self.thumbnail_cache.remove_page(original_page_num)
        self.visible_thumbnails.pop(original_page_num, None)

        # Remove widget if it exists
        widget_to_remove = None
        for widget in self.thumbnail_widgets:
            if widget.page_info.page_num == original_page_num:
                widget_to_remove = widget
                break

        if widget_to_remove:
            self.removeWidget(widget_to_remove)
            self.thumbnail_widgets.remove(widget_to_remove)
            widget_to_remove.deleteLater()

            # Recalculate layout
            if self.thumbnail_widgets:
                self.calculateMapPagesByIndex(self.thumbnail_widgets[0].layout_index)

    def rotate_page_thumbnail(self, original_page_num: int, rotation: int):
        """Rotate a page thumbnail and reload it"""
        current_rotation = self.page_rotations.get(original_page_num, 0)
        new_rotation = (current_rotation + rotation) % 360
        self.page_rotations[original_page_num] = new_rotation

        # Remove from cache to force reload
        self.thumbnail_cache.remove_page(original_page_num)
        self.visible_thumbnails.pop(original_page_num, None)

        # Reload the thumbnail
        QTimer.singleShot(100, lambda: self.load_thumbnail(original_page_num))

    def update_thumbnails_order(self, visible_order: List[int]):
        """Update display order and refresh all thumbnails"""
        # This would need to be implemented based on your specific reordering needs
        # For now, we'll just recalculate based on the first visible page
        if visible_order:
            self.calculateMapPagesByIndex(visible_order[0])
