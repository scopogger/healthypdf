import math
import threading

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSpacerItem, QSizePolicy
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QMouseEvent, QPaintEvent
from PySide6.QtCore import Qt, QRect, QPoint, QBuffer, Signal, QSize

from dataclasses import dataclass
import fitz  # PyMuPDF
from fitz import Page

from drawing_overlay import PageWidget


@dataclass
class PageInfo:
    """Information about a PDF page"""
    page_num: int  # original document page index
    width: float  # Store as float for precision
    height: float  # Store as float for precision
    rotation: int = 0


class Document:
    def __init__(self, file_path: str = None):
        self.file_path = file_path
        try:
            self.current_doc = fitz.open(file_path)
        except Exception as e:
            print(f"Error open document: {e}")

    def auth(self, password: str):
        if not self.current_doc.authenticate(password):
            self.close()

    def get_page_count(self) -> int:
        return self.current_doc.page_count

    def get_page(self, num: int):
        try:
            return self.current_doc[num]
        except Exception as e:
            print(f"Error get page: {e}")

    def get_page_info(self, num_page: int) -> PageInfo:
        w, h = self.get_page_size(num_page)
        result = PageInfo(
            page_num=num_page,
            width=w,
            height=h,
        )
        return result

    def get_page_size(self, num_page: int) -> tuple:
        if not 0 <= num_page < self.current_doc.page_count:
            raise IndexError(f'Page number {num_page} is out of range [0, {self.current_doc.page_count - 1}]')

        page = self.current_doc[num_page]
        rect = page.rect
        return rect.width, rect.height

    def need_auth(self) -> bool:
        return self.current_doc.needs_pass

    def new_page(self, in_width: float, in_height: float) -> Page:
        if self.current_doc:
            return self.current_doc.new_page(width=in_width, height=in_height)

    def save(self, file_path: str):
        if self.current_doc:
            self.current_doc.save(file_path)

    def close(self):
        if self.current_doc:
            self.current_doc.close()


class PageWidgetStack(QVBoxLayout):
    def __init__(self, mainWidget: QWidget, spacing: int = 10, all_margins: int = 10, map_step: int = 10):
        super(PageWidgetStack, self).__init__(mainWidget)
        self.setSpacing(spacing)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.setContentsMargins(all_margins, all_margins, all_margins, all_margins)

        self.pages_info: list[PageInfo] = []
        self.countTotalPagesInfo: int = 0

        self.page_widgets: list[PageWidget] = []
        self.zoom = 1.0
        self.spacer: QSpacerItem = QSpacerItem(0, 0)
        self.isSpacer = False


        self._map_step: int = map_step
        self._map_max: int = (self._map_step * 2) + 1
        self._map_size_tail = 3

    def __getItem__(self, item) -> PageWidget:
        return self.page_widgets[item]

    def setZoom(self, newZoom):
        self.zoom = newZoom

        if newZoom < 1:
            newStep = round(3.2 - 2.95 * math.log(newZoom))
        else:
            newStep = 3

        self._map_step = newStep + 3
        self._map_size_tail = newStep



    def initPageInfoList(self, pages_info: list[PageInfo]):
        self.pages_info = pages_info
        self.countTotalPagesInfo = len(self.pages_info)

    def addPageWidget(self, pageWidget: PageWidget, addLayout: bool = True):
        try:
            self.page_widgets.append(pageWidget)
            if addLayout:
                self.addWidget(pageWidget)
        except Exception as e:
            raise Exception(f"Ошибка при добавлении страницы: {e}")

    def insertPageWidget(self, index: int, widget: PageWidget):
        try:
            self.page_widgets.insert(index, widget)
            if self.isSpacer:
                index += 1
            self.insertWidget(index, widget)
        except Exception as e:
            raise Exception(f"Ошибка при вставке страницы: {e}")

    def removePageWidget(self, pageWidget: PageWidget):
        try:
            self.page_widgets.remove(pageWidget)
            self.removeWidget(pageWidget)
            pageWidget.deleteLater()
        except Exception as e:
            raise Exception(f"Ошибка при удалении страницы: {e}")

    def addPageWidgetByIndexInLayout(self, index: int):
        try:
            widget = list(filter(lambda x: x.layout_index == index, self.page_widgets))
            if len(widget) == 0:
                raise Exception(f"PageWidget с таким layout_index не найден")
            self.addWidget(widget[0])
        except Exception as e:
            raise Exception(f"Ошибка при добавлении в Layout: {e}")

    def addSpacer(self, height):
        try:
            if self.isSpacer:
                self.removeItem(self.spacer)
            self.spacer = QSpacerItem(0, height, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.insertSpacerItem(0, self.spacer)
            self.isSpacer = True

        except Exception as e:
            raise Exception(f"Ошибка при добавлении пространства: {e}")

    def removeSpacer(self):
        try:
            if not self.isSpacer:
                return
            self.removeItem(self.spacer)
            self.isSpacer = False
        except Exception as e:
            raise Exception(f"Ошибка при удалении пространства: {e}")

    def updateSpacerWithZoom(self):
        self.addSpacer(self.getTotalHeightByCountPages(self.page_widgets[0].layout_index))

    def getLastPageWidget(self) -> PageWidget:
        return self.page_widgets[-1:][0]

    def getFirstPageWidget(self) -> PageWidget:
        return self.page_widgets[0]

    def getPageWidgetByIndex(self, index: int) -> PageWidget:
        widgets = list(filter(lambda x: x.layout_index == index, self.page_widgets))
        if len(widgets) == 0:
            return None
        return widgets[0]

    def getPageInfoByIndex(self, index: int) -> PageInfo:
        return self.pages_info[index]

    def getTotalHeightByCountPages(self, count: int):
        spacing = self.spacing()
        total_height = self.contentsMargins().top() + spacing
        zoom = self.zoom

        for i in range(count):
            total_height += self.pages_info[i].height * zoom
            total_height += spacing

        if count == self.countTotalPagesInfo:
            total_height += self.contentsMargins().bottom()

        return total_height

    def getCurrPageIndexByHeightScroll(self, heightScroll):
        spacing = self.spacing()
        total_height = self.contentsMargins().top() + spacing
        zoom = self.zoom

        for i in range(self.countTotalPagesInfo):
            total_height += self.pages_info[i].height * zoom
            total_height += spacing

            if heightScroll < total_height:
                return i

        if heightScroll > total_height:
            return self.countTotalPagesInfo - 1

        return -1

    def needCalculateByScrollHeight(self, scroll: int):
        index = self.getCurrPageIndexByHeightScroll(scroll)

        widget = self.getPageWidgetByIndex(index)



        if widget is None:
            return True

        indexInList = self.page_widgets.index(widget)



        if indexInList == -1:
            return False



        topTail = min(index - 1, self._map_size_tail) + 1
        bottomTail = len(self.page_widgets) - min(self._map_size_tail, self.countTotalPagesInfo - index)



        if not topTail <= indexInList <= bottomTail:

            return True

        return False

    def calculateMapPagesByIndex(self, index: int):
        map_pages = []

        cur_min = index - min(self._map_step, index)
        cur_max = index + min(self._map_step, self.countTotalPagesInfo - index - 1)

        if self.countTotalPagesInfo == 0:
            raise Exception(f"PageInfo не инициализирован")

        try:

            for i in range(cur_min, cur_max + 1):

                widget = list(filter(lambda x: x.layout_index == i, self.page_widgets))

                if widget:
                    map_pages.append(widget[0])
                else:
                    page_info_i = self.pages_info[i]
                    newWidget = PageWidget(
                        page_info_i,
                        i,
                        zoom=self.zoom
                    )

                    map_pages.append(newWidget)




            widget_for_delete = list((set(self.page_widgets) ^ set(map_pages)) & set(self.page_widgets))
            widget_for_add = list((set(self.page_widgets) ^ set(map_pages)) & set(map_pages))

            widget_for_delete.sort(key=lambda x: x.layout_index)
            widget_for_add.sort(key=lambda x: x.layout_index)

            for widget in widget_for_delete:
                self.removePageWidget(widget)

            indexFirst = self.page_widgets[0].layout_index if len(self.page_widgets) > 0 else -1
            widget_for_add.reverse()

            lastIndex = len(self.page_widgets)

            for widget in widget_for_add:
                if indexFirst < widget.layout_index:
                    insertIndex = lastIndex
                else:
                    insertIndex = 0

                self.insertPageWidget(insertIndex, widget)

            if self.page_widgets[0].layout_index > 0:
                self.addSpacer(self.getTotalHeightByCountPages(self.page_widgets[0].layout_index))
            else:
                self.removeSpacer()

        except Exception as e:
            raise Exception(f"Ошибка расчёта карты страниц: {e}")

    def clear(self):
        self.countTotalPagesInfo = 0
        self.pages_info = []

        for widget in self.page_widgets:
            self.removePageWidget(widget)
            widget.clean_base()
            widget.clean()
            widget.deleteLater()

        if self.isSpacer:
            self.removeSpacer()

        self.zoom = 1.0
