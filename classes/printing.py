import fitz  # PyMuPDF
from PySide6.QtWidgets import (QMessageBox, QProgressDialog, QApplication)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtGui import QPainter, QImage, QPageLayout, QPageSize, QTransform
from PySide6.QtCore import QMarginsF, QRectF
from PySide6.QtCore import Qt


class PDFPrinter:
    mm_per_inch = 25.4
    points_per_inch = 72.0

    # def __init__(self, main_window, doc):
    #     self.main_window = main_window
    #     self.print_pdf_with_settings(doc)

    @staticmethod
    def print_pdf_with_settings(main_window, doc):
        total_pages = len(doc)
        if total_pages == 0:
            QMessageBox.warning(main_window, "Пустой PDF", "Файл не содержит страниц.")
            return

        # Создаём принтер
        printer = QPrinter(QPrinter.HighResolution)
        printer.setFromTo(1, total_pages)  # по умолчанию — все страницы

        # Настройки печати
        print_dialog = QPrintDialog(printer, main_window)
        print_dialog.setWindowTitle("Печать документа")

        # Включаем нужные опции
        print_dialog.setOption(QPrintDialog.PrintPageRange, True)
        print_dialog.setOption(QPrintDialog.PrintCollateCopies, True)
        print_dialog.setOption(QPrintDialog.PrintShowPageSize, True)
        print_dialog.setOption(QPrintDialog.PrintToFile, True)
        if print_dialog.exec() != QPrintDialog.Accepted:
            return

        # Получаем настройки
        mode = printer.printRange()
        printer_name = printer.printerName()
        copies = printer.copyCount()
        collate = printer.collateCopies()

        # Получаем список страниц
        pages_to_print = PDFPrinter._extract_pages_from_printer(printer, total_pages, mode)
        if not pages_to_print:
            QMessageBox.information(main_window, "Нет страниц", "Диапазон страниц пуст.")
            return

        # layout = printer.pageLayout()

        # тут уже всё в пикселях устройства, ничего считать заново не навдо
        paint_rect_px = printer.pageLayout().paintRectPixels(printer.resolution())
        paper_w_px = paint_rect_px.width()
        paper_h_px = paint_rect_px.height()

        # рендер на принтерном dpi
        render_dpi = min(printer.resolution(), 300)

        painter = QPainter(printer)

        progress = QProgressDialog("Печать...", "Отмена", 0, len(pages_to_print), main_window)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            for idx, page_num in enumerate(pages_to_print):
                progress.setValue(idx)
                QApplication.processEvents()
                if progress.wasCanceled():
                    break

                page = doc.load_page(page_num)
                rect = page.rect
                is_landscape = rect.width > rect.height

                # Рендерим с фиксированным DPI
                base_scale = render_dpi / PDFPrinter.points_per_inch
                mat = fitz.Matrix(base_scale, base_scale)
                pix = page.get_pixmap(matrix=mat)
                qimg = QImage.fromData(pix.tobytes("png"), "png")
                if qimg.isNull():
                    raise RuntimeError(f"Не удалось создать QImage для страницы {page_num + 1}")

                # Поворот для альбомных страниц
                if is_landscape:
                    transform = QTransform().rotate(90)
                    qimg = qimg.transformed(transform)

                # Размеры изображения после поворота
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
                target_rect = QRectF(target_x, target_y, scale_w, scale_h)

                painter.drawImage(target_rect, qimg)

                if idx < len(pages_to_print) - 1:
                    printer.newPage()
            msg = (
                f"Печать завершена!\n"
                f"Принтер: {printer_name or 'По умолчанию'}\n"
                f"Страниц: {len(pages_to_print)} из {total_pages}\n"
                f"Копий: {copies}, Коллация: {'Да' if collate else 'Нет'}"
            )
            QMessageBox.information(main_window, "Успех", msg)
        except Exception as e:
            QMessageBox.critical(main_window, "Ошибка печати", f"Произошла ошибка:\n{e}")
            # return
        finally:
            progress.close()
            painter.end()

    @staticmethod
    def _extract_pages_from_printer(printer, total_pages, mode):
        """
        Извлекает список страниц из QPrinter в зависимости от printRange().
        """
        pages = []

        if mode == QPrinter.PrintRange.PageRange:
            from_page = printer.fromPage()
            to_page = printer.toPage()
            if from_page <= 0:
                from_page = 1
            if to_page > total_pages:
                to_page = total_pages
            pages = list(range(from_page - 1, to_page))

        elif mode == QPrinter.PrintRange.AllPages:
            pages = list(range(total_pages))

        elif mode == QPrinter.PrintRange.CurrentPage:
            pages = [0]

        # Уникальные, отсортированные, валидные
        return sorted({p for p in pages if 0 <= p < total_pages})
