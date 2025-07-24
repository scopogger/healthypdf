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
    """Aggressive LRU Cache for rendered pages"""

    def __init__(self, max_size: int = 6):
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
            if len(self.cache) > self.max_size:
                oldest = next(iter(self.cache))
                del self.cache[oldest]
                gc.collect()

    def clear(self):
        self.cache.clear()
        gc.collect()

    def keep_only_pages(self, page_numbers: Set[int]):
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
            matrix = fitz.Matrix(self.zoom, self.zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
            if self.cancelled:
                doc.close()
                return
            img_data = pix.tobytes("ppm")
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            if not self.cancelled and (pixmap.width() > 2000 or pixmap.height() > 2000):
                pixmap = pixmap.scaled(min(2000, pixmap.width()), min(2000, pixmap.height()), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            doc.close()
            if not self.cancelled:
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
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.is_loaded = True
        self.setStyleSheet("")


class PDFViewer(QScrollArea):
    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None
        self.doc_path = ""
        self.pages_info = []
        self.page_widgets = []
        self.zoom_level = 1.0
        self.page_cache = PageCache(max_size=6)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(2)
        self.active_workers: Dict[str, PageRenderWorker] = {}
        self.current_render_id = 0
        self.render_lock = threading.Lock()
        self.is_modified = False
        self.deleted_pages = set()
        self.page_moves = {}
        self.setup_ui()
        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.update_visible_pages)
        self.verticalScrollBar().valueChanged.connect(self.on_scroll)
        self.last_visible_pages = set()

    def setup_ui(self):
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignCenter)
        self.pages_container = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setSpacing(10)
        self.pages_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.setWidget(self.pages_container)

    def open_document(self, file_path: str) -> bool:
        try:
            self.close_document()
            self.zoom_level = 1.0
            self.document = fitz.open(file_path)
            self.doc_path = file_path
            self.is_modified = False
            self.deleted_pages = set()
            self.page_moves = {}
            self.pages_info = []
            for page_num in range(len(self.document)):
                page = self.document[page_num]
                rect = page.rect
                self.pages_info.append(PageInfo(page_num, int(rect.width), int(rect.height)))
            self.create_page_widgets()
            self.verticalScrollBar().setValue(0)
            QTimer.singleShot(50, self.update_visible_pages)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open PDF: {e}")
            return False

    def close_document(self):
        self.cancel_all_renders()
        if self.document:
            self.document.close()
            self.document = None
        self.doc_path = ""
        self.pages_info.clear()
        self.page_cache.clear()
        self.last_visible_pages.clear()
        self.is_modified = False
        self.deleted_pages = set()
        self.page_moves = {}
        for widget in self.page_widgets:
            widget.deleteLater()
        self.page_widgets.clear()
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        gc.collect()

    def cancel_all_renders(self):
        with self.render_lock:
            for worker in self.active_workers.values():
                worker.cancel()
            self.active_workers.clear()

    def create_page_widgets(self):
        self.page_widgets = []
        for page_info in self.pages_info:
            display_width = int(page_info.width * self.zoom_level)
            display_height = int(page_info.height * self.zoom_level)
            page_widget = PageWidget(page_info.page_num, page_info)
            page_widget.setMinimumSize(display_width, display_height)
            self.page_widgets.append(page_widget)
            self.pages_layout.addWidget(page_widget)

    def on_scroll(self):
        self.cancel_all_renders()
        self.scroll_timer.start(100)

    def update_visible_pages(self):
        if not self.document:
            return
        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()
        buffer_pages = 1
        visible_pages = set()
        current_center_page = None
        viewport_center_y = scroll_y + viewport_rect.height() // 2
        for i, widget in enumerate(self.page_widgets):
            widget_y = widget.y() - scroll_y
            widget_bottom = widget_y + widget.height()
            if widget_bottom >= 0 and widget_y <= viewport_rect.height():
                visible_pages.add(i)
                widget_center_y = widget.y() + widget.height() // 2
                if current_center_page is None or abs(widget_center_y - viewport_center_y) < abs(
                        self.page_widgets[current_center_page].y() + self.page_widgets[current_center_page].height() // 2 - viewport_center_y):
                    current_center_page = i
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

        for page_num in visible_pages:
            self.load_page(page_num)
        self.last_visible_pages = visible_pages.copy()
        if current_center_page is not None:
            self.page_changed.emit(current_center_page)
        gc.collect()

    def get_current_page(self) -> int:
        if not self.document or not self.page_widgets:
            return 0
        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()
        viewport_center_y = scroll_y + viewport_rect.height() // 2
        current_page, min_distance = 0, float('inf')
        for i, widget in enumerate(self.page_widgets):
            if widget.page_num in self.deleted_pages:
                continue
            widget_center_y = widget.y() + widget.height() // 2
            dist = abs(widget_center_y - viewport_center_y)
            if dist < min_distance:
                min_distance, current_page = dist, widget.page_num
        return current_page

    def delete_current_page(self) -> bool:
        if not self.document:
            return False
        cur = self.get_current_page()
        remaining = len(self.pages_info) - len(self.deleted_pages)
        if remaining <= 1:
            QMessageBox.warning(None, "Cannot Delete", "Cannot delete the last remaining page.")
            return False
        self.deleted_pages.add(cur)
        self.is_modified = True
        if cur < len(self.page_widgets):
            self.page_widgets[cur].hide()
        self.update_visible_pages()
        return True

    def move_page_up(self) -> bool:
        if not self.document:
            return False
        cur = self.get_current_page()
        prev = next((i for i in range(cur-1, -1, -1) if i not in self.deleted_pages), None)
        if prev is None:
            return False
        self._swap_pages_in_layout(cur, prev)
        self.is_modified = True
        return True

    def move_page_down(self) -> bool:
        if not self.document:
            return False
        cur = self.get_current_page()
        nxt = next((i for i in range(cur+1, len(self.pages_info)) if i not in self.deleted_pages), None)
        if nxt is None:
            return False
        self._swap_pages_in_layout(cur, nxt)
        self.is_modified = True
        return True

    def _swap_pages_in_layout(self, p1: int, p2: int):
        if p1>=len(self.page_widgets) or p2>=len(self.page_widgets): return
        w1, w2 = self.page_widgets[p1], self.page_widgets[p2]
        pos1, pos2 = self.pages_layout.indexOf(w1), self.pages_layout.indexOf(w2)
        self.pages_layout.removeWidget(w1); self.pages_layout.removeWidget(w2)
        self.pages_layout.insertWidget(pos1, w2); self.pages_layout.insertWidget(pos2, w1)
        old1, old2 = self.page_moves.get(p1, p1), self.page_moves.get(p2, p2)
        self.page_moves[p1], self.page_moves[p2] = old2, old1

    def save_changes(self, file_path: str = None) -> bool:
        if not self.document or not self.is_modified:
            return True
        try:
            path = file_path or self.doc_path
            new_doc = fitz.open()
            order = []
            for i in range(self.pages_layout.count()):
                w = self.pages_layout.itemAt(i).widget()
                if hasattr(w, 'page_num') and w.page_num not in self.deleted_pages:
                    order.append(w.page_num)
            for p in order:
                if p<len(self.document): new_doc.insert_pdf(self.document, from_page=p, to_page=p)
            new_doc.save(path)
            new_doc.close()
            if path == self.doc_path:
                self.open_document(path)
            return True
        except Exception as e:
            QMessageBox.critical(None, "Save Error", f"Failed to save PDF: {e}")
            return False

    def has_unsaved_changes(self) -> bool:
        return self.is_modified

    def load_page(self, page_num: int):
        if page_num>=len(self.page_widgets): return
        widget = self.page_widgets[page_num]
        if widget.is_loaded: return
        cached = self.page_cache.get(page_num)
        if cached:
            widget.set_pixmap(cached)
            return
        with self.render_lock:
            self.current_render_id+=1
            rid=f"r{self.current_render_id}_{page_num}"
        worker=PageRenderWorker(self.doc_path, page_num, self.zoom_level, self.on_page_rendered, rid)
        with self.render_lock:
            self.active_workers[rid]=worker
        self.thread_pool.start(worker)

    def on_page_rendered(self, page_num: int, pixmap: QPixmap, render_id: str):
        with self.render_lock:
            self.active_workers.pop(render_id, None)
        if page_num not in self.last_visible_pages: return
        if page_num<len(self.page_widgets):
            self.page_cache.put(page_num, pixmap)
            w=self.page_widgets[page_num]
            if not w.is_loaded:
                w.set_pixmap(pixmap)

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
        if 0<=page_num<len(self.page_widgets):
            self.cancel_all_renders()
            self.ensureWidgetVisible(self.page_widgets[page_num])


class PDFEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pdf_viewer = None
        self.current_document_path = ""
        self.setup_ui()
        self.setup_menus()
        self.setup_toolbar()
        self.setup_status_bar()
        self.setAcceptDrops(True)
        self.setWindowTitle("PDF Editor")
        self.resize(1200, 800)
        self.update_toolbar_state()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.page_changed.connect(self.on_page_changed)
        layout.addWidget(self.pdf_viewer)

    def setup_menus(self):
        mb = self.menuBar()
        fm = mb.addMenu("File")
        open_act = QAction("Open...", self)
        open_act.setShortcut(QKeySequence.Open)
        open_act.triggered.connect(self.open_file)
        fm.addAction(open_act)
        close_act = QAction("Close", self)
        close_act.setShortcut(QKeySequence.Close)
        close_act.triggered.connect(self.close_file)
        fm.addAction(close_act)
        fm.addSeparator()
        save_act = QAction("Save", self)
        save_act.setShortcut(QKeySequence.Save)
        save_act.triggered.connect(self.save_file)
        fm.addAction(save_act)
        save_as_act = QAction("Save As...", self)
        save_as_act.setShortcut(QKeySequence.SaveAs)
        save_as_act.triggered.connect(self.save_file_as)
        fm.addAction(save_as_act)
        fm.addSeparator()
        exit_act = QAction("Exit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.triggered.connect(self.close)
        fm.addAction(exit_act)
        em = mb.addMenu("Edit")
        self.delete_page_action = QAction("Delete Current Page", self)
        self.delete_page_action.setShortcut("Delete")
        self.delete_page_action.triggered.connect(self.delete_current_page)
        em.addAction(self.delete_page_action)
        em.addSeparator()
        self.move_up_action = QAction("Move Page Up", self)
        self.move_up_action.setShortcut("Ctrl+Up")
        self.move_up_action.triggered.connect(self.move_page_up)
        em.addAction(self.move_up_action)
        self.move_down_action = QAction("Move Page Down", self)
        self.move_down_action.setShortcut("Ctrl+Down")
        self.move_down_action.triggered.connect(self.move_page_down)
        em.addAction(self.move_down_action)

    def setup_toolbar(self):
        tb = self.addToolBar("Main")
        tb.addWidget(QLabel("Zoom:"))
        zo = QPushButton("-")
        zo.setFixedSize(30,30)
        zo.clicked.connect(self.zoom_out)
        tb.addWidget(zo)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10,500)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(200)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        tb.addWidget(self.zoom_slider)
        zi = QPushButton("+")
        zi.setFixedSize(30,30)
        zi.clicked.connect(self.zoom_in)
        tb.addWidget(zi)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        tb.addWidget(self.zoom_label)
        tb.addSeparator()
        self.delete_btn = QPushButton("Delete Page")
        self.delete_btn.clicked.connect(self.delete_current_page)
        tb.addWidget(self.delete_btn)
        self.move_up_btn = QPushButton("Move Up")
        self.move_up_btn.clicked.connect(self.move_page_up)
        tb.addWidget(self.move_up_btn)
        self.move_down_btn = QPushButton("Move Down")
        self.move_down_btn.clicked.connect(self.move_page_down)
        tb.addWidget(self.move_down_btn)
        tb.addSeparator()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_file)
        tb.addWidget(self.save_btn)
        self.save_as_btn = QPushButton("Save As...")
        self.save_as_btn.clicked.connect(self.save_file_as)
        tb.addWidget(self.save_as_btn)

    def setup_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.page_info_label = QLabel("No document")
        sb.addWidget(self.page_info_label)

    def update_toolbar_state(self):
        has = self.pdf_viewer.document is not None
        self.delete_btn.setEnabled(has)
        self.move_up_btn.setEnabled(has)
        self.move_down_btn.setEnabled(has)
        self.save_btn.setEnabled(has)
        self.save_as_btn.setEnabled(has)
        self.delete_page_action.setEnabled(has)
        self.move_up_action.setEnabled(has)
        self.move_down_action.setEnabled(has)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if not path: return
        if self.pdf_viewer.has_unsaved_changes():
            r = QMessageBox.question(self, "Unsaved Changes", "Save changes?", QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
            if r == QMessageBox.Save and not self.pdf_viewer.save_changes(): return
            if r == QMessageBox.Cancel: return
        self.zoom_slider.setValue(100)
        if self.pdf_viewer.open_document(path):
            self.current_document_path = path
            self.setWindowTitle(f"PDF Editor - {os.path.basename(path)}")
            self.update_status_bar()
            self.update_toolbar_state()

    def close_file(self):
        if self.pdf_viewer.has_unsaved_changes():
            r = QMessageBox.question(self, "Unsaved Changes", "Save changes?", QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
            if r == QMessageBox.Save and not self.pdf_viewer.save_changes(): return
            if r == QMessageBox.Cancel: return
        self.zoom_slider.setValue(100)
        self.pdf_viewer.close_document()
        self.current_document_path = ""
        self.setWindowTitle("PDF Editor")
        self.page_info_label.setText("No document")
        self.update_toolbar_state()

    def zoom_in(self):
        v = self.zoom_slider.value()+25
        self.zoom_slider.setValue(min(500, v))

    def zoom_out(self):
        v = self.zoom_slider.value()-25
        self.zoom_slider.setValue(max(10, v))

    def on_zoom_changed(self, val):
        self.zoom_label.setText(f"{val}%")
        self.pdf_viewer.set_zoom(val/100)

    def delete_current_page(self):
        if self.pdf_viewer.delete_current_page():
            self.update_status_bar()
            if self.current_document_path and '*' not in self.windowTitle():
                self.setWindowTitle(f"PDF Editor - {os.path.basename(self.current_document_path)}*")
            self.update_toolbar_state()

    def move_page_up(self):
        if self.pdf_viewer.move_page_up():
            self.update_status_bar()
            if self.current_document_path and '*' not in self.windowTitle():
                self.setWindowTitle(f"PDF Editor - {os.path.basename(self.current_document_path)}*")
            self.update_toolbar_state()

    def move_page_down(self):
        if self.pdf_viewer.move_page_down():
            self.update_status_bar()
            if self.current_document_path and '*' not in self.windowTitle():
                self.setWindowTitle(f"PDF Editor - {os.path.basename(self.current_document_path)}*")
            self.update_toolbar_state()

    def save_file(self):
        if not self.current_document_path:
            self.save_file_as(); return
        if self.pdf_viewer.save_changes():
            if '*' in self.windowTitle():
                self.setWindowTitle(f"PDF Editor - {os.path.basename(self.current_document_path)}")

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF As", "", "PDF Files (*.pdf)")
        if not path: return
        if self.pdf_viewer.save_changes(path):
            self.current_document_path = path
            self.setWindowTitle(f"PDF Editor - {os.path.basename(path)}")

    def on_page_changed(self, page_num):
        self.update_status_bar(page_num)

    def update_status_bar(self, current_page=0):
        if self.pdf_viewer.document:
            total = len(self.pdf_viewer.document)
            self.page_info_label.setText(f"Page {current_page+1} of {total}")
        else:
            self.page_info_label.setText("No document")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].toLocalFile().lower().endswith('.pdf'):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith('.pdf') and self.pdf_viewer.open_document(path):
                self.current_document_path = path
                self.setWindowTitle(f"PDF Editor - {os.path.basename(path)}")
                self.update_status_bar()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Editor")
    app.setApplicationVersion("1.0")
    editor = PDFEditor()
    editor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
