import math
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QSpacerItem, QSizePolicy,
    QScrollArea, QFrame
)
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QMouseEvent, QPaintEvent
from PySide6.QtCore import Qt, QRect, QPoint, QBuffer, Signal, QSize, QTimer

from dataclasses import dataclass
import fitz  # PyMuPDF

from classes.document import Document


@dataclass
class ThumbnailInfo:
    """Information about a PDF thumbnail"""
    page_num: int  # original document page index
    width: float  # Store as float for precision
    height: float  # Store as float for precision
    rotation: int = 0


class ThumbnailWidget(QWidget):
    """Widget for displaying a single thumbnail"""
    clicked = Signal(int)

    def __init__(self, page, thumbnail_info: ThumbnailInfo, layout_index: int, zoom: float = 1.0):
        super().__init__()
        self.thumbnail_info = thumbnail_info
        self.layout_index = layout_index
        self.zoom = zoom
        self.page = page
        self.thumbnail_size = 100

        # Добавляем состояния
        self.is_selected = False
        self.is_hovered = False

        self.setFixedSize(self.thumbnail_size + 12, self.thumbnail_size + 12)
        self.setCursor(Qt.PointingHandCursor)

        # Включаем отслеживание мыши для hover эффекта
        self.setMouseTracking(True)

        # Thumbnail pixmap
        self.thumbnail_pixmap: Optional[QPixmap] = None
        self.is_loaded = False

    def set_selected(self, selected: bool):
        if self.is_selected != selected:
            self.is_selected = selected
            self.update()

    def enterEvent(self, event):
        """Курсор навёлся"""
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Курсор отвёлся"""
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Определяем цвета в зависимости от состояния
        if self.is_selected:
            border_color = QColor("#0078d4")
            background_color = QColor("#e3f2fd")
            border_width = 2
        elif self.is_hovered:
            border_color = QColor("#90caf9")
            background_color = QColor("#f0f8ff")
            border_width = 2
        else:
            border_color = QColor(200, 200, 200)
            background_color = QColor(240, 240, 240)
            border_width = 1

        # Рисуем фон с закругленными углами
        painter.setPen(Qt.NoPen)
        painter.setBrush(background_color)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

        # Рисуем белый прямоугольник для миниатюры
        content_rect = self.rect().adjusted(4, 4, -4, -4)
        painter.setBrush(Qt.white)
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(content_rect)

        if self.thumbnail_pixmap and not self.thumbnail_pixmap.isNull():
            # Center the thumbnail
            x = (self.width() - self.thumbnail_pixmap.width()) // 2
            y = (self.height() - self.thumbnail_pixmap.height()) // 2
            painter.drawPixmap(x, y, self.thumbnail_pixmap)
        else:
            # Draw placeholder
            painter.setPen(Qt.black)
            display_num = self.layout_index + 1
            f = painter.font()
            f.setBold(True)
            f.setPointSize(10)
            painter.setFont(f)
            painter.drawText(content_rect, Qt.AlignCenter, str(display_num))

        # Рисуем border в зависимости от состояния
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

    def load_thumbnail(self):
        """Load thumbnail from document"""
        if self.is_loaded:
            return
        try:
            page = self.page

            # Calculate scale for fixed thumbnail size
            rect = page.rect
            scale = min(self.thumbnail_size / rect.width, self.thumbnail_size / rect.height)
            matrix = fitz.Matrix(scale, scale)

            pix = page.get_pixmap(
                matrix=matrix,
                alpha=False,
                colorspace=fitz.csRGB
            )
            img_data = pix.tobytes("ppm")
            self.thumbnail_pixmap = QPixmap()
            self.thumbnail_pixmap.loadFromData(img_data)

            # Add page number overlay
            self._add_page_number_overlay()
            self.is_loaded = True

            # Trigger repaint
            self.update()

        except Exception as e:
            print(f"Error loading thumbnail for page {self.thumbnail_info.page_num}: {e}")

    def _add_page_number_overlay(self):
        """Add page number overlay to thumbnail"""
        if not self.thumbnail_pixmap:
            return

        # Create a copy to avoid modifying original
        result = QPixmap(self.thumbnail_pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw page number bar at bottom
        h = result.height()
        bar_h = max(14, int(h * 0.14))
        painter.fillRect(0, h - bar_h, result.width(), bar_h, QColor(0, 0, 0, 150))

        # Draw page number
        display_num = self.layout_index + 1
        f = painter.font()
        f.setBold(True)
        f.setPointSize(8)
        painter.setFont(f)
        painter.setPen(Qt.white)

        painter.drawText(result.rect().adjusted(0, 0, 0, -2),
                         Qt.AlignHCenter | Qt.AlignBottom,
                         str(display_num))

        painter.end()

        self.thumbnail_pixmap = result

    def paintEvent(self, event: QPaintEvent):
        """Paint the thumbnail widget"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw background
        painter.fillRect(self.rect(), QColor(240, 240, 240))

        if self.thumbnail_pixmap and not self.thumbnail_pixmap.isNull():
            # Center the thumbnail
            x = (self.width() - self.thumbnail_pixmap.width()) // 2
            y = (self.height() - self.thumbnail_pixmap.height()) // 2
            painter.drawPixmap(x, y, self.thumbnail_pixmap)
        else:
            # Draw placeholder
            painter.fillRect(self.rect().adjusted(2, 2, -2, -2), Qt.white)

            # Draw page number on placeholder
            display_num = self.layout_index + 1
            f = painter.font()
            f.setBold(True)
            f.setPointSize(10)
            painter.setFont(f)
            painter.setPen(Qt.black)
            painter.drawText(self.rect(), Qt.AlignCenter, str(display_num))

        # Draw border
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse clicks"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.thumbnail_info.page_num)
            event.accept()

    def clean(self):
        """Clean up resources"""
        if self.thumbnail_pixmap:
            self.thumbnail_pixmap = QPixmap()
        self.is_loaded = False


class ThumbnailWidgetStack(QVBoxLayout):
    page_clicked = Signal(int)

    def __init__(self, mainWidget: QWidget, spacing: int = 5, all_margins: int = 5, map_step: int = 20):
        super().__init__(mainWidget)
        self.setSpacing(spacing)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.setContentsMargins(all_margins, all_margins, all_margins, all_margins)

        self.thumbnails_info: List[ThumbnailInfo] = []
        self.countTotalThumbnailsInfo: int = 0

        self.thumbnail_widgets: List[ThumbnailWidget] = []
        self.zoom = 1.0  # Fixed for thumbnails
        self.spacer: QSpacerItem = QSpacerItem(0, 0)
        self.isSpacer = False

        self._map_step: int = map_step
        self._map_max: int = (self._map_step * 2) + 1
        self._map_size_tail = 10

        # Document info for loading thumbnails
        self.doc_path = ""
        self.document_password = ""
        # Track loaded thumbnails
        self.loaded_thumbnails = set()
        self.current_doc: Document = None

        self.current_selected_widget: Optional[ThumbnailWidget] = None

    def set_document_stack(self, document: Document):
        """Set the document to display thumbnails for"""
        self.clear()

        self.current_doc = document

        if self.current_doc:
            # Create thumbnail info for all pages
            thumbnails_info = []
            for page_num in range(document.get_page_count()):
                page = document.get_page(page_num)
                rect = page.rect
                thumbnail_info = ThumbnailInfo(
                    page_num=page_num,
                    width=rect.width,
                    height=rect.height
                )
                thumbnails_info.append(thumbnail_info)

            self.initThumbnailInfoList(thumbnails_info)

            # Load initial thumbnails
            self.calculateMapPagesByIndex(0)

    def setZoom(self, newZoom):
        """Thumbnails use fixed size, but keep for compatibility"""
        self.zoom = newZoom

        if newZoom < 1:
            newStep = round(3.2 - 2.95 * math.log(newZoom))
        else:
            newStep = 3

        self._map_step = newStep + 3
        self._map_size_tail = newStep

    def initThumbnailInfoList(self, thumbnails_info: List[ThumbnailInfo]):
        self.thumbnails_info = thumbnails_info
        self.countTotalThumbnailsInfo = len(self.thumbnails_info)

    def addThumbnailWidget(self, thumbnailWidget: ThumbnailWidget, addLayout: bool = True):
        try:
            self.thumbnail_widgets.append(thumbnailWidget)
            if addLayout:
                self.addWidget(thumbnailWidget)
        except Exception as e:
            raise Exception(f"Error adding thumbnail: {e}")

    def insertThumbnailWidget(self, index: int, widget: ThumbnailWidget):
        try:
            self.thumbnail_widgets.insert(index, widget)
            if self.isSpacer:
                index += 1
            self.insertWidget(index, widget)
        except Exception as e:
            raise Exception(f"Error inserting thumbnail: {e}")

    def removeThumbnailWidget(self, thumbnailWidget: ThumbnailWidget):
        try:
            self.thumbnail_widgets.remove(thumbnailWidget)
            self.removeWidget(thumbnailWidget)
            thumbnailWidget.clean()
            thumbnailWidget.deleteLater()
        except Exception as e:
            raise Exception(f"Error removing thumbnail: {e}")

    def addThumbnailWidgetByIndexInLayout(self, index: int):
        try:
            widget = list(filter(lambda x: x.layout_index == index, self.thumbnail_widgets))
            if len(widget) == 0:
                raise Exception(f"ThumbnailWidget with layout_index not found")
            self.addWidget(widget[0])
        except Exception as e:
            raise Exception(f"Error adding to Layout: {e}")

    def addSpacer(self, height):
        try:
            if self.isSpacer:
                self.removeItem(self.spacer)
            self.spacer = QSpacerItem(0, height, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.insertSpacerItem(0, self.spacer)
            self.isSpacer = True
        except Exception as e:
            raise Exception(f"Error adding spacer: {e}")

    def removeSpacer(self):
        try:
            if not self.isSpacer:
                return
            self.removeItem(self.spacer)
            self.isSpacer = False
        except Exception as e:
            raise Exception(f"Error removing spacer: {e}")

    def updateSpacerWithZoom(self):
        self.addSpacer(self.getTotalHeightByCountThumbnails(self.thumbnail_widgets[0].layout_index))

    def getLastThumbnailWidget(self) -> ThumbnailWidget:
        return self.thumbnail_widgets[-1:][0]

    def getFirstThumbnailWidget(self) -> ThumbnailWidget:
        return self.thumbnail_widgets[0]

    def getThumbnailWidgetByIndex(self, index: int) -> ThumbnailWidget:
        widgets = list(filter(lambda x: x.layout_index == index, self.thumbnail_widgets))
        if len(widgets) == 0:
            return None
        return widgets[0]

    def getThumbnailInfoByIndex(self, index: int) -> ThumbnailInfo:
        return self.thumbnails_info[index]

    def getTotalHeightByCountThumbnails(self, count: int):
        spacing = self.spacing()
        total_height = self.contentsMargins().top() + spacing

        # Fixed thumbnail size (100px + 12px padding)
        thumbnail_height = 112

        for i in range(count):
            total_height += thumbnail_height
            total_height += spacing

        if count == self.countTotalThumbnailsInfo:
            total_height += self.contentsMargins().bottom()

        return total_height

    def getCurrThumbnailIndexByHeightScroll(self, heightScroll):
        spacing = self.spacing()
        total_height = self.contentsMargins().top() + spacing

        # Fixed thumbnail size
        thumbnail_height = 112

        for i in range(self.countTotalThumbnailsInfo):
            total_height += thumbnail_height
            total_height += spacing

            if heightScroll < total_height:
                return i

        if heightScroll > total_height:
            return self.countTotalThumbnailsInfo - 1

        return -1

    def needCalculateByScrollHeight(self, scroll: int):
        index = self.getCurrThumbnailIndexByHeightScroll(scroll)

        widget = self.getThumbnailWidgetByIndex(index)

        if widget is None:
            return True

        indexInList = self.thumbnail_widgets.index(widget)

        if indexInList == -1:
            return False

        topTail = min(index - 1, self._map_size_tail) + 1
        bottomTail = len(self.thumbnail_widgets) - min(self._map_size_tail, self.countTotalThumbnailsInfo - index)

        if not topTail <= indexInList <= bottomTail:
            return True
        return False

    def calculateMapPagesByIndex(self, index: int):
        """Calculate and update which thumbnails to display"""
        map_thumbnails = []
        cur_min = index - min(self._map_step, index)
        cur_max = index + min(self._map_step, self.countTotalThumbnailsInfo - index - 1)

        if self.countTotalThumbnailsInfo == 0:
            raise Exception(f"ThumbnailInfo not initialized")

        try:
            for i in range(cur_min, cur_max + 1):
                widget = list(filter(lambda x: x.layout_index == i, self.thumbnail_widgets))

                if widget:
                    map_thumbnails.append(widget[0])
                else:
                    thumbnail_info_i = self.thumbnails_info[i]
                    newWidget = ThumbnailWidget(
                        self.current_doc.get_page(thumbnail_info_i.page_num),
                        thumbnail_info_i,
                        i,
                        zoom=self.zoom
                    )
                    # Connect click signal
                    newWidget.clicked.connect(self._on_thumbnail_clicked)
                    map_thumbnails.append(newWidget)

            # Find thumbnails to remove and add
            thumbnails_for_delete = list(
                (set(self.thumbnail_widgets) ^ set(map_thumbnails)) & set(self.thumbnail_widgets))
            thumbnails_for_add = list((set(self.thumbnail_widgets) ^ set(map_thumbnails)) & set(map_thumbnails))

            thumbnails_for_delete.sort(key=lambda x: x.layout_index)
            thumbnails_for_add.sort(key=lambda x: x.layout_index)

            # Remove old thumbnails
            for widget in thumbnails_for_delete:
                self.removeThumbnailWidget(widget)

            # Add new thumbnails
            indexFirst = self.thumbnail_widgets[0].layout_index if len(self.thumbnail_widgets) > 0 else -1
            thumbnails_for_add.reverse()

            lastIndex = len(self.thumbnail_widgets)

            for widget in thumbnails_for_add:
                if indexFirst < widget.layout_index:
                    insertIndex = lastIndex
                else:
                    insertIndex = 0

                self.insertThumbnailWidget(insertIndex, widget)

            # Update spacer
            if self.thumbnail_widgets and self.thumbnail_widgets[0].layout_index > 0:
                self.addSpacer(self.getTotalHeightByCountThumbnails(self.thumbnail_widgets[0].layout_index))
            else:
                self.removeSpacer()

            for th in self.thumbnail_widgets:
                th.load_thumbnail()

        except Exception as e:
            raise Exception(f"Error calculating thumbnail map: {e}")

    def _on_thumbnail_clicked(self, page_num: int):
        """Обработчик клика по миниатюре"""
        self.set_current_page(page_num)
        self.page_clicked.emit(page_num)

    def set_current_page(self, page_num: int):
        """Highlight the thumbnail for the given page number"""
        # Снимаем выделение с предыдущего виджета
        if self.current_selected_widget:
            self.current_selected_widget.set_selected(False)

        # Находим и выделяем новый виджет
        for widget in self.thumbnail_widgets:
            if widget.thumbnail_info.page_num == page_num:
                widget.set_selected(True)
                self.current_selected_widget = widget
                break
        else:
            self.current_selected_widget = None

    def rotate_page_thumbnail(self, page_num: int, rotation: int):
        """Rotate a page thumbnail"""
        # Find thumbnail info and update rotation
        for thumb_info in self.thumbnails_info:
            if thumb_info.page_num == page_num:
                current_rotation = thumb_info.rotation
                new_rotation = (current_rotation + rotation) % 360
                thumb_info.rotation = new_rotation
                break

        # Reload thumbnail
        for widget in self.thumbnail_widgets:
            if widget.thumbnail_info.page_num == page_num:
                widget.thumbnail_info.rotation = new_rotation
                widget.is_loaded = False
                if self.doc_path:
                    widget.load_thumbnail()
                break

    def update_thumbnails_order(self, visible_order: List[int]):
        """Update display order of thumbnails"""
        # Recreate thumbnail info in new order
        new_thumbnails_info = []
        for display_index, original_page in enumerate(visible_order):
            if original_page < len(self.thumbnails_info):
                thumb_info = self.thumbnails_info[original_page]
                # Create new thumbnail info with updated display position
                new_thumb_info = ThumbnailInfo(
                    page_num=thumb_info.page_num,
                    width=thumb_info.width,
                    height=thumb_info.height,
                    rotation=thumb_info.rotation
                )
                new_thumbnails_info.append(new_thumb_info)

        self.thumbnails_info = new_thumbnails_info
        self.countTotalThumbnailsInfo = len(self.thumbnails_info)

        # Clear current widgets and recalculate map
        for widget in self.thumbnail_widgets[:]:
            self.removeThumbnailWidget(widget)

        self.calculateMapPagesByIndex(0)

    def clear(self):
        """Clear all thumbnails"""
        self.countTotalThumbnailsInfo = 0
        self.thumbnails_info = []
        for widget in self.thumbnail_widgets:
            self.removeThumbnailWidget(widget)
            widget.clean()
            widget.deleteLater()

        if self.isSpacer:
            self.removeSpacer()

        self.zoom = 1.0
        self.doc_path = ""
        self.document_password = ""
        self.loaded_thumbnails.clear()


# Container widget for the thumbnail stack
class ThumbnailContainerWidget(QScrollArea):
    """Container widget that holds the ThumbnailWidgetStack"""

    page_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create scroll area
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Create container widget for thumbnails
        self.container_widget = QWidget()
        self.thumbnail_stack = ThumbnailWidgetStack(self.container_widget)

        # Connect signals
        self.thumbnail_stack.page_clicked.connect(self.page_clicked.emit)

        self.container_widget.setLayout(self.thumbnail_stack)
        self.setWidget(self.container_widget)

        # Connect scroll to update thumbnails
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.document: Document = None

        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.calculate_in_need)

        # self.container_widget.setMinimumHeight(2000)  # For testing the scrolling

    def _on_scroll(self):
        """Handle scroll events to update visible thumbnails"""
        self.scroll_timer.start(200)

    def calculate_in_need(self):
        value = self.verticalScrollBar().value()

        if self.thumbnail_stack.needCalculateByScrollHeight(value):
            index = self.thumbnail_stack.getCurrThumbnailIndexByHeightScroll(value)
            if index >= 0:
                self.thumbnail_stack.calculateMapPagesByIndex(index)

    def set_document(self, document):
        """Set the document to display thumbnails for"""
        self.document = document
        self.thumbnail_stack.set_document_stack(document)
        self.container_widget.setMinimumHeight(
            self.thumbnail_stack.getTotalHeightByCountThumbnails(self.thumbnail_stack.countTotalThumbnailsInfo))
        self.container_widget.adjustSize()

    def set_current_page(self, page_num: int):
        """Highlight the thumbnail for the given page number"""
        self.thumbnail_stack.set_current_page(page_num)

    def rotate_page_thumbnail(self, page_num: int, rotation: int):
        """Rotate a page thumbnail"""
        self.thumbnail_stack.rotate_page_thumbnail(page_num, rotation)

    def update_thumbnails_order(self, visible_order: List[int]):
        """Update display order of thumbnails"""
        self.thumbnail_stack.update_thumbnails_order(visible_order)

    def clear(self):
        """Clear all thumbnails"""
        self.thumbnail_stack.clear()
