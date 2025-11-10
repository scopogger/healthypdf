import os
import shutil
import sys
import tempfile
from datetime import datetime
from typing import List, Optional

# PySide6
from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QProgressDialog, QApplication, QInputDialog, QLineEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QPainter, QImage
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtGui import QPageLayout

# Optional dependency used when we render to image for printing
try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

from settings_manager import settings_manager


# -----------------------------
# Helper
# -----------------------------

def messagebox_info(parent, title, message):
    QMessageBox.information(parent, title, message)


class ActionsHandler:
    """Wire up menus/toolbars and provide app actions compatible with the *new* UI
    while preserving behavior from the *old* implementation where possible.

    This class is defensive: it checks for the presence of attributes/methods
    on ui widgets so it can work across slightly different PDFViewer/Thumbnail
    implementations.
    """

    def __init__(self, main_window):
        self.main_window = main_window
        self.ui = main_window.ui
        self.recent_file_actions: list[QAction] = []

        # Connect everything
        self.connect_all_actions()

        # Build recents submenu
        self.update_recent_files_menu()

    # -----------------------------
    # Wiring
    # -----------------------------
    def connect_all_actions(self):
        """Connect all UI actions to their handlers"""
        self.connect_file_actions()
        self.connect_navigation_actions()
        self.connect_page_actions()
        self.connect_view_actions()
        self.connect_panel_actions()
        self.connect_recent_files_actions()
        self.connect_print_actions()
        self.connect_help_actions()

    def connect_file_actions(self):
        """Connect file menu actions"""
        if hasattr(self.ui, 'actionOpen'):
            self.ui.actionOpen.triggered.connect(self.open_file)
        if hasattr(self.ui, 'actionSave'):
            self.ui.actionSave.triggered.connect(self.save_file)
        if hasattr(self.ui, 'actionSaveAs'):
            self.ui.actionSaveAs.triggered.connect(self.save_file_as)
        if hasattr(self.ui, 'actionClosePdf'):
            self.ui.actionClosePdf.triggered.connect(self.close_file)
        if hasattr(self.ui, 'actionQuit'):
            self.ui.actionQuit.triggered.connect(self.main_window.close)
        if hasattr(self.ui, 'actionPasswordDoc'):
            self.ui.actionPasswordDoc.triggered.connect(self.toggle_password_for_current_document)
        if hasattr(self.ui, 'actionAddFile'):
            self.ui.actionAddFile.triggered.connect(self.add_file_to_document)

    def connect_navigation_actions(self):
        """Connect navigation actions"""
        if hasattr(self.ui, 'actionPrevious_Page'):
            self.ui.actionPrevious_Page.triggered.connect(self.previous_page)
        if hasattr(self.ui, 'actionNext_Page'):
            self.ui.actionNext_Page.triggered.connect(self.next_page)
        if hasattr(self.ui, 'actionJumpToFirstPage'):
            self.ui.actionJumpToFirstPage.triggered.connect(self.jump_to_first_page)
        if hasattr(self.ui, 'actionJumpToLastPage'):
            self.ui.actionJumpToLastPage.triggered.connect(self.jump_to_last_page)

    def connect_page_actions(self):
        """Connect page manipulation actions"""
        if hasattr(self.ui, 'actionDeletePage'):
            self.ui.actionDeletePage.triggered.connect(self.delete_current_page)
        if hasattr(self.ui, 'actionMovePageUp'):
            self.ui.actionMovePageUp.triggered.connect(self.move_page_up)
        if hasattr(self.ui, 'actionMovePageDown'):
            self.ui.actionMovePageDown.triggered.connect(self.move_page_down)
        if hasattr(self.ui, 'actionRotateCurrentPageClockwise'):
            self.ui.actionRotateCurrentPageClockwise.triggered.connect(self.rotate_page_clockwise)
        if hasattr(self.ui, 'actionRotateCurrentPageCounterclockwise'):
            self.ui.actionRotateCurrentPageCounterclockwise.triggered.connect(self.rotate_page_counterclockwise)
        if hasattr(self.ui, 'actionSave_Page_As_Image'):
            self.ui.actionSave_Page_As_Image.triggered.connect(self.save_current_page_as_image)
        if hasattr(self.ui, 'actionEnumeratePages'):
            self.ui.actionEnumeratePages.triggered.connect(self.enumerate_pages)

    def connect_help_actions(self):
        """Connect help menu actions"""
        if hasattr(self.ui, 'actionAboutPdf'):
            self.ui.actionAboutPdf.triggered.connect(self.show_pdf_info)
        if hasattr(self.ui, 'actionAbout'):
            self.ui.actionAbout.triggered.connect(self.show_about)

    def connect_view_actions(self):
        """Connect view actions"""
        if hasattr(self.ui, 'actionZoom_In'):
            self.ui.actionZoom_In.triggered.connect(self.zoom_in)
        if hasattr(self.ui, 'actionZoom_Out'):
            self.ui.actionZoom_Out.triggered.connect(self.zoom_out)
        if hasattr(self.ui, 'actionFitToWidth'):
            self.ui.actionFitToWidth.triggered.connect(self.fit_to_width)
        if hasattr(self.ui, 'actionFitToHeight'):
            self.ui.actionFitToHeight.triggered.connect(self.fit_to_height)
        if hasattr(self.ui, 'actionRotateViewClockwise'):
            self.ui.actionRotateViewClockwise.triggered.connect(self.rotate_view_clockwise)
        if hasattr(self.ui, 'actionRotateViewCounterclockwise'):
            self.ui.actionRotateViewCounterclockwise.triggered.connect(self.rotate_view_counterclockwise)

    def connect_panel_actions(self):
        """Connect panel actions"""
        if hasattr(self.ui, 'actionToggle_Panel'):
            self.ui.actionToggle_Panel.triggered.connect(self.toggle_side_panel)

    def connect_recent_files_actions(self):
        # submenu exists in the new UI
        if hasattr(self.ui, 'actionClearRecentFiles'):
            self.ui.actionClearRecentFiles.triggered.connect(self.clear_recent_files)

    def connect_print_actions(self):
        """Connect printing actions"""
        if hasattr(self.ui, 'actionPrint'):
            self.ui.actionPrint.triggered.connect(self.print_document)

    def toggle_password_for_current_document(self):
        """If current document has password -> ask to remove, else ask to set a new password."""
        pv = getattr(self.ui, 'pdfView', None)
        if not pv or not getattr(pv, 'doc_path', None):
            messagebox_info(self.main_window, "Внимание", "Сначала откройте документ.")
            return

        doc_path = pv.doc_path
        current_pw = getattr(pv, 'document_password', "") or ""

        if current_pw:
            # Есть пароль — предложить удалить
            reply = QMessageBox.question(
                self.main_window,
                "Удалить пароль",
                "Документ защищён паролем. Удалить пароль (разблокировать файл)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                ok = self._remove_password_for_file(doc_path, current_pw)
                if ok:
                    settings_manager.remove_encryption_password(doc_path)
                    messagebox_info(self.main_window, "Готово", "Пароль удалён и документ перезагружен.")
                    # Перезагружаем документ в UI (viewer + thumbnails)
                    try:
                        self.main_window.load_document(doc_path)
                    except Exception:
                        pass
                else:
                    QMessageBox.critical(self.main_window, "Ошибка",
                                         "Не удалось удалить пароль. Проверьте текущий пароль.")
        else:
            # Нет пароля — предложить задать
            pw, ok = QInputDialog.getText(self.main_window, "Установить пароль", "Введите новый пароль:",
                                          QLineEdit.Password)
            if not ok or not pw:
                return
            pw2, ok2 = QInputDialog.getText(self.main_window, "Подтверждение пароля", "Повторите пароль:",
                                            QLineEdit.Password)
            if not ok2 or pw != pw2:
                QMessageBox.warning(self.main_window, "Ошибка", "Пароли не совпадают или пустые.")
                return

            success = self._set_password_for_file(doc_path, pw, current_password_hint=current_pw)
            if success:
                # Пометить (опционально) в настройках
                try:
                    settings_manager.save_encryption_password(doc_path, pw)
                except Exception:
                    pass
                messagebox_info(self.main_window, "Готово", "Пароль установлен и документ перезагружен.")
                try:
                    self.main_window.load_document(doc_path)
                except Exception:
                    pass
            else:
                QMessageBox.critical(self.main_window, "Ошибка", "Не удалось установить пароль для файла.")

    def _set_password_for_file(self, file_path: str, new_password: str, current_password_hint: str = "") -> bool:
        """Save a password-protected copy over the original file.
        Strategy: open original with PyMuPDF (authenticate if needed), save to temp with encryption, replace file.
        """
        if fitz is None:
            QMessageBox.critical(self.main_window, "Ошибка", "PyMuPDF (fitz) не установлен — операция недоступна.")
            return False

        try:
            doc = fitz.open(file_path)
            if doc.needs_pass and current_password_hint:
                if not doc.authenticate(current_password_hint):
                    doc.close()
                    return False

            # Save to temp file with AES-256 encryption (owner & user same for simplicity)
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            try:
                # PyMuPDF encryption constants: fitz.PDF_ENCRYPT_AES_256
                # Use owner_pw and user_pw parameters.
                doc.save(tmp_path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=new_password, user_pw=new_password)
            except TypeError:
                # Older PyMuPDF signature fallback
                try:
                    doc.save(tmp_path, encryption=fitz.PDF_ENCRYPT_AES_256)
                    # If API doesn't accept owner_pw/user_pw, we can't set password reliably
                    doc.close()
                    return False
                except Exception as e:
                    doc.close()
                    print("save encryption failed:", e)
                    return False
            finally:
                doc.close()

            # Replace original with temp (atomic)
            shutil.move(tmp_path, file_path)
            return True

        except Exception as e:
            print(f"_set_password_for_file error: {e}")
            return False

    def _remove_password_for_file(self, file_path: str, current_password: str) -> bool:
        """Remove password by opening and saving plain copy, then replacing original."""
        if fitz is None:
            QMessageBox.critical(self.main_window, "Ошибка", "PyMuPDF (fitz) не установлен — операция недоступна.")
            return False

        try:
            doc = fitz.open(file_path)
            if doc.needs_pass:
                if not doc.authenticate(current_password):
                    doc.close()
                    return False

            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            try:
                # Save without encryption
                doc.save(tmp_path)
            finally:
                doc.close()

            shutil.move(tmp_path, file_path)
            return True

        except Exception as e:
            print(f"_remove_password_for_file error: {e}")
            return False

    def add_file_to_document(self):
        """Append another PDF to the current document and display the merged result"""
        pv = getattr(self.ui, 'pdfView', None)
        if not pv or not getattr(pv, 'document', None):
            QMessageBox.warning(self.main_window, "No Document", "Пожалуйста сначала откройте PDF документ.")
            return

        # Select file to merge
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Выберите PDF документ для добавления",
            "",
            "PDF Files (*.pdf)"
        )
        if not file_path:
            return

        try:
            # Open the document to append
            new_doc = fitz.open(file_path)
        except Exception as e:
            QMessageBox.critical(self.main_window, "Error", f"Failed to open file:\n{e}")
            return

        try:
            # Handle password protection for the new document
            if new_doc.needs_pass:
                authed = False
                for _ in range(3):
                    pw, ok = QInputDialog.getText(self.main_window, "Password",
                                                  f"Введите пароль для {os.path.basename(file_path)}:",
                                                  QLineEdit.Password)
                    if not ok:
                        break
                    if new_doc.authenticate(pw):
                        authed = True
                        break
                if not authed:
                    QMessageBox.critical(self.main_window, "Error", "Неверный пароль или операция была отменена.")
                    new_doc.close()
                    return

            # Get current document
            cur_doc = pv.document

            # Create a new merged document
            merged_doc = fitz.open()

            # Insert all pages from current document
            merged_doc.insert_pdf(cur_doc)

            # Insert all pages from new document (append to end)
            merged_doc.insert_pdf(new_doc)

            # Save merged document to a temporary file
            import tempfile
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            merged_doc.save(temp_path)
            merged_doc.close()
            new_doc.close()

            # Close current document properly
            pv.close_document()

            # Load the merged document
            success = pv.open_document(temp_path)

            if success:
                # Update the document path to the temp file
                pv.doc_path = temp_path

                # Update thumbnails
                if hasattr(self.ui, 'thumbnailList'):
                    try:
                        self.ui.thumbnailList.set_document(pv.document, pv.doc_path,
                                                           getattr(pv, 'document_password', None))
                    except Exception as e:
                        print(f"Thumbnail update failed: {e}")

                # Mark as modified and update UI
                pv.is_modified = True
                self.main_window.is_document_modified = True
                self.main_window.update_ui_state()
                self.main_window.update_page_info()

                QMessageBox.information(self.main_window, "Success", "Files merged successfully!")
            else:
                QMessageBox.critical(self.main_window, "Error", "Failed to load merged document.")

        except Exception as e:
            try:
                new_doc.close()
            except:
                pass
            QMessageBox.critical(self.main_window, "Merge Error", f"Error during merge operation: {e}")

    # -----------------------------
    # Helpers for page visibility/order (compatible with old & new viewers)
    # -----------------------------
    def get_visible_pages_as_original_indices(self) -> List[int]:
        visible_pages: List[int] = []
        pv = getattr(self.ui, 'pdfView', None)
        if not pv:
            return visible_pages
        # Old viewer exposed pages_info + deleted_pages
        if hasattr(pv, 'pages_info') and hasattr(pv, 'deleted_pages'):
            for info in pv.pages_info:
                if info.page_num not in pv.deleted_pages:
                    visible_pages.append(info.page_num)
            return visible_pages
        # Fallback: assume all pages by count
        total = self._get_total_pages()
        if total:
            visible_pages = list(range(total))
        return visible_pages

    def get_visible_pages_in_layout_order(self) -> List[int]:
        pv = getattr(self.ui, 'pdfView', None)
        if not pv:
            return []
        # Old viewer: walk the layout widgets to respect current order
        if hasattr(pv, 'pages_layout') and hasattr(pv, 'page_widgets'):
            order: List[int] = []
            layout = pv.pages_layout
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget() and not item.widget().isHidden():
                    widget = item.widget()
                    for j, pw in enumerate(pv.page_widgets):
                        if pw == widget:
                            order.append(j)
                            break
            return order
        # Newer viewer may keep a current layout list
        if hasattr(pv, 'visible_layout_indices'):
            return list(pv.visible_layout_indices)
        # Fallback to natural order
        total = self._get_total_pages()
        return list(range(total)) if total else []

    def _get_total_pages(self) -> int:
        pv = getattr(self.ui, 'pdfView', None)
        if not pv:
            return 0
        if hasattr(pv, 'get_total_pages'):
            try:
                return int(pv.get_total_pages())
            except Exception:
                pass
        if hasattr(pv, 'page_widgets') and pv.page_widgets is not None:
            return len(pv.page_widgets)
        if hasattr(pv, 'document') and pv.document is not None:
            try:
                return len(pv.document)
            except Exception:
                return 0
        return 0

    # -----------------------------
    # Recent files (new UI submenu-aware)
    # -----------------------------
    def update_recent_files_menu(self):
        menu = getattr(self.ui, 'menuOpenRecent', None)
        if not menu:
            return

        # Remove previous actions we added
        for act in self.recent_file_actions:
            try:
                menu.removeAction(act)
                act.deleteLater()
            except Exception:
                pass
        self.recent_file_actions.clear()

        recent_files = settings_manager.get_recent_files() or []
        max_items = getattr(settings_manager, 'MAX_RECENT_FILES', 10)

        if not recent_files:
            action = QAction("No recent files", menu)
            action.setEnabled(False)
            menu.addAction(action)
            self.recent_file_actions.append(action)
            return

        for i, file_path in enumerate(recent_files[:max_items]):
            text = f"{i + 1}. {os.path.basename(file_path)}"
            act = QAction(text, menu)
            act.setToolTip(file_path)
            # capture path correctly at definition time
            act.triggered.connect(lambda checked=False, p=file_path: self.open_recent_file(p))
            menu.addAction(act)
            self.recent_file_actions.append(act)

        # trailing separator + clear action if available
        clear_act = getattr(self.ui, 'actionClearRecentFiles', None)
        if clear_act:
            menu.addSeparator()
            menu.addAction(clear_act)

    def open_recent_file(self, file_path: str):
        if os.path.exists(file_path):
            self.main_window.load_document(file_path)
        else:
            QMessageBox.warning(
                self.main_window,
                "File Not Found",
                f"The file '{file_path}' no longer exists."
            )
            settings_manager.remove_recent_file(file_path)
            self.update_recent_files_menu()

    def clear_recent_files(self):
        reply = QMessageBox.question(
            self.main_window,
            "Удалить недавние",
            "Очистить список недавних файлов?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            settings_manager.clear_recent_files()
            self.update_recent_files_menu()

    # -----------------------------
    # File operations
    # -----------------------------
    def open_file(self):
        if getattr(self.main_window, 'is_document_modified', False):
            reply = self.main_window.ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Save and not self.save_file():
                return

        last_dir = settings_manager.get_last_directory()
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Open PDF",
            last_dir,
            "PDF Files (*.pdf)"
        )
        if file_path:
            settings_manager.save_last_directory(os.path.dirname(file_path))
            settings_manager.add_recent_file(file_path)
            self.update_recent_files_menu()
            self.main_window.load_document(file_path)

    def save_file(self) -> bool:
        # Prefer viewer-provided save if any
        pv = getattr(self.ui, 'pdfView', None)
        if not pv:
            return False

        # Some viewers expose merge/flatten step prior to save
        try:
            if hasattr(pv, 'merge_annotations_to_document'):
                pv.merge_annotations_to_document()
        except Exception:
            pass

        # Old API
        if hasattr(pv, 'save_changes'):
            success = bool(pv.save_changes())
            if success:
                self._mark_not_modified()
            return success

        # Newer API requires a target path
        current_path = getattr(self.main_window, 'current_document_path', '')
        if not current_path:
            return self.save_file_as()

        if hasattr(pv, 'save_document'):
            try:
                ok = bool(pv.save_document(current_path))
            except TypeError:
                # some implementations accept (path=None)
                ok = bool(pv.save_document())
            if ok:
                self._mark_not_modified()
                return True

        QMessageBox.critical(self.main_window, "Save Error", "Failed to save the document.")
        return False

    def save_file_as(self) -> bool:
        pv = getattr(self.ui, 'pdfView', None)
        if not pv:
            return False

        last_dir = settings_manager.get_last_directory()
        base = os.path.splitext(os.path.basename(getattr(self.main_window, 'current_document_path', '') or 'document'))[0]
        default_name = f"{base}_modified.pdf" if base else "document.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Save PDF As",
            os.path.join(last_dir, default_name),
            "PDF Files (*.pdf)"
        )
        if not file_path:
            return False

        settings_manager.save_last_directory(os.path.dirname(file_path))

        try:
            if hasattr(pv, 'merge_annotations_to_document'):
                pv.merge_annotations_to_document()
        except Exception:
            pass

        ok = False
        if hasattr(pv, 'save_changes'):
            ok = bool(pv.save_changes(file_path))
        elif hasattr(pv, 'save_document'):
            ok = bool(pv.save_document(file_path))

        if ok:
            self.main_window.current_document_path = file_path
            if hasattr(self.main_window, 'setWindowTitle'):
                filename = os.path.basename(file_path)
                self.main_window.setWindowTitle(f"PDF Editor - {filename}")
            self._mark_not_modified()
            settings_manager.add_recent_file(file_path)
            self.update_recent_files_menu()
            return True

        QMessageBox.critical(self.main_window, "Save Error", "Failed to save the document.")
        return False

    def close_file(self):
        if getattr(self.main_window, 'is_document_modified', False):
            reply = self.main_window.ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Save and not self.save_file():
                return

        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'close_document'):
            pv.close_document()

        # Clear thumbnails for both old and new widgets
        thumb = getattr(self.ui, 'thumbnailList', None)
        if thumb:
            for method in ('clear_thumbnails', 'clear', 'refresh_thumbnails'):
                if hasattr(thumb, method):
                    try:
                        getattr(thumb, method)()
                        break
                    except Exception:
                        pass

        self.main_window.current_document_path = ""
        self._mark_not_modified(update_title=True)
        if hasattr(self.main_window, 'update_page_info'):
            self.main_window.update_page_info()

    def _mark_not_modified(self, update_title: bool = False):
        self.main_window.is_document_modified = False
        if hasattr(self.main_window, 'update_ui_state'):
            self.main_window.update_ui_state()
        if update_title and hasattr(self.main_window, 'setWindowTitle'):
            self.main_window.setWindowTitle("PDF Editor")
        if hasattr(self.main_window, 'update_window_title'):
            self.main_window.update_window_title()

    # -----------------------------
    # Printing (prints only visible pages, preserving layout order). If the
    # viewer implements its own print_document(), we prefer that.
    # -----------------------------
    def print_document(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'print_document'):
            try:
                pv.print_document()
                return
            except Exception:
                pass

        if not pv or not hasattr(pv, 'document') or pv.document is None:
            messagebox_info(self.main_window, "Warning", "Please open a PDF file first.")
            return

        if fitz is None:
            QMessageBox.critical(
                self.main_window,
                "Print Error",
                "Printing requires PyMuPDF (fitz). Please install it to enable printing."
            )
            return

        # Configure printer and dialog
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self.main_window)
        if dialog.exec() != QPrintDialog.Accepted:
            return

        visible_pages_layout = self.get_visible_pages_in_layout_order()
        if not visible_pages_layout:
            QMessageBox.warning(self.main_window, "No Pages to Print", "No visible pages to print.")
            return

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.critical(self.main_window, "Print Error", "Cannot open print device.")
            return

        progress = QProgressDialog("Printing...", "Cancel", 0, len(visible_pages_layout), self.main_window)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            for idx, layout_index in enumerate(visible_pages_layout):
                progress.setValue(idx)
                QApplication.processEvents()
                if progress.wasCanceled():
                    break

                if idx > 0:
                    printer.newPage()

                # Map layout index to original index if viewer supports it
                page_num = layout_index
                if hasattr(pv, 'original_index_for_layout'):
                    try:
                        page_num = pv.original_index_for_layout(layout_index)
                    except Exception:
                        pass

                page = pv.document[page_num]

                # Apply temporary per-page rotation if the viewer tracks it
                rotation = 0
                if hasattr(pv, 'page_rotations'):
                    rotation = pv.page_rotations.get(page_num, 0)
                if rotation:
                    try:
                        page.set_rotation(rotation)
                    except Exception:
                        pass

                # Orientation
                pdf_rect = page.rect
                is_landscape = pdf_rect.width > pdf_rect.height
                page_layout = printer.pageLayout()
                if is_landscape and page_layout.orientation() == QPageLayout.Portrait:
                    printer.setPageLayout(QPageLayout(page_layout.pageSize(), QPageLayout.Landscape, page_layout.margins()))

                # Render
                zoom = 2
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

                paint_rect = printer.pageRect(QPrinter.DevicePixel)
                scaled = image.scaled(paint_rect.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

                x = paint_rect.x() + (paint_rect.width() - scaled.width()) // 2
                y = paint_rect.y() + (paint_rect.height() - scaled.height()) // 2
                target = paint_rect.adjusted(
                    x - paint_rect.x(), y - paint_rect.y(),
                    -(paint_rect.width() - (x - paint_rect.x()) - scaled.width()),
                    -(paint_rect.height() - (y - paint_rect.y()) - scaled.height()),
                )
                painter.drawImage(target, scaled)
        except Exception as e:
            QMessageBox.critical(self.main_window, "Print Error", f"Error occurred while printing: {e}")
        finally:
            painter.end()
            progress.close()

    # -----------------------------
    # Navigation (respect layout order when available)
    # -----------------------------
    def previous_page(self):
        pv = getattr(self.ui, 'pdfView', None)
        if not pv:
            return

        if hasattr(pv, 'previous_page'):
            pv.previous_page()
            return

        if hasattr(pv, 'get_current_page') and hasattr(pv, 'layout_index_for_original'):
            current_original = pv.get_current_page()
            current_layout = pv.layout_index_for_original(current_original)
            vis = self.get_visible_pages_in_layout_order()
            if current_layout in vis:
                i = vis.index(current_layout)
                if i > 0:
                    pv.go_to_page(vis[i - 1])

    def next_page(self):
        pv = getattr(self.ui, 'pdfView', None)
        if not pv:
            return

        if hasattr(pv, 'next_page'):
            pv.next_page()
            return

        if hasattr(pv, 'get_current_page') and hasattr(pv, 'layout_index_for_original'):
            current_original = pv.get_current_page()
            current_layout = pv.layout_index_for_original(current_original)
            vis = self.get_visible_pages_in_layout_order()
            if current_layout in vis:
                i = vis.index(current_layout)
                if i < len(vis) - 1:
                    pv.go_to_page(vis[i + 1])

    def jump_to_first_page(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'go_to_page'):
            vis = self.get_visible_pages_in_layout_order()
            if vis:
                pv.go_to_page(vis[0])

    def jump_to_last_page(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'go_to_page'):
            vis = self.get_visible_pages_in_layout_order()
            if vis:
                pv.go_to_page(vis[-1])

    # -----------------------------
    # View ops
    # -----------------------------
    def _update_zoom_selector(self, zoom_value: Optional[float] = None):
        selector = getattr(self.ui, 'm_zoomSelector', None)
        pv = getattr(self.ui, 'pdfView', None)
        if selector and hasattr(selector, 'set_zoom_value'):
            if zoom_value is None:
                for attr in ('zoom_factor', 'zoom_level'):
                    if hasattr(pv, attr):
                        zoom_value = getattr(pv, attr)
                        break
            if zoom_value is not None:
                selector.set_zoom_value(float(zoom_value))

    def zoom_in(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'zoom_in'):
            pv.zoom_in()
        elif hasattr(pv, 'set_zoom'):
            current = getattr(pv, 'zoom_level', 1.0)
            pv.set_zoom(min(5.0, current * 1.25))
        self._update_zoom_selector()

    def zoom_out(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'zoom_out'):
            pv.zoom_out()
        elif hasattr(pv, 'set_zoom'):
            current = getattr(pv, 'zoom_level', 1.0)
            pv.set_zoom(max(0.1, current * 0.8))
        self._update_zoom_selector()

    def fit_to_width(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'fit_to_width'):
            pv.fit_to_width()
        self._update_zoom_selector()

    def fit_to_height(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'fit_to_height'):
            pv.fit_to_height()
        self._update_zoom_selector()

    def rotate_view_clockwise(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'rotate_view'):
            pv.rotate_view(90)

    def rotate_view_counterclockwise(self):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, 'rotate_view'):
            pv.rotate_view(-90)

    # -----------------------------
    # Panel ops (respecting new splitter sizing)
    # -----------------------------
    def toggle_side_panel(self):
        if not hasattr(self.ui, 'sidePanelContent'):
            return
        is_visible = self.ui.sidePanelContent.isVisible()

        if not is_visible:
            self.ui.sidePanelContent.show()
            # Prefer opening the Pages tab
            for name in ('pagesButton', 'pagesTab'):
                w = getattr(self.ui, name, None)
                if hasattr(w, 'setChecked'):
                    w.setChecked(True)
                if hasattr(w, 'show'):
                    w.show()

            if hasattr(self.ui, 'splitter'):
                sizes = self.ui.splitter.sizes()
                total = sum(sizes) if sizes else self.main_window.width()
                tab_buttons_width = 25
                # Try to restore preferred width from settings if present
                try:
                    _, panel_width, _ = settings_manager.load_panel_state()
                except Exception:
                    panel_width = 150
                panel_width = max(150, min(300, int(panel_width or 150)))
                self.ui.splitter.setSizes([tab_buttons_width, panel_width, max(400, total - tab_buttons_width - panel_width)])
        else:
            self.ui.sidePanelContent.hide()
            if hasattr(self.ui, 'splitter'):
                total = sum(self.ui.splitter.sizes())
                self.ui.splitter.setSizes([25, 0, max(0, total - 25)])

    # -----------------------------
    # Page edits
    # -----------------------------
    def delete_current_page(self):
        pv = getattr(self.ui, 'pdfView', None)
        if not pv or (hasattr(pv, 'document') and pv.document is None):
            return

        total = self._get_total_pages()
        if total <= 1:
            QMessageBox.warning(self.main_window, "Cannot Delete Page", "Cannot delete the last remaining page.")
            return

        # reply = QMessageBox.question(
        #     self.main_window,
        #     "Delete Page",
        #     "Are you sure you want to delete the current page?",
        #     QMessageBox.Yes | QMessageBox.No,
        #     QMessageBox.No,
        # )
        # if reply != QMessageBox.Yes:
        #     return

        if hasattr(pv, 'get_current_page'):
            current_page = pv.get_current_page()
        else:
            current_page = None

        success = False
        for method in ('delete_current_page',):
            if hasattr(pv, method):
                try:
                    success = bool(getattr(pv, method)())
                    break
                except Exception:
                    pass
        if not success:
            return

        # Mark modified and update UI bits
        if hasattr(self.main_window, 'on_document_modified'):
            self.main_window.on_document_modified(True)
        else:
            self.main_window.is_document_modified = True
        if hasattr(self.main_window, 'update_ui_state'):
            self.main_window.update_ui_state()
        if hasattr(self.main_window, 'update_window_title'):
            self.main_window.update_window_title()

        # Thumbnail updates
        thumb = getattr(self.ui, 'thumbnailList', None)
        if thumb:
            if current_page is not None and hasattr(thumb, 'hide_page_thumbnail'):
                try:
                    thumb.hide_page_thumbnail(current_page)
                except Exception:
                    pass
            for method in ('refresh_thumbnails', 'update_thumbnails_order'):
                if hasattr(thumb, method):
                    try:
                        # When reordering, use original indices if we can
                        if method == 'update_thumbnails_order':
                            thumb.update_thumbnails_order(self.get_visible_pages_as_original_indices())
                        else:
                            getattr(thumb, method)()
                    except Exception:
                        pass
            try:
                if hasattr(pv, 'get_current_page') and hasattr(thumb, 'set_current_page'):
                    thumb.set_current_page(pv.get_current_page())
            except Exception:
                pass

    def save_current_page_as_image(self):
        """Сохранить текущую страницу как изображение с настройками качества"""
        pv = getattr(self.ui, 'pdfView', None)
        if not pv or not hasattr(pv, 'document') or pv.document is None:
            QMessageBox.warning(self.main_window, "Нет документа", "Пожалуйста, сначала откройте PDF файл.")
            return

        # Получить текущую страницу
        current_original_page = pv.get_current_page()
        if current_original_page is None:
            QMessageBox.warning(self.main_window, "Ошибка", "Не удалось определить текущую страницу.")
            return

        # Запрос качества/уровня масштабирования
        zoom_levels = {
            "Среднее (72 DPI)": 1.0,
            "Хорошее (150 DPI)": 2.0,
            "Высокое (300 DPI)": 4.0,
            "Очень высокое (600 DPI)": 8.0
        }

        quality, ok = QInputDialog.getItem(
            self.main_window,
            "Качество изображения",
            "Выберите качество изображения:",
            list(zoom_levels.keys()),
            1,  # По умолчанию "Хорошее"
            False
        )

        if not ok:
            return

        zoom = zoom_levels[quality]

        # Диалог сохранения файла
        last_dir = settings_manager.get_last_directory()
        default_name = f"страница_{current_original_page + 1}_{quality.replace(' ', '_').lower()}.png"

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self.main_window,
            f"Сохранить страницу как изображение ({quality})",
            os.path.join(last_dir, default_name),
            "Изображения PNG (*.png);;Изображения JPEG (*.jpg *.jpeg);;Изображения BMP (*.bmp);;Все файлы (*)"
        )

        if not file_path:
            return

        # Определить формат из расширения файла или выбранного фильтра
        if selected_filter.startswith("PNG") or file_path.lower().endswith('.png'):
            format = 'PNG'
            quality_param = 100
        elif selected_filter.startswith("JPEG") or file_path.lower().endswith(('.jpg', '.jpeg')):
            format = 'JPEG'
            quality_param = 95
            if not file_path.lower().endswith(('.jpg', '.jpeg')):
                file_path += '.jpg'
        else:  # BMP или другие
            format = 'BMP'
            quality_param = 100
            if not file_path.lower().endswith('.bmp'):
                file_path += '.bmp'

        try:
            # Показать прогресс
            progress = QProgressDialog("Формирование страницы...", "Отмена", 0, 100, self.main_window)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            QApplication.processEvents()

            # Получить страницу
            page = pv.document[current_original_page]

            # Применить поворот если есть
            rotation = pv.page_rotations.get(current_original_page, 0)
            if rotation != 0:
                page.set_rotation(rotation)

            # Создать матрицу для рендеринга
            matrix = fitz.Matrix(zoom, zoom)

            progress.setValue(50)
            QApplication.processEvents()

            if progress.wasCanceled():
                return

            # Преобразовать страницу в изображение
            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)

            progress.setValue(80)
            QApplication.processEvents()

            # Конвертировать в QImage
            img_data = pix.tobytes("ppm")
            image = QImage()
            image.loadFromData(img_data)

            if image.isNull():
                QMessageBox.critical(self.main_window, "Ошибка", "Не удалось преобразовать страницу в изображение.")
                return

            progress.setValue(90)
            QApplication.processEvents()

            # Сохранить изображение
            success = image.save(file_path, format, quality_param)

            progress.close()

            if success:
                QMessageBox.information(self.main_window, "Успешно",
                                        f"Страница {current_original_page + 1} сохранена в качестве {quality}!\n\n"
                                        f"Файл: {os.path.basename(file_path)}\n"
                                        f"Размер: {image.width()} x {image.height()} пикселей")
                settings_manager.save_last_directory(os.path.dirname(file_path))
            else:
                QMessageBox.critical(self.main_window, "Ошибка", "Не удалось сохранить файл изображения.")

        except Exception as e:
            try:
                progress.close()
            except:
                pass
            QMessageBox.critical(self.main_window, "Ошибка",
                                 f"Не удалось сохранить страницу как изображение:\n{str(e)}")

    def show_pdf_info(self):
        """Показать детальную техническую информацию о текущем PDF документе"""
        pv = getattr(self.ui, 'pdfView', None)
        if not pv or not hasattr(pv, 'document') or pv.document is None:
            QMessageBox.information(self.main_window, "Информация о PDF",
                                    "В настоящее время PDF документ не открыт.")
            return

        try:
            doc = pv.document
            doc_path = getattr(pv, 'doc_path', 'Неизвестно')

            # Сбор комплексной информации о PDF
            info = doc.metadata
            page_count = len(doc)

            # Информация о файле
            file_size = "Неизвестно"
            file_date = "Неизвестно"
            if os.path.exists(doc_path):
                size_bytes = os.path.getsize(doc_path)
                file_size = self._format_file_size(size_bytes)
                file_date = datetime.fromtimestamp(os.path.getmtime(doc_path)).strftime('%Y-%m-%d %H:%M:%S')

            # Технические свойства документа
            is_encrypted = doc.is_encrypted
            needs_pass = doc.needs_pass
            can_save = not getattr(doc, 'can_save_incrementally', lambda: True)()
            is_repaired = getattr(doc, 'is_repaired', False)
            is_pdf = getattr(doc, 'is_pdf', True)

            # Check if document has bookmarks
            has_bookmarks = "Нет"
            try:
                # Try to get bookmarks using PyMuPDF
                toc = doc.get_toc()
                has_bookmarks = "Да" if toc else "Нет"

                # If there are bookmarks, show how many
                if toc:
                    bookmark_count = len(toc)
                    has_bookmarks = f"Да: {bookmark_count}"
            except Exception:
                # If we can't check bookmarks, show unknown
                has_bookmarks = "Неизвестно"

            # Получить информацию о шифровании, если доступно
            encryption_info = ""
            if is_encrypted:
                try:
                    encrypt_method = getattr(doc, 'get_encryption_method', lambda: 'Неизвестно')()
                    encrypt_bits = getattr(doc, 'get_encryption_strength', lambda: 0)()
                    encryption_info = f"{encrypt_method} ({encrypt_bits} бит)"
                except:
                    encryption_info = "Зашифрован"

            # Информация о страницах
            visible_pages = pv.get_visible_page_count() if hasattr(pv, 'get_visible_page_count') else page_count
            deleted_pages = len(getattr(pv, 'deleted_pages', set()))
            rotated_pages = len(getattr(pv, 'page_rotations', {}))

            # Получить размеры первой страницы для справки
            page_dimensions = ""
            if page_count > 0:
                try:
                    first_page = doc[0]
                    rect = first_page.rect
                    page_dimensions = f"{rect.width:.1f} x {rect.height:.1f} пунктов"
                except:
                    page_dimensions = "Неизвестно"

            # Построение комплексного информационного сообщения
            message = f"""
    <b>Информация о PDF документе</b>
    <br><br>

    <b>Информация о файле:</b><br>
    • <b>Имя:</b> {os.path.basename(doc_path)}<br>
    • <b>Путь:</b> {doc_path}<br>
    • <b>Размер:</b> {file_size}<br>
    • <b>Изменен:</b> {file_date}<br>
    <br>

    <b>Структура документа:</b><br>
    • <b>Всего страниц:</b> {page_count}<br>
    • <b>Видимые страницы:</b> {visible_pages}<br>
    • <b>Удаленные страницы:</b> {deleted_pages}<br>
    • <b>Повернутые страницы:</b> {rotated_pages}<br>
    • <b>Размер страницы (первая):</b> {page_dimensions}<br>
    <br>

    <b>Безопасность:</b><br>
    • <b>Зашифрован:</b> {'Да' if is_encrypted else 'Нет'}<br>
    • <b>Защищен паролем:</b> {'Да' if needs_pass else 'Нет'}<br>
    • <b>Метод шифрования:</b> {encryption_info}<br>
    • <b>Восстановлен:</b> {'Да' if is_repaired else 'Нет'}<br>
    <br>

    <b>Технические свойства:</b><br>
    • <b>Версия PDF:</b> {getattr(doc, 'pdf_version', 'Неизвестно')}<br>
    • <b>Инкрементное сохранение:</b> {'Нет' if can_save else 'Да'}<br>
    • <b>Закладки:</b> {has_bookmarks}<br>
    • <b>Корректный PDF:</b> {'Да' if is_pdf else 'Нет'}<br>
    <br>

    <b>Метаданные:</b><br>
    • <b>Заголовок:</b> {info.get('title', 'Не указан')}<br>
    • <b>Автор:</b> {info.get('author', 'Не указан')}<br>
    • <b>Тема:</b> {info.get('subject', 'Не указан')}<br>
    • <b>Ключевые слова:</b> {info.get('keywords', 'Не указаны')}<br>
    • <b>Создатель:</b> {info.get('creator', 'Не указан')}<br>
    • <b>Производитель:</b> {info.get('producer', 'Не указан')}<br>
    • <b>Дата создания:</b> {self._parse_pdf_date(info.get('creationDate', 'Не указана'))}<br>
    • <b>Дата изменения:</b> {self._parse_pdf_date(info.get('modDate', 'Не указана'))}<br>
    <br>

    <b>Состояние просмотрщика:</b><br>
    • <b>Текущий масштаб:</b> {getattr(pv, 'zoom_level', 1.0):.1%}<br>
    • <b>Текущая страница:</b> {pv.get_current_page() + 1 if hasattr(pv, 'get_current_page') else 'Неизвестно'}<br>
    • <b>Документ изменен:</b> {'Да' if getattr(pv, 'is_modified', False) else 'Нет'}<br>
    • <b>Аннотации:</b> {len(getattr(pv, 'page_annotations', {}))} страниц с аннотациями<br>
    """

            # Создать и показать окно сообщения
            msg_box = QMessageBox(self.main_window)
            msg_box.setWindowTitle(f"Информация о PDF - {os.path.basename(doc_path)}")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(message)

            # Сделать диалог больше, чтобы показать всю информацию
            msg_box.resize(600, 700)

            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec()

        except Exception as e:
            QMessageBox.critical(self.main_window, "Ошибка",
                                 f"Не удалось получить информацию о PDF:\n{str(e)}")

    def _format_file_size(self, size_bytes):
        """Format file size in human-readable format"""
        if size_bytes == 0:
            return "0 bytes"

        size_names = ["bytes", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.1f} {size_names[i]}"

    def _parse_pdf_date(self, pdf_date_str):
        """Parse PDF date string and convert to human-readable format with time"""
        if not pdf_date_str or pdf_date_str == 'Не указана':
            return 'Не указана'

        try:
            # PDF dates are in format: D:YYYYMMDDHHmmSSOHH'mm'
            # Example: D:20231225143000+03'00'

            if pdf_date_str.startswith('D:'):
                date_str = pdf_date_str[2:]
            else:
                date_str = pdf_date_str

            # Extract date and time components
            year = int(date_str[0:4]) if len(date_str) >= 4 else 2023
            month = int(date_str[4:6]) if len(date_str) >= 6 else 1
            day = int(date_str[6:8]) if len(date_str) >= 8 else 1

            # Extract time components if available
            hour = int(date_str[8:10]) if len(date_str) >= 10 else 0
            minute = int(date_str[10:12]) if len(date_str) >= 12 else 0
            second = int(date_str[12:14]) if len(date_str) >= 14 else 0

            from datetime import datetime
            date_obj = datetime(year, month, day, hour, minute, second)

            # Format in Russian
            months_ru = {
                1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
                5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
                9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
            }

            if hour == 0 and minute == 0 and second == 0:
                # Only date, no time
                return f"{day} {months_ru.get(month, 'января')} {year} года"
            else:
                # Date with time
                return f"{day} {months_ru.get(month, 'января')} {year} года, {hour:02d}:{minute:02d}"

        except Exception as e:
            print(f"Error parsing PDF date '{pdf_date_str}': {e}")
            return pdf_date_str

    def show_about(self):
        """Показать детальную информацию о приложении"""
        # Вы можете определить эти константы версий в начале файла или класса
        APP_NAME = "Редактор документов АльтPDF"
        APP_VERSION = "0.8.1"
        APP_DESCRIPTION = "Мощное кроссплатформенное приложение для просмотра и редактирования PDF документов"

        about_text = f"""
    <b>{APP_NAME} v{APP_VERSION}</b>
    <br><br>
    {APP_DESCRIPTION}
    <br><br>
    <u>Основные возможности:</u>
    • Просмотр и навигация по PDF документам
    • Аннотации и инструменты рисования на страницах
    • Манипуляции со страницами (поворот, удаление, перестановка)
    • Экспорт страниц как изображений
    • Управление парольной защитой
    • Навигация с помощью миниатюр
    • Расширенные опции масштабирования и подгонки
    • Высококачественная печать
    <br><br>
    <u>Создано с использованием:</u>
    • <b>PySide6</b> - Кроссплатформенный GUI фреймворк
    • <b>PyMuPDF</b> - Высокопроизводительная обработка PDF
    • <b>Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}</b> - Язык программирования
    <br><br>
    <u>Библиотеки и зависимости:</u>
    • Qt {self._get_qt_version()} - Фреймворк приложения
    • Fitz - Движок рендеринга PDF
    • Стандартные библиотеки Python
    <br><br>
    <u>Назначение приложения:</u>
    Это приложение предоставляет комплексные возможности редактирования PDF для производственного использования, включая рисование в документах, управление страницами и конвертацию форматов.
    <br><br>
    <small>Создано с использованием современных Python библиотек для эффективной обработки PDF и интуитивного пользовательского опыта по заказу ПАО СургутНефтегаз.</small>
    """

        msg_box = QMessageBox(self.main_window)
        msg_box.setWindowTitle(f"О программе {APP_NAME}")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(about_text)

        # Сделать диалог немного больше для размещения всего текста
        msg_box.resize(500, 600)

        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    def _get_qt_version(self):
        """Получить строку версии Qt"""
        try:
            from PySide6.QtCore import qVersion
            return qVersion()
        except:
            return "Неизвестно"

    def move_page_up(self):
        self._move_page_generic('move_page_up')

    def move_page_down(self):
        self._move_page_generic('move_page_down')

    def _move_page_generic(self, method_name: str):
        pv = getattr(self.ui, 'pdfView', None)
        if hasattr(pv, method_name):
            try:
                success = bool(getattr(pv, method_name)())
            except Exception:
                success = False
            if success:
                if hasattr(self.main_window, 'on_document_modified'):
                    self.main_window.on_document_modified(True)
                else:
                    self.main_window.is_document_modified = True
                if hasattr(self.main_window, 'update_page_info'):
                    self.main_window.update_page_info()
                if hasattr(self.main_window, 'update_ui_state'):
                    self.main_window.update_ui_state()
                if hasattr(self.main_window, 'update_window_title'):
                    self.main_window.update_window_title()

                # Thumbnails follow original indices to match viewer's layout
                thumb = getattr(self.ui, 'thumbnailList', None)
                if thumb and hasattr(thumb, 'update_thumbnails_order'):
                    try:
                        thumb.update_thumbnails_order(self.get_visible_pages_as_original_indices())
                        if hasattr(pv, 'get_current_page') and hasattr(thumb, 'set_current_page'):
                            thumb.set_current_page(pv.get_current_page())
                    except Exception:
                        pass

    def rotate_page_clockwise(self):
        self._rotate_page_generic(90)

    def rotate_page_counterclockwise(self):
        self._rotate_page_generic(-90)

    def _rotate_page_generic(self, delta: int):
        pv = getattr(self.ui, 'pdfView', None)
        method = 'rotate_page_clockwise' if delta > 0 else 'rotate_page_counterclockwise'
        success = False
        if hasattr(pv, method):
            try:
                success = bool(getattr(pv, method)())
            except Exception:
                success = False
        if not success and hasattr(pv, 'rotate_page'):
            try:
                success = bool(pv.rotate_page(delta))
            except Exception:
                success = False

        if success:
            if hasattr(self.main_window, 'on_document_modified'):
                self.main_window.on_document_modified(True)
            else:
                self.main_window.is_document_modified = True
            # Update corresponding thumbnail preview if supported
            thumb = getattr(self.ui, 'thumbnailList', None)
            if thumb and hasattr(pv, 'get_current_page'):
                cur = pv.get_current_page()
                for meth in ('rotate_page_thumbnail', 'refresh_thumbnails'):
                    if hasattr(thumb, meth):
                        try:
                            if meth == 'rotate_page_thumbnail':
                                thumb.rotate_page_thumbnail(cur, delta)
                            else:
                                thumb.refresh_thumbnails()
                            break
                        except Exception:
                            pass
