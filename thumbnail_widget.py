import math
import threading
from typing import Optional, Dict, List
from collections import OrderedDict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSlider, QLabel, QScrollArea, QFrame,
    QInputDialog, QMessageBox, QSizePolicy, QSpacerItem, QScrollBar
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRunnable, QThreadPool, QRect
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QFont, QMouseEvent, QPaintEvent, QPen

import fitz  # PyMuPDF


class ThumbnailCache:
    """Кэш для миниатюр страниц с LRU-вытеснением"""

    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        # Храним сырые миниатюры БЕЗ номеров страниц
        self.cache: OrderedDict[tuple, QPixmap] = OrderedDict()  # (номер_страницы, размер) -> пиксмап

    def get_raw(self, page_num: int, size: int) -> Optional[QPixmap]:
        """Достаем сырую миниатюру без номера страницы"""
        key = (page_num, size)
        if key in self.cache:
            self.cache.move_to_end(key)  # Перемещаем в конец как недавно использованную
            return self.cache[key]
        return None

    def put_raw(self, page_num: int, size: int, pixmap: QPixmap):
        """Сохраняем сырую миниатюру без номера страницы"""
        key = (page_num, size)
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            self.cache[key] = pixmap
            # Вытесняем старые миниатюры если кэш переполнен
            while len(self.cache) > self.max_size:
                oldest = next(iter(self.cache))  # Самая старая запись
                oldest_pixmap = self.cache[oldest]
                if not oldest_pixmap.isNull():
                    oldest_pixmap = QPixmap()
                del self.cache[oldest]

    def clear(self):
        """Полная очистка кэша"""
        keys_to_delete = list(self.cache.keys())
        for key in keys_to_delete:
            pixmap = self.cache[key]
            if not pixmap.isNull():
                self.cache[key] = QPixmap()  # Освобождаем память
            del self.cache[key]
        self.cache.clear()

    def remove_page(self, page_num: int):
        """Удаляем все миниатюры для конкретной страницы"""
        keys_to_remove = [key for key in self.cache.keys() if key[0] == page_num]
        for key in keys_to_remove:
            pixmap = self.cache[key]
            if not pixmap.isNull():
                pixmap = QPixmap()
            del self.cache[key]


class ThumbnailRenderWorker(QRunnable):
    """Воркер для рендеринга миниатюр в фоне"""

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
        """Отменяем рендеринг"""
        self.cancelled = True

    def run(self):
        """Основной метод рендеринга"""
        if self.cancelled:
            return

        doc = None
        try:
            doc = fitz.open(self.doc_path)

            # Обрабатываем защиту паролем
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

            # Вычисляем масштаб для нужного размера миниатюры
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

            # Закрываем документ и чистим память
            doc.close()
            doc = None

            # Принудительная очистка
            del pix
            del matrix
            del page

            if not self.cancelled:
                # Передаем сырую пиксмап БЕЗ номера страницы
                self.callback(self.page_num, pixmap, self.render_id, self.thumbnail_size)
            else:
                # Чистим если отменили
                if not pixmap.isNull():
                    pixmap = QPixmap()

        except Exception as e:
            if not self.cancelled:
                print(f"Ошибка рендеринга миниатюры {self.page_num}: {e}")
        finally:
            # Всегда закрываем документ
            if doc is not None:
                try:
                    doc.close()
                except:
                    pass


class ThumbnailWidget(QWidget):
    """Виджет для одной миниатюры страницы"""

    clicked = Signal(int)  # Сигнал с номером оригинальной страницы

    def __init__(self, page_info, layout_index: int, zoom: float = 1.0, parent=None):
        super().__init__(parent)
        self.page_info = page_info
        self.layout_index = layout_index
        self.zoom = zoom
        self.is_selected = False

        # Вычисляем размер на основе размеров страницы и зума
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
        """)

        # Пиксмап миниатюры
        self.thumbnail_pixmap = None
        self.placeholder_pixmap = self._create_placeholder()

    def _create_placeholder(self) -> QPixmap:
        """Создаем заглушку с номером страницы"""
        pixmap = QPixmap(self.thumbnail_size, self.thumbnail_size)
        pixmap.fill(Qt.white)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Рисуем рамку страницы
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(0, 0, self.thumbnail_size - 1, self.thumbnail_size - 1)

        # Рисуем номер страницы
        painter.setPen(QColor(100, 100, 100))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        # Вычисляем номер для отображения (начинается с 1)
        display_num = self.layout_index + 1
        painter.drawText(pixmap.rect(), Qt.AlignCenter, str(display_num))
        painter.end()

        return pixmap

    def set_thumbnail(self, pixmap: QPixmap):
        """Устанавливаем пиксмап миниатюры"""
        self.thumbnail_pixmap = pixmap
        self.update()

    def set_selected(self, selected: bool):
        """Устанавливаем состояние выделения"""
        self.is_selected = selected
        self.update()

    def paintEvent(self, event: QPaintEvent):
        """Рисуем миниатюру"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Рисуем фон в зависимости от состояния
        if self.is_selected:
            painter.fillRect(self.rect(), QColor(227, 242, 253))  # Выделенный
        elif self.underMouse():
            painter.fillRect(self.rect(), QColor(240, 248, 255))  # При наведении
        else:
            painter.fillRect(self.rect(), QColor(248, 248, 248))  # Обычный

        # Рисуем рамку в зависимости от состояния
        border_rect = QRect(2, 2, self.width() - 4, self.height() - 4)
        if self.is_selected:
            painter.setPen(QPen(QColor(0, 120, 212), 2))  # Синяя для выделения
        elif self.underMouse():
            painter.setPen(QPen(QColor(144, 202, 249), 2))  # Светло-синяя при наведении
        else:
            painter.setPen(QPen(QColor(200, 200, 200), 2))  # Серая обычная
        painter.drawRoundedRect(border_rect, 4, 4)

        # Рисуем изображение миниатюры по центру
        thumb_rect = QRect(6, 6, self.thumbnail_size, self.thumbnail_size)
        if self.thumbnail_pixmap and not self.thumbnail_pixmap.isNull():
            # Масштабируем пиксмап с сохранением пропорций
            scaled_pixmap = self.thumbnail_pixmap.scaled(
                self.thumbnail_size, self.thumbnail_size,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            # Центрируем
            x = thumb_rect.center().x() - scaled_pixmap.width() // 2
            y = thumb_rect.center().y() - scaled_pixmap.height() // 2
            painter.drawPixmap(x, y, scaled_pixmap)
        else:
            # Рисуем заглушку
            painter.drawPixmap(thumb_rect, self.placeholder_pixmap)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        """Обрабатываем клик мыши"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.page_info.page_num)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        """Мышь вошла в виджет"""
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Мышь вышла из виджета"""
        self.update()
        super().leaveEvent(event)


class ThumbnailContainerWidget(QWidget):
    """Контейнер для миниатюр с прокруткой"""

    page_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Создаем область прокрутки
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # Без горизонтальной прокрутки
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Вертикальная по необходимости
        self.scroll_area.setFrameShape(QFrame.NoFrame)

        # Создаем контейнер для миниатюр
        self.container_widget = QWidget()
        self.thumbnail_layout = ThumbnailWidgetStack(self.container_widget)

        # Устанавливаем контейнер в область прокрутки
        self.scroll_area.setWidget(self.container_widget)

        # Основной лейаут
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll_area)

        # Подключаем сигналы
        self.thumbnail_layout.page_clicked.connect(self.page_clicked)

        # Устанавливаем минимальные размеры
        self.setMinimumWidth(150)
        self.setMinimumHeight(200)  # Нормальная минимальная высота

    def set_document(self, document, doc_path: str, password: str = ""):
        """Устанавливаем документ для миниатюр"""
        self.thumbnail_layout.set_document(document, doc_path, password)

    def set_current_page(self, original_page_num: int):
        """Выделяем миниатюру для указанной страницы"""
        self.thumbnail_layout.set_current_page(original_page_num)

    def set_zoom(self, zoom: float):
        """Устанавливаем уровень зума"""
        self.thumbnail_layout.setZoom(zoom)

    def hide_page_thumbnail(self, original_page_num: int):
        """Скрываем миниатюру удаленной страницы"""
        self.thumbnail_layout.hide_page_thumbnail(original_page_num)

    def rotate_page_thumbnail(self, original_page_num: int, rotation: int):
        """Поворачиваем миниатюру страницы"""
        self.thumbnail_layout.rotate_page_thumbnail(original_page_num, rotation)

    def update_thumbnails_order(self, visible_order: List[int]):
        """Обновляем порядок отображения"""
        self.thumbnail_layout.update_thumbnails_order(visible_order)

    def clear_thumbnails(self):
        """Очищаем все миниатюры"""
        self.thumbnail_layout.clear_thumbnails()


class ThumbnailWidgetStack(QVBoxLayout):
    """Основной контейнер для миниатюр, похожий на PageWidgetStack"""

    page_clicked = Signal(int)  # Сигнал с номером оригинальной страницы

    def __init__(self, mainWidget: QWidget, spacing: int = 5, all_margins: int = 5, map_step: int = 10):
        super(ThumbnailWidgetStack, self).__init__(mainWidget)
        self.setSpacing(spacing)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.setContentsMargins(all_margins, all_margins, all_margins, all_margins)

        # Документ и кэширование
        self.document = None
        self.doc_path = ""
        self.document_password = ""
        self.thumbnail_cache = ThumbnailCache(max_size=20)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)  # Один поток для рендеринга

        # Отслеживаем активные задачи рендеринга
        self.active_workers: Dict[str, ThumbnailRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()

        # Отслеживаем модификации страниц
        self.page_rotations = {}
        self.deleted_pages = set()

        # Данные миниатюр
        self.pages_info: list = []  # Список информации о страницах
        self.countTotalPagesInfo: int = 0
        self.thumbnail_widgets: list[ThumbnailWidget] = []

        # Управление лейаутом
        self.spacer: QSpacerItem = QSpacerItem(0, 0)
        self.isSpacer = False

        # Зум и размеры
        self.zoom = 0.15  # Стандартный зум для миниатюр
        self._map_step: int = map_step
        self._map_max: int = (self._map_step * 2) + 1
        self._map_size_tail = 3

        # Отслеживание видимых миниатюр для ленивой загрузки
        self.visible_thumbnails: OrderedDict[int, bool] = OrderedDict()
        self.max_visible_thumbnails = 20

        # Таймер для отложенной загрузки
        self.load_timer = QTimer()
        self.load_timer.setSingleShot(True)
        self.load_timer.timeout.connect(self.load_visible_thumbnails)

        # Текущее выделение
        self.current_selected_widget = None

        # Подключаем скроллбар к ленивой загрузке
        scroll_area = self.get_scroll_area()
        if scroll_area:
            scroll_bar = scroll_area.verticalScrollBar()
            if scroll_bar:
                scroll_bar.valueChanged.connect(self._on_scroll)

    def get_scroll_area(self):
        """Получаем родительскую область прокрутки если есть"""
        parent = self.parent()
        while parent:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parent()
        return None

    def _on_scroll(self, value):
        """Обрабатываем скроллинг для ленивой загрузки"""
        self.load_timer.start(50)

    def set_document(self, document, doc_path: str, password: str = ""):
        """Устанавливаем документ для отображения миниатюр"""
        self.cancel_all_renders()
        self.clear_thumbnails()

        self.document = document
        self.doc_path = doc_path
        self.document_password = password
        self.page_rotations.clear()
        self.deleted_pages.clear()
        self.visible_thumbnails.clear()

        if document:
            # Создаем список информации о страницах
            self.pages_info = []
            for page_num in range(len(document)):
                page = document[page_num]
                rect = page.rect
                # Создаем объект с информацией о странице
                page_info = type('PageInfo', (), {
                    'page_num': page_num,
                    'width': rect.width,
                    'height': rect.height,
                    'rotation': 0
                })()
                self.pages_info.append(page_info)

            self.countTotalPagesInfo = len(self.pages_info)

            # Инициализируем первой партией миниатюр
            self.calculateMapPagesByIndex(0)

    def clear_thumbnails(self):
        """Очищаем все миниатюры и сбрасываем состояние"""
        self.cancel_all_renders()

        # Удаляем все виджеты
        for widget in self.thumbnail_widgets:
            self.removeWidget(widget)
            widget.deleteLater()

        self.thumbnail_widgets.clear()

        # Очищаем кэш
        self.thumbnail_cache.clear()

        # Очищаем данные
        self.pages_info.clear()
        self.countTotalPagesInfo = 0
        self.deleted_pages.clear()
        self.page_rotations.clear()
        self.visible_thumbnails.clear()

        # Удаляем спейсер
        if self.isSpacer:
            self.removeItem(self.spacer)
            self.isSpacer = False

        # Сбрасываем ссылки на документ
        self.document = None
        self.doc_path = ""
        self.document_password = ""

    def cancel_all_renders(self):
        """Отменяем все активные задачи рендеринга"""
        with self.render_lock:
            for worker_id, worker in list(self.active_workers.items()):
                worker.cancel()
            self.active_workers.clear()
        self.thread_pool.waitForDone()

    def setZoom(self, newZoom):
        """Устанавливаем уровень зума для миниатюр"""
        self.zoom = newZoom

        # Обновляем шаг карты на основе зума
        if newZoom < 0.1:
            newStep = round(3.2 - 2.95 * math.log(newZoom))
        else:
            newStep = 3

        self._map_step = newStep + 3
        self._map_size_tail = newStep

        # Обновляем все существующие виджеты
        for widget in self.thumbnail_widgets:
            page_info = self.pages_info[widget.layout_index]
            thumbnail_size = int(max(page_info.width, page_info.height) * self.zoom)
            widget.thumbnail_size = thumbnail_size
            widget.setFixedSize(thumbnail_size + 12, thumbnail_size + 12)
            widget.placeholder_pixmap = widget._create_placeholder()
            widget.update()

        # Перезагружаем миниатюры с новым размером
        self.load_timer.start(200)

    def getThumbnailWidgetByIndex(self, index: int) -> ThumbnailWidget:
        """Получаем виджет миниатюры по индексу лейаута"""
        widgets = list(filter(lambda x: x.layout_index == index, self.thumbnail_widgets))
        if len(widgets) == 0:
            return None
        return widgets[0]

    def getPageInfoByIndex(self, index: int):
        """Получаем информацию о странице по индексу"""
        if 0 <= index < len(self.pages_info):
            return self.pages_info[index]
        return None

    def getTotalHeightByCountPages(self, count: int):
        """Вычисляем общую высоту для указанного количества страниц"""
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
        """Получаем индекс текущей страницы на основе высоты скролла"""
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
        """Проверяем нужно ли пересчитывать на основе позиции скролла"""
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
        """Вычисляем какие миниатюры показывать на основе текущего индекса"""
        if self.countTotalPagesInfo == 0:
            return

        map_pages = []
        cur_min = index - min(self._map_step, index)
        cur_max = index + min(self._map_step, self.countTotalPagesInfo - index - 1)

        try:
            # Создаем или получаем виджеты для текущего диапазона
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

            # Находим виджеты для удаления и добавления
            widgets_to_delete = list((set(self.thumbnail_widgets) - set(map_pages)))
            widgets_to_add = list((set(map_pages) - set(self.thumbnail_widgets)))

            # Удаляем старые виджеты
            for widget in widgets_to_delete:
                self.removeWidget(widget)
                self.thumbnail_widgets.remove(widget)
                widget.deleteLater()

            # Добавляем новые виджеты
            for widget in widgets_to_add:
                self.thumbnail_widgets.append(widget)

                # Вставляем в правильную позицию
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

            # Обновляем спейсер
            if self.thumbnail_widgets and self.thumbnail_widgets[0].layout_index > 0:
                self.addSpacer(self.getTotalHeightByCountPages(self.thumbnail_widgets[0].layout_index))
            else:
                self.removeSpacer()

            # Загружаем миниатюры для видимых виджетов
            self.load_timer.start(100)

        except Exception as e:
            print(f"Ошибка расчета карты миниатюр: {e}")

    def addSpacer(self, height):
        """Добавляем спейсер в лейаут"""
        try:
            if self.isSpacer:
                self.removeItem(self.spacer)
            self.spacer = QSpacerItem(0, height, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.insertSpacerItem(0, self.spacer)
            self.isSpacer = True
        except Exception as e:
            print(f"Ошибка добавления спейсера: {e}")

    def removeSpacer(self):
        """Удаляем спейсер из лейаута"""
        try:
            if not self.isSpacer:
                return
            self.removeItem(self.spacer)
            self.isSpacer = False
        except Exception as e:
            print(f"Ошибка удаления спейсера: {e}")

    def load_visible_thumbnails(self):
        """Загружаем миниатюры для текущих видимых виджетов"""
        if not self.thumbnail_widgets:
            return

        # Обновляем отслеживание видимых страниц
        visible_pages = set()
        for widget in self.thumbnail_widgets:
            original_page = widget.page_info.page_num
            visible_pages.add(original_page)
            if original_page in self.visible_thumbnails:
                self.visible_thumbnails.move_to_end(original_page)
            else:
                self.visible_thumbnails[original_page] = True

        # LRU вытеснение
        while len(self.visible_thumbnails) > self.max_visible_thumbnails:
            oldest_page, _ = self.visible_thumbnails.popitem(last=False)
            self.thumbnail_cache.remove_page(oldest_page)

        # Загружаем миниатюры для видимых страниц
        for original_page in visible_pages:
            self.load_thumbnail(original_page)

    def load_thumbnail(self, original_page_num: int):
        """Загружаем миниатюру для конкретной страницы"""
        if original_page_num >= len(self.pages_info):
            return

        # Находим виджет для этой страницы
        widget = None
        for thumb_widget in self.thumbnail_widgets:
            if thumb_widget.page_info.page_num == original_page_num:
                widget = thumb_widget
                break

        if not widget:
            return

        # Проверяем кэш сначала
        thumbnail_size = int(max(widget.base_width, widget.base_height) * self.zoom)
        cached_raw = self.thumbnail_cache.get_raw(original_page_num, thumbnail_size)
        if cached_raw:
            widget.set_thumbnail(cached_raw)
            return

        # Генерируем уникальный ID рендеринга
        with self.render_lock:
            self.current_render_id += 1
            render_id = f"thumb_{self.current_render_id}_{original_page_num}_{thumbnail_size}"

        # Получаем поворот для этой страницы
        rotation = self.page_rotations.get(original_page_num, 0)

        # Создаем воркер
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
        """Обрабатываем результат рендеринга миниатюры"""
        with self.render_lock:
            if render_id in self.active_workers:
                del self.active_workers[render_id]

        # Сохраняем в кэш
        self.thumbnail_cache.put_raw(original_page_num, size, raw_pixmap)

        # Обновляем отслеживание
        if original_page_num in self.visible_thumbnails:
            self.visible_thumbnails.move_to_end(original_page_num)

        # Находим и обновляем виджет
        for widget in self.thumbnail_widgets:
            if widget.page_info.page_num == original_page_num:
                widget.set_thumbnail(raw_pixmap)
                break

    def _on_thumbnail_clicked(self, original_page_num: int):
        """Обрабатываем клик по миниатюре"""
        # Очищаем предыдущее выделение
        if self.current_selected_widget:
            self.current_selected_widget.set_selected(False)

        # Устанавливаем новое выделение
        for widget in self.thumbnail_widgets:
            if widget.page_info.page_num == original_page_num:
                widget.set_selected(True)
                self.current_selected_widget = widget
                break

        self.page_clicked.emit(original_page_num)

    def set_current_page(self, original_page_num: int):
        """Выделяем миниатюру для указанной оригинальной страницы"""
        # Очищаем предыдущее выделение
        if self.current_selected_widget:
            self.current_selected_widget.set_selected(False)

        # Устанавливаем новое выделение
        for widget in self.thumbnail_widgets:
            if widget.page_info.page_num == original_page_num:
                widget.set_selected(True)
                self.current_selected_widget = widget

                # Убеждаемся что эта миниатюра в текущей карте
                if widget.layout_index not in [w.layout_index for w in self.thumbnail_widgets]:
                    self.calculateMapPagesByIndex(widget.layout_index)
                break

    def hide_page_thumbnail(self, original_page_num: int):
        """Скрываем миниатюру удаленной страницы"""
        self.deleted_pages.add(original_page_num)

        # Удаляем из кэша и отслеживания
        self.thumbnail_cache.remove_page(original_page_num)
        self.visible_thumbnails.pop(original_page_num, None)

        # Удаляем виджет если он существует
        widget_to_remove = None
        for widget in self.thumbnail_widgets:
            if widget.page_info.page_num == original_page_num:
                widget_to_remove = widget
                break

        if widget_to_remove:
            self.removeWidget(widget_to_remove)
            self.thumbnail_widgets.remove(widget_to_remove)
            widget_to_remove.deleteLater()

            # Пересчитываем лейаут
            if self.thumbnail_widgets:
                self.calculateMapPagesByIndex(self.thumbnail_widgets[0].layout_index)

    def rotate_page_thumbnail(self, original_page_num: int, rotation: int):
        """Поворачиваем миниатюру страницы и перезагружаем ее"""
        current_rotation = self.page_rotations.get(original_page_num, 0)
        new_rotation = (current_rotation + rotation) % 360
        self.page_rotations[original_page_num] = new_rotation

        # Удаляем из кэша для принудительной перезагрузки
        self.thumbnail_cache.remove_page(original_page_num)
        self.visible_thumbnails.pop(original_page_num, None)

        # Перезагружаем миниатюру
        QTimer.singleShot(100, lambda: self.load_thumbnail(original_page_num))

    def update_thumbnails_order(self, visible_order: List[int]):
        """Обновляем порядок отображения и перезагружаем все миниатюры"""
        # пока просто пересчитываем на основе первой видимой страницы (хз)
        if visible_order:
            self.calculateMapPagesByIndex(visible_order[0])
