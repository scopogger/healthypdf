import fitz
import gc
from pymupdf import Page

from classes.document import Document
from PySide6.QtCore import (
    Qt, QRunnable, QThreadPool, QTimer, Signal, QSize
)
from PySide6.QtGui import QPixmap


class PageRenderWorker(QRunnable):
    """Lightweight worker for rendering pages (page_num here is ORIGINAL page number)"""

    def __init__(self, page: Page, page_num: int, zoom: float, callback, render_id: str, rotation: int = 0):
        super().__init__()
        self.page = page
        self.page_num = page_num  # ORIGINAL document page index
        self.zoom = zoom
        self.callback = callback
        self.render_id = render_id
        self.rotation = rotation
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        if self.cancelled:
            return

        try:
            # print(f"Rendering page {self.page_num} with zoom {self.zoom}")

            # Open document briefly

            if self.cancelled:
                # self.current_doc.close()
                return

            # if self.cancelled:
            #     self.current_doc.close()
            #     return

            # Apply rotation
            old_rotation = self.page.rotation
            if self.rotation != 0:
                self.page.set_rotation(old_rotation + self.rotation)

            # Use zoom to create matrix - this determines the actual pixel dimensions
            matrix = fitz.Matrix(self.zoom, self.zoom)
            pix = self.page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB, clip=None)

            # if self.cancelled:
            #     self.current_doc.close()
            #     return

            # Convert to QPixmap
            img_data = pix.tobytes("ppm")
            pixmap = QPixmap()
            success = pixmap.loadFromData(img_data)

            # Force cleanup of PyMuPDF objects
            if self.rotation != 0:
                self.page.set_rotation(old_rotation)

            del pix
            del matrix

            gc.collect()

            if not self.cancelled and success:
                # callback receives original page number, pixmap and render_id
                self.callback(self.page_num, pixmap, self.render_id)
            else:
                print(f"Failed to render page {self.page_num} or was cancelled")
                # Clean up the pixmap if not used
                if not pixmap.isNull():
                    pixmap = QPixmap()

        except Exception as e:
            if not self.cancelled:
                print(f"Error rendering page {self.page_num}: {e}")
