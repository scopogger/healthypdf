import fitz  # PyMuPDF
from PySide6.QtWidgets import (QMessageBox, QProgressDialog, QApplication)
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtGui import QPainter, QImage, QTransform
from PySide6.QtCore import QRectF, Qt


class PDFPrinter:
    mm_per_inch = 25.4
    points_per_inch = 72.0

    @staticmethod
    def print_pdf_with_settings(main_window, doc):
        total_pages = len(doc)
        if total_pages == 0:
            QMessageBox.warning(main_window, "Пустой PDF", "Файл не содержит страниц.")
            return

        printer = QPrinter(QPrinter.HighResolution)
        printer.setFromTo(1, total_pages)

        # Show print preview — the preview's own "Print" button opens the print settings dialog.
        # We deliberately skip a separate QPrintDialog here so the user sees exactly one dialog.
        preview = QPrintPreviewDialog(printer, main_window)
        preview.setWindowTitle("Предпросмотр и печать")

        preview.paintRequested.connect(
            lambda p: PDFPrinter._paint_to_printer(p, doc, main_window)
        )

        preview.exec()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _paint_to_printer(printer: QPrinter, doc, main_window):
        """
        Render all requested pages onto *printer*.
        Called both by the preview widget and the final print pass.
        """
        total_pages = len(doc)
        mode = printer.printRange()
        pages_to_print = PDFPrinter._extract_pages_from_printer(printer, total_pages, mode)
        if not pages_to_print:
            return

        paint_rect_px = printer.pageLayout().paintRectPixels(printer.resolution())
        paper_w_px = paint_rect_px.width()
        paper_h_px = paint_rect_px.height()
        render_dpi = min(printer.resolution(), 300)

        painter = QPainter(printer)
        try:
            for idx, page_num in enumerate(pages_to_print):
                page = doc.load_page(page_num)
                rect = page.rect
                is_landscape = rect.width > rect.height

                base_scale = render_dpi / PDFPrinter.points_per_inch
                mat = fitz.Matrix(base_scale, base_scale)
                pix = page.get_pixmap(matrix=mat)
                qimg = QImage.fromData(pix.tobytes("png"), "png")
                if qimg.isNull():
                    continue

                if is_landscape:
                    qimg = qimg.transformed(QTransform().rotate(90))

                img_w = qimg.width()
                img_h = qimg.height()
                if img_w and img_h:
                    scale_factor = min(paper_w_px / img_w, paper_h_px / img_h)
                else:
                    scale_factor = 1.0

                scale_w = img_w * scale_factor
                scale_h = img_h * scale_factor
                target_x = (paper_w_px - scale_w) / 2
                target_y = (paper_h_px - scale_h) / 2
                painter.drawImage(QRectF(target_x, target_y, scale_w, scale_h), qimg)

                if idx < len(pages_to_print) - 1:
                    printer.newPage()
        finally:
            painter.end()

    @staticmethod
    def _extract_pages_from_printer(printer, total_pages, mode):
        pages = []
        if mode == QPrinter.PrintRange.PageRange:
            from_page = max(1, printer.fromPage())
            to_page = min(total_pages, printer.toPage())
            pages = list(range(from_page - 1, to_page))
        elif mode == QPrinter.PrintRange.AllPages:
            pages = list(range(total_pages))
        elif mode == QPrinter.PrintRange.CurrentPage:
            pages = [0]
        return sorted({p for p in pages if 0 <= p < total_pages})
