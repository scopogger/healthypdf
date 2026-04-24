import fitz  # PyMuPDF
from PySide6.QtWidgets import (QMessageBox, QApplication, QDialog, QVBoxLayout,
                                QHBoxLayout, QLabel, QLineEdit, QCheckBox,
                                QDialogButtonBox, QPushButton, QSpinBox)
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtGui import QPainter, QImage, QTransform
from PySide6.QtCore import QRectF, Qt


class PrintSetupDialog(QDialog):
    """Ask the user which pages to print and whether to show a preview."""

    def __init__(self, parent=None, total_pages: int = 1, current_page: int = 1):
        super().__init__(parent)
        self.total_pages = total_pages
        self.setWindowTitle("Печать")
        self.setModal(True)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Page range ──────────────────────────────────────────────────
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("С:"))
        self.from_input = QLineEdit(str(current_page))
        self.from_input.setFixedWidth(55)
        range_layout.addWidget(self.from_input)
        range_layout.addWidget(QLabel("по:"))
        self.to_input = QLineEdit(str(total_pages))
        self.to_input.setFixedWidth(55)
        range_layout.addWidget(self.to_input)
        range_layout.addWidget(QLabel(f"из {total_pages}"))
        range_layout.addStretch()
        layout.addLayout(range_layout)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # ── Show preview checkbox ───────────────────────────────────────
        self.preview_checkbox = QCheckBox("Показать предпросмотр перед печатью")
        self.preview_checkbox.setChecked(True)
        layout.addWidget(self.preview_checkbox)

        # ── Buttons ─────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.print_btn = QPushButton("Печать")
        self.print_btn.setDefault(True)
        self.print_btn.clicked.connect(self._on_print_clicked)
        btn_layout.addWidget(self.print_btn)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _parse(self):
        try:
            f = int(self.from_input.text().strip())
            t = int(self.to_input.text().strip())
        except ValueError:
            raise ValueError("Введите целые числа в поля «С» и «по».")
        if not (1 <= f <= self.total_pages):
            raise ValueError(f"Начальная страница должна быть от 1 до {self.total_pages}.")
        if not (1 <= t <= self.total_pages):
            raise ValueError(f"Конечная страница должна быть от 1 до {self.total_pages}.")
        if f > t:
            raise ValueError("Начальная страница не может быть больше конечной.")
        return f - 1, t - 1   # 0-based

    def _on_print_clicked(self):
        self.error_label.setVisible(False)
        try:
            self._parse()
        except ValueError as e:
            self.error_label.setText(str(e))
            self.error_label.setVisible(True)
            return
        self.accept()

    def get_page_range(self):
        f0, t0 = self._parse()
        return list(range(f0, t0 + 1))   # 0-based list

    def show_preview(self) -> bool:
        return self.preview_checkbox.isChecked()


class PDFPrinter:
    mm_per_inch = 25.4
    points_per_inch = 72.0

    PREVIEW_DPI = 96
    PRINT_DPI   = 300

    @staticmethod
    def print_pdf_with_settings(main_window, doc):
        total_pages = len(doc)
        if total_pages == 0:
            QMessageBox.warning(main_window, "Пустой PDF", "Файл не содержит страниц.")
            return

        # Determine current page for default "from" value
        current_page = 1
        try:
            pv = main_window.ui.pdfView
            current_page = pv.get_current_page() + 1  # 1-based
        except Exception:
            pass

        # ── Step 1: ask which pages and whether to preview ──────────────
        setup = PrintSetupDialog(main_window, total_pages=total_pages, current_page=current_page)
        if setup.exec() != QDialog.Accepted:
            return

        pages_to_print = setup.get_page_range()   # 0-based
        want_preview   = setup.show_preview()

        # Page-render cache shared between preview and final print pass
        _cache: dict = {}

        printer = QPrinter(QPrinter.HighResolution)
        printer.setFromTo(pages_to_print[0] + 1, pages_to_print[-1] + 1)

        if want_preview:
            # ── Step 2a: show preview; user clicks Print inside it ───────
            def _on_paint_preview(p: QPrinter):
                # For the preview widget Qt uses a low-res virtual device
                is_screen = (p.outputFormat() == QPrinter.OutputFormat.PdfFormat or
                             p.resolution() <= 150)
                dpi = PDFPrinter.PREVIEW_DPI if is_screen else PDFPrinter.PRINT_DPI
                PDFPrinter._paint_pages(p, doc, pages_to_print, dpi, _cache)

            preview = QPrintPreviewDialog(printer, main_window)
            preview.setWindowTitle("Предпросмотр и печать")
            preview.paintRequested.connect(_on_paint_preview)
            preview.exec()
        else:
            # ── Step 2b: print directly without preview ──────────────────
            from PySide6.QtPrintSupport import QPrintDialog
            dlg = QPrintDialog(printer, main_window)
            dlg.setWindowTitle("Настройки принтера")
            if dlg.exec() != QDialog.Accepted:
                return
            PDFPrinter._paint_pages(printer, doc, pages_to_print,
                                    PDFPrinter.PRINT_DPI, _cache)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _paint_pages(printer: QPrinter, doc, pages_to_print: list,
                     render_dpi: int, cache: dict):
        """
        Render *pages_to_print* (0-based list) onto *printer*.
        *cache* keyed by (page_num, dpi) so each page is rendered at most once.
        """
        paint_rect_px = printer.pageLayout().paintRectPixels(printer.resolution())
        paper_w_px = paint_rect_px.width()
        paper_h_px = paint_rect_px.height()

        painter = QPainter(printer)
        try:
            for idx, page_num in enumerate(pages_to_print):
                cache_key = (page_num, render_dpi)
                qimg = cache.get(cache_key)

                if qimg is None:
                    page = doc.load_page(page_num)
                    rect = page.rect
                    is_landscape = rect.width > rect.height

                    base_scale = render_dpi / PDFPrinter.points_per_inch
                    mat  = fitz.Matrix(base_scale, base_scale)
                    pix  = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
                    qimg = QImage.fromData(pix.tobytes("ppm"), "ppm")
                    del pix, mat

                    if qimg.isNull():
                        continue

                    if is_landscape:
                        qimg = qimg.transformed(QTransform().rotate(90))

                    cache[cache_key] = qimg
                    QApplication.processEvents()

                img_w, img_h = qimg.width(), qimg.height()
                if img_w and img_h:
                    scale_factor = min(paper_w_px / img_w, paper_h_px / img_h)
                else:
                    scale_factor = 1.0

                scale_w  = img_w * scale_factor
                scale_h  = img_h * scale_factor
                target_x = (paper_w_px - scale_w) / 2
                target_y = (paper_h_px - scale_h) / 2
                painter.drawImage(QRectF(target_x, target_y, scale_w, scale_h), qimg)

                if idx < len(pages_to_print) - 1:
                    printer.newPage()
        finally:
            painter.end()

    # kept for compatibility with old call-sites that pass printer + mode
    @staticmethod
    def _extract_pages_from_printer(printer, total_pages, mode):
        pages = []
        if mode == QPrinter.PrintRange.PageRange:
            from_page = max(1, printer.fromPage())
            to_page   = min(total_pages, printer.toPage())
            pages = list(range(from_page - 1, to_page))
        elif mode == QPrinter.PrintRange.AllPages:
            pages = list(range(total_pages))
        elif mode == QPrinter.PrintRange.CurrentPage:
            pages = [0]
        return sorted({p for p in pages if 0 <= p < total_pages})