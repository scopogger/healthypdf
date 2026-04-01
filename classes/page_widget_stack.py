import gc
import math

from PySide6.QtWidgets import QWidget, QVBoxLayout, QSpacerItem, QSizePolicy
from PySide6.QtCore import Qt, Signal

from classes.document import PageInfo
from classes.vector_manager import VectorManager
from classes.page_widget import PageWidget
from classes.mapPage import MapPage


class PageWidgetStack(QVBoxLayout):

    pagePainted = Signal()

    def __init__(self, mainWidget: QWidget, spacing: int = 10, all_margins: int = 10, map_step: int = 10):
        super(PageWidgetStack, self).__init__(mainWidget)
        # super().__init__(mainWidget)

        self.dict_vectors = VectorManager()

        self.setSpacing(spacing)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        # self.set

        self.setContentsMargins(all_margins, all_margins, all_margins, all_margins)

        self.pages_info: list[PageInfo] = []
        self.countTotalPagesInfo: int = 0

        self.page_widgets: list[PageWidget] = []
        self.zoom = 1.0
        self.spacer: QSpacerItem = QSpacerItem(0, 0)
        self.isSpacer = False

        # self._map_pages: list[list[int]] = list(list)
        # self._map_step: int = map_step
        # # self._map_max: int = (self._map_step * 2) + 1
        # self._map_size_tail = 3

        self.map_page = MapPage(map_step, 3)

        self.rotation_view_deg = 0
        self.chunks = [[0, 0]]
        self.current_chunk_index = 0
        self.MAX_HEIGHT_CHUNK = 16000000

    def __getitem__(self, item) -> PageWidget:
        return self.page_widgets[item]

    def _build_chunks(self, total_height: int = -1):
        self.chunks.clear()
        self.chunks = []
        # TODO 24.12.2025 - переработать момент с чисткой
        # if aggr_clean:
        # self.clearWidgets()
        if total_height == -1:
            total_height = self.getTotalHeightByCountPages(self.countTotalPagesInfo)
        count_chunks = int(total_height // self.MAX_HEIGHT_CHUNK) + 1
        if count_chunks <= 1:
            self.chunks.append([0, self.countTotalPagesInfo - 1])
        else:
            # TODO 24.12.2025 - идея - чистка ПРИ наличии доп чанков, см ниже
            self.clearWidgets()
            left_index = 0
            for i in range(count_chunks):
                right_index = self.getCurrPageIndexByHeightScroll(self.MAX_HEIGHT_CHUNK * (i + 1), False)
                if left_index > right_index:
                    return
                self.chunks.append([left_index, right_index])
                left_index = right_index

    def getChunkByScroll(self, scroll: int) -> int:
        page_index = self.getCurrPageIndexByHeightScroll(scroll)
        return self.getChunkByPageIndex(page_index)

    def getChunkByPageIndex(self, page_index):
        for i, chunk in enumerate(self.chunks):
            if chunk[0] <= page_index <= chunk[1]:
                return i
        return len(self.chunks)

    def setCurrentChunkByScroll(self, scroll):
        new_current_chunk = self.getChunkByScroll(scroll)
        self.current_chunk_index = new_current_chunk

    def setCurrentChunkByPageIndex(self, page_index):
        new_current_chunk = self.getChunkByPageIndex(page_index)
        self.current_chunk_index = new_current_chunk

    def setCurrentChunk(self, new_current_chunk):
        if 0 <= new_current_chunk <= len(self.chunks) - 1 and new_current_chunk != self.current_chunk_index:
            self.current_chunk_index = new_current_chunk

    def nextChunk(self):
        if self.current_chunk_index == len(self.chunks) - 1:
            return
        self.current_chunk_index += 1

    def prevChunk(self):
        if self.current_chunk_index == 0:
            return
        self.current_chunk_index -= 1

    def isLastChunk(self):
        return self.current_chunk_index == len(self.chunks) - 1

    def isFirstChunk(self):
        return self.current_chunk_index == 0

    def setZoom(self, newZoom):
        self.zoom = newZoom

        if newZoom < 1:
            newStep = round(3.2 - 2.95 * math.log(newZoom))
        else:
            newStep = 3

        # self._map_step = newStep + 3
        # self._map_size_tail = newStep
        self.map_page.update(newStep)

        self.updateSpacerWithZoom()
        self._build_chunks()

    def setRotationView(self, deg):
        self.rotation_view_deg = deg

    def initPageInfoList(self, pages_info: list[PageInfo]):
        self.pages_info = pages_info
        self.countTotalPagesInfo = len(self.pages_info)
        self._build_chunks()

    def addPageWidget(self, pageWidget: PageWidget, addLayout: bool = True):
        try:
            self.page_widgets.append(pageWidget)
            if addLayout:
                self.addWidget(pageWidget, 0, Qt.AlignmentFlag.AlignHCenter)
        except Exception as e:
            raise Exception(f"Ошибка при добавлении страницы: {e}")

    def insertPageWidget(self, index: int, widget: PageWidget):
        try:
            self.page_widgets.insert(index, widget)
            if self.isSpacer:
                index += 1
            self.insertWidget(index, widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        except Exception as e:
            raise Exception(f"Ошибка при вставке страницы: {e}")

    def removePageWidget(self, pageWidget: PageWidget):
        try:
            self.page_widgets.remove(pageWidget)
            self.removeWidget(pageWidget)
            pageWidget.clear_base()
            pageWidget.clear()
            pageWidget.deleteLater()
        except Exception as e:
            raise Exception(f"Ошибка при удалении страницы: {e}")

    def addPageWidgetByIndexInLayout(self, index: int):
        try:
            widget = list(filter(lambda x: x.layout_index == index, self.page_widgets))
            if len(widget):
                raise Exception(f"PageWidget с таким layout_index не найден")
            self.addWidget(widget[0])
        except Exception as e:
            raise Exception(f"Ошиька при добавлении в Layout: {e}")

    def addSpacer(self, height):
        try:
            if self.isSpacer:
                self.removeItem(self.spacer)
            self.spacer = QSpacerItem(0, height, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.insertSpacerItem(0, self.spacer)
            self.isSpacer = True
            print(f"Added spacer height: {height}")
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
        if len(self.page_widgets) > 0:
            self.addSpacer(self.getTotalHeightByCountPages(self.page_widgets[0].layout_index, True))

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

    def getTotalHeightByCountPages(self, count: int, withChunk: bool = False):
        spacing = self.spacing()
        total_height = self.contentsMargins().top() + spacing
        zoom = self.zoom

        start_range = self.chunks[self.current_chunk_index][0] if withChunk else 0

        # print(f"Chunks: {self.chunks}")
        # print(f"Start {start_range}, count {count}")

        for i in range(start_range, count):
            height = self.pages_info[i].width if abs(self.rotation_view_deg) == 90 else self.pages_info[i].height
            total_height += (height * zoom + 0.5)
            total_height += spacing

        if count == self.countTotalPagesInfo:
            total_height += self.contentsMargins().bottom()

        # print(f"TH: {total_height}")
        return total_height

    def getCurrPageIndexByHeightScroll(self, heightScroll, withChunk: bool = True):
        spacing = self.spacing()
        total_height = self.contentsMargins().top() + spacing
        zoom = self.zoom

        print(f"Current Chunk Index: {self.current_chunk_index}")

        heightScrollWithChunk = heightScroll + \
                                self.MAX_HEIGHT_CHUNK * self.current_chunk_index - 1 \
            if self.current_chunk_index > 0 and withChunk \
            else heightScroll

        print(f"HSWC: {heightScrollWithChunk}; ")

        for i in range(self.countTotalPagesInfo):
            height = self.pages_info[i].width if abs(self.rotation_view_deg) == 90 else self.pages_info[i].height
            total_height += (height * zoom + 0.5)
            total_height += spacing

            if heightScrollWithChunk < total_height:
                return i

        if heightScrollWithChunk > total_height:
            return self.countTotalPagesInfo - 1

        return -1

    def needCalculateByScrollHeight(self, scroll: int):
        index = self.getCurrPageIndexByHeightScroll(scroll)

        print(f"index: {index} in scroll: {scroll}")

        widget = self.getPageWidgetByIndex(index)

        if widget is None:
            return True

        indexInList = self.page_widgets.index(widget)

        print(f"index in List: {indexInList}")

        if indexInList == -1:
            return False

        # print(f"{self._map_size_tail} >= {indexInList} or {indexInList} >= {len(self.page_widgets) - self._map_size_tail}")

        # topTail = min(index - 1, self._map_size_tail) + 1
        # bottomTail = len(self.page_widgets) - min(self._map_size_tail, self.countTotalPagesInfo - index)

        tail = self.map_page.map_size_tail
        top_tail = min(index - 1, tail)
        bottom_tail = len(self.page_widgets) - min(tail, self.countTotalPagesInfo - index)

        if not top_tail <= indexInList <= bottom_tail:
            # self.calculateMapPagesByIndex(index)
            return True

        return False

    def calculateMapPagesByIndex(self, index: int):
        map_pages = []

        # cur_min = index - min(self._map_step, index)
        # cur_max = index + min(self._map_step, self.countTotalPagesInfo - index - 1)

        cur_min, cur_max = self.map_page.calculate(index, self.countTotalPagesInfo)

        if self.countTotalPagesInfo == 0:
            raise Exception(f"PageInfo не инициализирован")

        try:

            for indexI, i in enumerate(range(cur_min, cur_max + 1)):

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

                    try:
                        newWidget.overlay.annotation_changed.connect(
                            lambda pw=newWidget, orig=page_info_i.page_num: self._save_vector_immediate(pw, orig)
                        )
                    except Exception as e:
                        print(
                            f"[PDFViewer] create_placeholder_widgets: connect failed for orig {page_info_i.page_num}: {e}")

                    map_pages.append(newWidget)

            # print(f"Current pages: {[x.layout_index for x in self.page_widgets]}")
            # print(f"New pages: {[x.layout_index for x in map_pages]}")

            widget_for_delete = list((set(self.page_widgets) ^ set(map_pages)) & set(self.page_widgets))
            widget_for_add = list((set(self.page_widgets) ^ set(map_pages)) & set(map_pages))

            widget_for_delete.sort(key=lambda x: x.layout_index)
            widget_for_add.sort(key=lambda x: x.layout_index)

            # print(f"Deleting: {[x.layout_index for x in widget_for_delete]}")
            # print(f"Adding: {[x.layout_index for x in widget_for_add]}")

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

                # print(f"Add widget {widget.layout_index} in index {insertIndex}")
                self.insertPageWidget(insertIndex, widget)
                # print(f"Pages: {[x.layout_index for x in self.page_widgets]}")

            if self.page_widgets[0].layout_index > 0:
                self.addSpacer(self.getTotalHeightByCountPages(self.page_widgets[0].layout_index, True))
            else:
                self.removeSpacer()

            gc.collect()

        except Exception as e:
            raise Exception(f"Ошибка расчёта карты страниц: {e}")

        # print(f"END Pages: {[x.layout_index for x in self.page_widgets]}")

    def clear(self):
        self.countTotalPagesInfo = 0
        self.pages_info = []

        for i in range(len(self.page_widgets)):
            self.removePageWidget(self.page_widgets[0])

        if self.isSpacer:
            self.removeSpacer()

        self.chunks.clear()
        self.chunks = []
        self.current_chunk_index = 0

        self.zoom = 1.0
        self.dict_vectors.Clear()

    def clearWidgets(self):
        for i in range(len(self.page_widgets)):
            self.removePageWidget(self.page_widgets[0])

        # self.page_widgets.clear()
        # self.page_widgets = []

        if self.isSpacer:
            self.removeSpacer()

    def _save_vector_immediate(self, widget, orig_page_num: int):
        # print(f"num {widget}")
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
                self.dict_vectors.Add(self.page_vectors[orig_page_num], orig_page_num)
                self.pagePainted.emit()
                print(f"[PDFViewer] _save_vector_immediate: saved vector for orig {orig_page_num}")
            else:
                if orig_page_num in self.page_vectors:
                    self.page_vectors.pop(orig_page_num, None)

        except Exception as e:
            print(f"[PDFViewer] _save_vector_immediate error for orig {orig_page_num}: {e}")