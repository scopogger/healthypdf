import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

import pypdf
import fitz
import win32com.client as win32

from PySide6.QtCore import Slot, QUrl, QPoint, QModelIndex, QStandardPaths, Qt, QThreadPool, QObject, QRunnable, Signal, \
    QTimer, QSize, QRect
from PySide6.QtGui import QImage, QPixmap, QPageLayout, QPainter, QPageSize
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import QMessageBox, QFileDialog, QDialog, QLabel, QScrollArea, QWidget, QVBoxLayout, \
    QListWidgetItem, QSizePolicy, QGroupBox, QRadioButton, QHBoxLayout, QSpinBox, QPushButton, QApplication, QMenu

from page_operation_dialog import PageOperationDialog
from settings_manager import settings_manager


class ActionsHandler:
    def __init__(self, main_window):
        self.main_window = main_window
        self.ui_module = main_window.ui

        self.pdf_viewer = main_window.ui.pdfView
        # Remove the pdf_viewer_doc object as it's now managed by the new viewer

        self.file_dialog = None

        self.current_file_path = None
        self.temp_file_path = None
        self.visual_rotation_degree = 0  # Track visual rotations

        self.fileModified = False
        self.tempFileOpen = False
        self.fileOpen = False
        self.in_draw_mode = False

        self.initialize_bookmarks_panel()
        self.initialize_thumbnail_components()

        connect_ui_actions(self)

    def load_document(self, file_path):
        """Loads and displays the selected PDF file."""
        if self.pdf_viewer.open_document(file_path):
            # Cancel any ongoing thumbnail generation
            self.cancel_thumbnail_generation = True

            if file_path != self.temp_file_path:
                self.tempFileOpen = False
                self.fileOpen = True
                self.current_file_path = file_path
                settings_manager.save_last_directory(
                    os.path.dirname(file_path))  # Save last used directory for open files
            else:
                self.tempFileOpen = True
                self.fileOpen = False

            self.set_window_title(self.current_file_path)
            self.setup_document_view()
            self.ui_module.m_pageInput.setText("1")
            self.ui_module.thumbnailList.clear()
            self.restart_thumbnail_timer()
            return True
        return False

    def setup_document_view(self):
        """Initializes the document view."""
        # The new viewer handles the document itself, so we just need to update UI
        if not self.tempFileOpen:
            # Set initial page
            self.pdf_viewer.jump_to_page(0)
            # Update bookmarks if needed
            if hasattr(self, 'bookmark_model'):
                # You may need to create a custom solution for bookmarks
                pass
        self.update_page_display(0)

    @Slot()
    def on_actionOpen_triggered(self):
        """Slot for handling the 'Open' action"""
        self.open_file_dialog()

    def open_file_dialog(self):
        """Opens a file dialog to select a PDF file"""
        directory = settings_manager.get_last_directory()

        if not self.file_dialog:
            self.file_dialog = self.create_file_dialog(directory)
        else:
            self.file_dialog.setDirectory(directory)

        if self.file_dialog.exec() == QFileDialog.Accepted:
            selected_file_url = self.file_dialog.selectedUrls()[0]
            if selected_file_url.isValid():
                # Close current document if open
                if self.pdf_viewer.doc:
                    # Check for unsaved changes
                    if self.fileModified:
                        response = self.prompt_save_unsaved_changes()
                        if response == QMessageBox.Yes:
                            # Save changes
                            self.on_actionSave_triggered()
                        elif response == QMessageBox.Cancel:
                            return  # Cancel open if user doesn't want to discard changes

                    # Close current document and reset UI
                    self.pdf_viewer.close_document()
                    self.reset_ui_after_close()

                # Reset state variables
                self.visual_rotation_degree = 0
                self.fileModified = False
                self.tempFileOpen = False
                self.fileOpen = True

                # Delete temp file if it exists
                if self.temp_file_path and os.path.exists(self.temp_file_path):
                    try:
                        os.remove(self.temp_file_path)
                        self.temp_file_path = None
                    except OSError as e:
                        print(f"Ошибка при удалении временного файла: {e}")

                # Open the new document
                self.open_in_viewer(selected_file_url)

    def open_in_viewer(self, doc_location):
        """Try to process the PDF file path or URL and open it."""
        if isinstance(doc_location, QUrl):
            if doc_location.isLocalFile():
                file_path = doc_location.toLocalFile()
            else:
                messagebox_crit(self.main_window, "Ошибка при открытии",
                                f"{doc_location} недействительный локальный файл")
                return
        else:
            file_path = doc_location  # Assume it's already a file path string

        if not self.load_document(file_path):
            messagebox_crit(self.main_window, "Ошибка при открытии", f"Не удалось открыть файл по пути: {file_path}")

    @Slot(int)
    def update_page_display(self, page_number):
        total_pages = self.pdf_viewer.page_count()
        self.ui_module.m_pageInput.setText(str(page_number + 1))
        self.ui_module.m_pageLabel.setText(f"/ {total_pages}")

        if self.fileModified:
            self.update_status_bar(self.temp_file_path, page_number)
            self.tempFileOpen = True
            self.fileOpen = False
        else:
            self.update_status_bar(self.current_file_path, page_number)
            self.tempFileOpen = False
            self.fileOpen = True

    def on_actionClosePdf_triggered(self):
        """Closes the current PDF, resets the viewer, and deletes temp files."""
        if not self.pdf_viewer.doc:
            return  # No open PDF files check

        if self.fileModified:
            response = self.prompt_save_unsaved_changes()
            if response == QMessageBox.Yes:
                # Save changes
                self.on_actionSave_triggered()
            elif response == QMessageBox.Cancel:
                # Cancel the close action
                return

        # Close the PDF document
        self.pdf_viewer.close_document()

        # Proceed with resetting the UI
        self.reset_ui_after_close()
        self.visual_rotation_degree = 0
        self.fileModified = False
        self.tempFileOpen = False
        self.fileOpen = False

        # Cancel any ongoing thumbnail generation
        self.cancel_thumbnail_generation = True

        # Delete the temporary file if it exists
        if self.temp_file_path and os.path.exists(self.temp_file_path):
            try:
                os.remove(self.temp_file_path)
                self.temp_file_path = None  # Clear the reference after deletion
            except OSError as e:
                print(f"Ошибка при удалении временного файла: {e}")

    @Slot()
    def on_actionSave_triggered(self):
        """Save the modified PDF, rotating back if necessary."""
        self.pdf_viewer.save_to_original()

        # if self.fileModified and self.temp_file_path:
        #     try:
        #         # Rotate tempfile backwards if visual_rotation_degree is not 0
        #         if self.visual_rotation_degree != 0:
        #             rotate_pdf_pages(self.temp_file_path, -self.visual_rotation_degree)
        #
        #         shutil.copyfile(self.temp_file_path, self.current_file_path)
        #         messagebox_info(self.main_window, "Файл сохранён", "PDF файл успешно сохранён!")
        #         self.fileModified = False
        #     except Exception as e:
        #         messagebox_warn(self.main_window, "Ошибка", f"Не удалось сохранить файл: {str(e)}")
        # else:
        #     messagebox_warn(self.main_window, "Нет изменений",
        #                     "Файл не был модифицирован, пересохранения не произошло.")

    @Slot()
    def on_actionSaveAs_triggered(self):
        """Save the current PDF file to a new location."""
        self.pdf_viewer.save_copy()

        # if not self.fileOpen and not self.tempFileOpen:
        #     messagebox_warn(self.main_window, "Ошибка", "Нет открытого файла для сохранения.")
        #     return
        #
        # # Extract the default file name from the current file path
        # default_file_name = os.path.basename(self.current_file_path) if self.current_file_path else "Untitled.pdf"
        # default_dir = os.path.dirname(self.current_file_path) if self.current_file_path else os.getcwd()
        #
        # # Create and configure file dialog
        # file_dialog = self.create_file_dialog(default_dir)
        # file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        # file_dialog.setDefaultSuffix("pdf")
        # file_dialog.selectFile(default_file_name)  # Set the default file name
        #
        # if file_dialog.exec() == QFileDialog.Accepted:
        #     new_file_path = file_dialog.selectedFiles()[0]
        #     if not new_file_path.endswith(".pdf"):
        #         new_file_path += ".pdf"
        #
        #     try:
        #         # Save the file depending on its state
        #         self._save_file_to_path(new_file_path)
        #
        #         # Update states
        #         self.current_file_path = new_file_path
        #         self.set_window_title(self.current_file_path)
        #         self.fileModified = False
        #         self.tempFileOpen = False
        #         self.fileOpen = True
        #         self.visual_rotation_degree = 0  # Reset rotation
        #
        #         messagebox_info(self.main_window, "Файл сохранён", f"PDF файл успешно сохранён как {new_file_path}!")
        #     except Exception as e:
        #         messagebox_warn(self.main_window, "Ошибка", f"Не удалось сохранить файл: {str(e)}")

    def _save_file_to_path(self, new_file_path):
        """Helper method to handle file saving."""
        # Ensure target directory exists
        target_dir = os.path.dirname(new_file_path)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        # Handle saving based on file state
        if self.tempFileOpen and self.temp_file_path:
            # Rotate tempfile backwards if visual_rotation_degree is not 0
            if self.visual_rotation_degree != 0:
                rotate_pdf_pages(self.temp_file_path, -self.visual_rotation_degree)

            shutil.copyfile(self.temp_file_path, new_file_path)
        elif self.fileOpen and self.current_file_path:
            shutil.copyfile(self.current_file_path, new_file_path)

    @Slot()
    def on_actionSave_Page_As_Image_triggered(self):
        messagebox_about(self.main_window, "Системная ошибка 10", "Данный функционал пока не реализован.")

    @Slot()
    def on_actionCompress_triggered(self):
        """
        Optimize and compress the PDF document.
        """
        if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
            return  # No open PDF files check

        self.ensure_temp_file()

        try:
            # Rotate tempfile backwards if visual_rotation_degree is not 0
            if self.visual_rotation_degree != 0:
                rotate_pdf_pages(self.temp_file_path, -self.visual_rotation_degree)

            output_file_path = self.current_file_path + "_compressed.pdf"

            with fitz.open(self.temp_file_path) as doc:
                # Save the document to a new file with optimization
                doc.save(output_file_path, garbage=4, deflate=True, clean=True)

            # Overwrite the original file after successful compression
            shutil.move(output_file_path, self.current_file_path)

            messagebox_info(self.main_window, "Сжатие документа", "PDF документ успешно сжат!")

            # Update state and reload the compressed file
            self.fileModified = False
            self.tempFileOpen = False
            self.fileOpen = True
            self.open_in_viewer(self.current_file_path)
            self.visual_rotation_degree = 0  # Reset rotation

        except Exception as e:
            messagebox_warn(self.main_window, "Ошибка", f"Не удалось сжать PDF документ: {str(e)}")

    @Slot()
    def on_actionAddFile_triggered(self):
        # messagebox_info(self.main_window, "Окно в разработке", f"Данный функционал пока не реализован.")
        """Insert a PDF or image into the currently open PDF document."""
        if not hasattr(self, 'pdf_viewer_doc') or not (self.fileOpen or self.tempFileOpen):
            messagebox_info(self.main_window, "Вставка файла",
                            f"Пожалуйста, сначала откройте PDF документ для вставки в него другого документа.")
            return  # no open pdf check

        # Step 1: File dialog to select the file
        file_dialog = QFileDialog(self.main_window, "Выберите файл для вставки",
                                  os.path.dirname(self.current_file_path))
        file_dialog.setNameFilters(["PDF Files (*.pdf)", "Images (*.png *.jpg *.jpeg *.bmp)"])
        file_dialog.setAcceptMode(QFileDialog.AcceptOpen)

        if file_dialog.exec() != QFileDialog.Accepted:
            return  # User canceled the file dialog

        insertion_file = file_dialog.selectedFiles()[0]

        # Step 2: Show the dialog for insertion configuration
        current_page = self.nav.currentPage()  # Get current page
        dialog = InsertPageDialog(self.main_window, max_pages=self.pdf_viewer_doc.pageCount(),
                                  current_page=current_page)

        if dialog.exec() != QDialog.Accepted:
            return  # User canceled the insert dialog

        # Get the insertion settings
        insert_before_position, specified_page = dialog.get_insertion_settings()

        try:
            current_page = self.nav.currentPage()  # Get the current page number

            self.ensure_temp_file()

            # Insert the file based on the user's selection
            insert_file_into_pdf(self.temp_file_path, insertion_file, insert_before_position, specified_page)

            # Refresh the viewer
            self.fileModified = True
            self.tempFileOpen = True
            self.fileOpen = False
            self.open_in_viewer(self.temp_file_path)
            self.jump_to_int_page(current_page)  # Jump back to the current page

            messagebox_info(self.main_window, "Успех", "Файл успешно вставлен.")

        except Exception as e:
            messagebox_warn(self.main_window, "Ошибка", f"Не удалось вставить файл: {str(e)}")

    @Slot(QPoint)
    def show_thumbnail_context_menu(self, position):
        """Show a custom context menu for the thumbnail list."""
        global_pos = self.ui_module.thumbnailList.mapToGlobal(position)
        menu = QMenu()

        # Add actions
        delete_action = menu.addAction("Удалить страницу")
        move_up_action = menu.addAction("Переместить страницу вверх")
        move_down_action = menu.addAction("Переместить страницу вниз")
        save_action = menu.addAction("Сохранить страницу как изображение...")

        # Execute menu and get selected action
        action = menu.exec(global_pos)

        # Perform the action
        if action == delete_action:
            self.delete_selected_page()
        elif action == move_up_action:
            self.move_selected_page_up()
        elif action == move_down_action:
            self.move_selected_page_down()
        elif action == save_action:
            self.save_selected_page_as_image()

    def delete_selected_page(self):
        """Delete the selected page in the PDF."""
        if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
            return  # no open pdf files check

        selected_items = self.ui_module.thumbnailList.selectedItems()
        if not selected_items:
            return

        # Get the selected page index
        page_index = selected_items[0].data(Qt.UserRole)

        self.ensure_temp_file()

        current_page = self.nav.currentPage()  # Get the current page number

        try:
            # Delete the current page
            delete_pdf_page(self.temp_file_path, page_index)
            self.fileModified = True
            self.tempFileOpen = True
            self.fileOpen = False

            # Open updated PDF
            self.open_in_viewer(self.temp_file_path)
            next_page = min(current_page, self.pdf_viewer_doc.pageCount() - 1)  # Jump to a valid page
            self.jump_to_int_page(next_page)

        except Exception as e:
            messagebox_warn(self.main_window, "Ошибка", f"Не удалось удалить страницу: {str(e)}")

    def move_selected_page_up(self):
        """Move the selected page up."""
        if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
            return  # no open pdf files check

        selected_items = self.ui_module.thumbnailList.selectedItems()
        if not selected_items:
            return

        # Get the selected page index
        page_index = selected_items[0].data(Qt.UserRole)

        if page_index == 0:
            return  # Already at the top

        self.ensure_temp_file()

        current_page = self.nav.currentPage()

        try:
            move_pdf_page(self.temp_file_path, page_index, page_index - 1)
            self.fileModified = True
            self.tempFileOpen = True
            self.fileOpen = False

            self.open_in_viewer(self.temp_file_path)
            next_page = min(current_page, self.pdf_viewer_doc.pageCount() - 1)  # Jump to a valid page
            self.jump_to_int_page(next_page)

        except Exception as e:
            messagebox_warn(self.main_window, "Ошибка", f"Не удалось переместить страницу: {str(e)}")

    def move_selected_page_down(self):
        """Move the selected page down."""
        if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
            return  # no open pdf files check

        selected_items = self.ui_module.thumbnailList.selectedItems()
        if not selected_items:
            return

        # Get the selected page index
        page_index = selected_items[0].data(Qt.UserRole)
        total_pages = self.pdf_viewer_doc.pageCount()

        if page_index >= total_pages:
            return  # Already at the bottom

        self.ensure_temp_file()

        current_page = self.nav.currentPage()

        try:
            move_pdf_page(self.temp_file_path, page_index + 1, page_index)
            self.fileModified = True
            self.tempFileOpen = True
            self.fileOpen = False

            self.open_in_viewer(self.temp_file_path)
            next_page = min(current_page, self.pdf_viewer_doc.pageCount() - 1)  # Jump to a valid page
            self.jump_to_int_page(next_page)

        except Exception as e:
            messagebox_warn(self.main_window, "Ошибка", f"Не удалось переместить страницу: {str(e)}")

    def save_selected_page_as_image(self):
        """Save the selected page as an image."""
        selected_items = self.ui_module.thumbnailList.selectedItems()
        if not selected_items:
            return

        # Get the selected page index
        page_index = selected_items[0].data(Qt.UserRole)

        file_dialog = QFileDialog(self.main_window)
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setNameFilter("Images (*.png *.jpg *.jpeg)")
        file_dialog.setFileMode(QFileDialog.AnyFile)

        if file_dialog.exec() == QDialog.Accepted:
            file_path = file_dialog.selectedFiles()[0]
            base_name, extension = os.path.splitext(file_path)

            try:
                with fitz.open(self.current_file_path) as doc:
                    page = doc[page_index]

                    # Set higher resolution for the image
                    zoom_x = 2.0  # Horizontal zoom (2x resolution)
                    zoom_y = 2.0  # Vertical zoom (2x resolution)
                    matrix = fitz.Matrix(zoom_x, zoom_y)

                    # Generate high-resolution pixmap
                    pix = page.get_pixmap(matrix=matrix)
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

                    if extension.lower() in ['.jpg', '.jpeg']:
                        img.save(file_path, 'JPEG')
                    else:
                        img.save(file_path, 'PNG')

                messagebox_info(self.main_window, "Сохранение страницы",
                                f"Страница {page_index + 1} успешно сохранена!")
            except Exception as e:
                messagebox_warn(self.main_window, "Ошибка", f"Не удалось сохранить страницу: {str(e)}")

    @Slot()
    def on_actionPasswordDoc_triggered(self):
        messagebox_about(self.main_window, "Системная ошибка 14", "Данный функционал пока не реализован.")
        # Code is commented

    # endregion File Operations

    # region File Operations (helper)

    def create_temp_file(self):
        """Creates a temp file from the original PDF file."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        shutil.copyfile(self.current_file_path, temp_file.name)
        temp_file.close()  # Close the file handle to avoid locking
        return temp_file.name

    def ensure_temp_file(self):
        """Ensure a temporary file for saving changes exists."""
        if self.current_file_path and not self.temp_file_path:
            self.temp_file_path = self.create_temp_file()

    def prompt_save_unsaved_changes(self):
        """Prompts the user to save unsaved changes, discard them, or cancel."""
        msg_box = QMessageBox(self.main_window)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("Сохранить изменения?")
        msg_box.setText("Вы хотите сохранить изменения перед закрытием документа?")

        yes_button = msg_box.addButton("Да", QMessageBox.YesRole)
        no_button = msg_box.addButton("Нет", QMessageBox.NoRole)
        cancel_button = msg_box.addButton("Отмена", QMessageBox.RejectRole)

        msg_box.setDefaultButton(cancel_button)
        msg_box.exec_()

        if msg_box.clickedButton() == yes_button:
            return QMessageBox.Yes
        elif msg_box.clickedButton() == no_button:
            return QMessageBox.No
        else:
            return QMessageBox.Cancel

    def reset_ui_after_close(self):
        pass
        # """Resets all UI components related to the document after closing."""
        # # Clear PDF view and related UI elements
        # self.pdf_viewer = self.main_window.ui.pdfView
        # self.pdf_viewer.setDocument(None)
        # self.bookmark_model.setDocument(None)
        #
        # self.pdf_viewer_doc.close()  # In case doc gets locked
        # self.pdf_viewer_doc = None
        # self.pdf_viewer_doc = QPdfDocument()
        #
        # self.ui_module.m_pageInput.clear()
        # self.ui_module.m_pageLabel.setText("")
        # self.ui_module.statusBar.clearMessage()
        #
        # # Set the window title back to default
        # self.main_window.setWindowTitle("Альт PDF")
        #
        # # Clear thumbnail list
        # self.ui_module.thumbnailList.clear()
        #
        # # Stop any running timers
        # if self.thumbnail_timer.isActive():
        #     self.thumbnail_timer.stop()

    def create_file_dialog(self, directory):
        """Creates the file dialog for selecting PDF files."""
        file_dialog = QFileDialog(self.main_window, "Выберите PDF файл", directory)
        file_dialog.setAcceptMode(QFileDialog.AcceptOpen)
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        file_dialog.setMimeTypeFilters(["application/pdf"])  # one is redundant
        file_dialog.setNameFilter("Файлы PDF (*.pdf)")  # one is redundant
        return file_dialog

    # endregion File Operations (helper)

    # ------------------------ Document View ------------------------ (3/5 complete)
    # region Document View

    @Slot()
    def on_actionZoom_In_triggered(self):
        pass
        #
        # current_text = self.ui_module.m_zoomSelector.currentText()
        # current_page = self.nav.currentPage()
        #
        # # Access the viewer and its scrollbars
        # viewer = self.pdf_viewer
        # h_scrollbar = viewer.horizontalScrollBar()
        # v_scrollbar = viewer.verticalScrollBar()
        #
        # # Calculate the center point in logical document coordinates
        # center_x = h_scrollbar.value() + (h_scrollbar.pageStep() // 2)
        # center_y = v_scrollbar.value() + (v_scrollbar.pageStep() // 2)
        # logical_center_x = center_x / viewer.zoomFactor()
        # logical_center_y = center_y / viewer.zoomFactor()
        #
        # # Determine the new zoom factor
        # if current_text in ["По ширине", "По высоте"]:
        #     new_factor = 1.0 + 0.1  # Reset to a default zoom if in fit mode
        # else:
        #     new_factor = viewer.zoomFactor() + 0.1
        #
        # # Clamp the zoom factor within reasonable bounds
        # new_factor = min(20.0, max(0.1, new_factor))
        # viewer.setZoomFactor(new_factor)
        #
        # # Restore the center position using the logical coordinates
        # h_scrollbar.setValue(int(logical_center_x * new_factor - (h_scrollbar.pageStep() // 2)))
        # v_scrollbar.setValue(int(logical_center_y * new_factor - (v_scrollbar.pageStep() // 2)))
        #
        # # Update the current page display
        # next_page = min(current_page, self.pdf_viewer_doc.pageCount() - 1)  # Jump to a valid page
        # self.jump_to_int_page(next_page)
        # self.update_page_display(current_page)

    @Slot()
    def on_actionZoom_Out_triggered(self):
        pass
        # current_text = self.ui_module.m_zoomSelector.currentText()
        # current_page = self.nav.currentPage()  # Remember page before zoom
        #
        # # Access the viewer and its scrollbars
        # viewer = self.pdf_viewer
        # h_scrollbar = viewer.horizontalScrollBar()
        # v_scrollbar = viewer.verticalScrollBar()
        #
        # # Calculate the center point in logical document coordinates
        # center_x = h_scrollbar.value() + (h_scrollbar.pageStep() // 2)
        # center_y = v_scrollbar.value() + (v_scrollbar.pageStep() // 2)
        # logical_center_x = center_x / viewer.zoomFactor()
        # logical_center_y = center_y / viewer.zoomFactor()
        #
        # # Determine the new zoom factor
        # if current_text in ["По ширине", "По высоте"]:
        #     new_factor = 1.0 - 0.1  # Reset to a default zoom if in fit mode
        # else:
        #     new_factor = viewer.zoomFactor() - 0.1
        #
        # # Clamp the zoom factor within reasonable bounds
        # new_factor = max(0.1, min(20.0, new_factor))
        # viewer.setZoomFactor(new_factor)
        #
        # # Restore the center position using the logical coordinates
        # h_scrollbar.setValue(int(logical_center_x * new_factor - (h_scrollbar.pageStep() // 2)))
        # v_scrollbar.setValue(int(logical_center_y * new_factor - (v_scrollbar.pageStep() // 2)))
        #
        # # Update the current page display
        # next_page = min(current_page, self.pdf_viewer_doc.pageCount() - 1)  # Jump to a valid page
        # self.jump_to_int_page(next_page)
        # self.update_page_display(current_page)

    @Slot()
    def on_actionFitToWidth_triggered(self):
        # self.ui_module.m_zoomSelector.set_zoom_factor(1)
        self.pdf_viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.ui_module.m_zoomSelector.set_zoom_factor(QPdfView.ZoomMode.FitToWidth)

    @Slot()
    def on_actionFitToHeight_triggered(self):
        # self.ui_module.m_zoomSelector.set_zoom_factor(1)
        self.pdf_viewer.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.ui_module.m_zoomSelector.set_zoom_factor(QPdfView.ZoomMode.FitInView)

    # endregion Document View

    # region Document View (helper)

    def set_window_title(self, pdf_document_path):
        document_title = os.path.basename(pdf_document_path)
        if self.fileModified:
            document_title += " *"
        self.main_window.setWindowTitle(document_title if document_title else "Альт PDF")

    def update_status_bar(self, pdf_document_path, current_page):
        pass
        # """Updates the status bar with details about the current page."""
        # if pdf_document_path and 0 <= current_page < self.pdf_viewer_doc.pageCount():
        #     doc = get_document(self, pdf_document_path)
        #
        #     if doc:
        #         page = doc[current_page]
        #         width_mm, height_mm = page.rect.width / 72 * 25.4, page.rect.height / 72 * 25.4
        #         format_name = get_page_format(width_mm, height_mm)
        #         status_text = (f"Страница {current_page + 1} из {self.pdf_viewer_doc.pageCount()}    |   "
        #                        f" Формат: {format_name}   |   "
        #                        f"{width_mm:.0f} x {height_mm:.0f} мм ({page.rect.width:.0f} x {page.rect.height:.0f} пксл)")
        #
        #         # Add visual rotation degree to the right side of the status bar
        #         rotation_text = f"Поворот: {self.visual_rotation_degree}°"
        #
        #         # Create a permanent widget for the rotation information
        #         if not hasattr(self, 'rotation_label'):
        #             self.rotation_label = QLabel(rotation_text)
        #             self.ui_module.statusBar.addPermanentWidget(self.rotation_label)
        #         else:
        #             self.rotation_label.setText(rotation_text)
        #
        #         self.ui_module.statusBar.showMessage(status_text)
        #         doc.close()

    # endregion Document View (helper)

    # ------------------------ Page Manipulation ------------------------ (0/8 complete)
    # region Page Manipulation

    # def on_actionRotateLeft_triggered(self):
    #     """Rotate the PDF 90 degrees counterclockwise."""
    #     if self.pdf_viewer.doc:
    #         self.visual_rotation_degree = (self.visual_rotation_degree - 90) % 360
    #         self.pdf_viewer.rotate_document(-90)
    #         self.fileModified = True
    #
    # def on_actionRotateRight_triggered(self):
    #     """Rotate the PDF 90 degrees clockwise."""
    #     if self.pdf_viewer.doc:
    #         self.visual_rotation_degree = (self.visual_rotation_degree + 90) % 360
    #         self.pdf_viewer.rotate_document(90)
    #         self.fileModified = True

    @Slot()
    def on_actionRotateViewClockwise_triggered(self):
        """Rotate the PDF 90 degrees clockwise."""
        self.pdf_viewer.rotate_current_page(90)

        # """Rotate pages visually only (for display)."""
        # if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
        #     return  # no open pdf files check
        #
        # self.ensure_temp_file()
        #
        # try:
        #     rotate_pdf_pages(self.temp_file_path, 90)  # Rotate all pages
        #     self.visual_rotation_degree = (self.visual_rotation_degree + 90) % 360  # Update visual rotation
        #     self.tempFileOpen = True
        #     self.fileOpen = False
        #     self.open_in_viewer(self.temp_file_path)
        #
        #     # # Update the page display and status bar
        #     # current_page = self.pdf_viewer.pageNavigator().currentPage()
        #     # self.update_page_display(current_page)
        #
        # except Exception as e:
        #     messagebox_warn(self.main_window, "Ошибка", f"Не удалось повернуть страницы: {str(e)}")

    @Slot()
    def on_actionRotateViewCounterclockwise_triggered(self):
        """Rotate the PDF 90 degrees counterclockwise."""
        self.pdf_viewer.rotate_current_page(-90)

        # """Rotate pages visually only (for display)."""
        # if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
        #     return  # no open pdf files check
        #
        # self.ensure_temp_file()
        #
        # try:
        #     rotate_pdf_pages(self.temp_file_path, 270)  # Rotate all pages
        #     self.visual_rotation_degree = (self.visual_rotation_degree - 90) % 360  # Update visual rotation
        #     self.tempFileOpen = True
        #     self.fileOpen = False
        #     self.open_in_viewer(self.temp_file_path)
        #
        # except Exception as e:
        #     messagebox_warn(self.main_window, "Ошибка", f"Не удалось повернуть страницы: {str(e)}")

    @Slot()
    def on_actionDeletePage_triggered(self):
        """Delete the current page in a temp file (for saving)."""
        self.pdf_viewer.delete_current_page()

        # if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
        #     return  # no open pdf files check
        #
        # self.ensure_temp_file()
        #
        # current_page = self.nav.currentPage()  # Get the current page number
        #
        # try:
        #     # Delete the current page
        #     delete_pdf_page(self.temp_file_path, current_page)
        #     self.fileModified = True
        #     self.tempFileOpen = True
        #     self.fileOpen = False
        #
        #     # Open updated PDF
        #     self.open_in_viewer(self.temp_file_path)
        #     next_page = min(current_page, self.pdf_viewer_doc.pageCount() - 1)  # Jump to a valid page
        #     self.jump_to_int_page(next_page)
        #
        # except Exception as e:
        #     messagebox_warn(self.main_window, "Ошибка", f"Не удалось удалить страницу: {str(e)}")

    @Slot()
    def on_actionRotateSpecificPages_triggered(self):
        pass
        # """Rotate specific pages in a temp file (for saving)."""
        # if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
        #     return  # no open pdf files check
        #
        # self.ensure_temp_file()
        #
        # current_page = self.nav.currentPage()  # Get the current page number
        #
        # # Create and execute the PageOperationDialog for rotation
        # dialog = PageOperationDialog(self.main_window, max_pages=self.pdf_viewer_doc.pageCount(),
        #                              current_page=current_page,
        #                              operation="rotate")
        # if dialog.exec() != QDialog.Accepted:
        #     return  # User canceled the dialog
        #
        # # Get the operation settings
        # rotation_str, page_range, page_type = dialog.get_operation_settings()
        #
        # # Map rotation string (e.g., "90°") to an integer angle
        # rotation_map = {"90°": 90, "-90°": -90, "180°": 180}
        # rotation = rotation_map.get(rotation_str)
        #
        # if rotation is None:
        #     messagebox_warn(self.main_window, "Ошибка", f"Неверный угол поворота: {rotation_str}")
        #     return
        #
        # try:
        #     pages_to_rotate = get_pages_in_range(page_range, page_type)  # Get the specific pages
        #     rotate_pdf_pages(self.temp_file_path, rotation, page_number=pages_to_rotate)  # Rotate pages
        #
        #     self.fileModified = True
        #     self.tempFileOpen = True
        #     self.fileOpen = False
        #     self.open_in_viewer(self.temp_file_path)
        #     self.jump_to_int_page(current_page)  # Jump back to the current page
        #
        # except Exception as e:
        #     messagebox_warn(self.main_window, "Ошибка", f"Не удалось повернуть страницы: {str(e)}")

    @Slot()
    def on_actionDeleteSpecificPages_triggered(self):
        """Delete specific pages based on user input."""
        if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
            return  # no open pdf files check

        self.ensure_temp_file()

        current_page = self.nav.currentPage()  # Get the current page number
        dialog = PageOperationDialog(self.main_window, max_pages=self.pdf_viewer_doc.pageCount(),
                                     current_page=current_page, operation="delete")

        if dialog.exec() == QDialog.Accepted:
            page_range, page_type = dialog.get_operation_settings()

            try:
                # Convert page range into list of pages
                pages_to_delete = get_pages_in_range(page_range, page_type)

                # Delete specified pages
                for page in sorted(pages_to_delete, reverse=True):
                    delete_pdf_page(self.temp_file_path, page)

                self.fileModified = True
                self.tempFileOpen = True
                self.fileOpen = False

                # Open updated PDF and jump to a valid page
                self.open_in_viewer(self.temp_file_path)
                next_page = min(current_page, self.pdf_viewer_doc.pageCount() - 1)
                self.jump_to_int_page(next_page)

                messagebox_info(self.main_window, "Успех", "Страницы успешно удалены.")

            except Exception as e:
                messagebox_warn(self.main_window, "Ошибка", f"Не удалось удалить страницы: {str(e)}")

    @Slot()
    def on_actionMovePageDown_triggered(self):
        self.pdf_viewer.move_page_down()

        # """Move the current page down (forward) in a temp file (for saving)."""
        # if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
        #     return  # no open pdf files check
        #
        # self.ensure_temp_file()
        #
        # current_page = self.nav.currentPage()
        # next_page = current_page + 1  # Get the next page number
        #
        # if current_page >= self.pdf_viewer_doc.pageCount():
        #     # messagebox_warn(self.main_window, "Внимание", "Невозможно переместить страницу дальше.")
        #     return
        #
        # try:
        #     move_pdf_page(self.temp_file_path, next_page, current_page)
        #     self.fileModified = True
        #     self.tempFileOpen = True
        #     self.fileOpen = False
        #
        #     self.open_in_viewer(self.temp_file_path)
        #     next_page = min(next_page, self.pdf_viewer_doc.pageCount() - 1)  # Jump to a valid page
        #     self.jump_to_int_page(next_page)
        #
        #     # messagebox_info(self.main_window, "Успех", f"Страница {next_page + 1} перемещена вперед.")
        #
        # except Exception as e:
        #     messagebox_warn(self.main_window, "Ошибка", f"Не удалось переместить страницу: {str(e)}")

    @Slot()
    def on_actionMovePageUp_triggered(self):
        self.pdf_viewer.move_page_up()

        # """Move the current page up (backward) in a temp file (for saving)."""
        # if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
        #     return  # no open pdf files check
        #
        # self.ensure_temp_file()
        #
        # current_page = self.nav.currentPage()  # Get the current page number
        # prev_page = current_page - 1
        #
        # if prev_page < 0:
        #     # messagebox_warn(self.main_window, "Внимание", "Невозможно переместить страницу назад.")
        #     return
        #
        # try:
        #     move_pdf_page(self.temp_file_path, current_page, prev_page)
        #     self.fileModified = True
        #     self.tempFileOpen = True
        #     self.fileOpen = False
        #
        #     self.open_in_viewer(self.temp_file_path)
        #     prev_page = min(prev_page, self.pdf_viewer_doc.pageCount() - 1)  # Jump to a valid page
        #     self.jump_to_int_page(prev_page)
        #
        #     # messagebox_info(self.main_window, "Успех", f"Страница {current_page + 1} перемещена назад.")
        #
        # except Exception as e:
        #     messagebox_warn(self.main_window, "Ошибка", f"Не удалось переместить страницу: {str(e)}")

    @Slot()
    def on_actionRotateCurrentPageClockwise_triggered(self):
        """Rotate current page clockwise in a temp file (for saving)."""
        if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
            return  # no open pdf files check

        self.ensure_temp_file()

        current_page = self.nav.currentPage()  # Get the current page number

        try:
            rotate_pdf_pages(self.temp_file_path, 90, page_number=current_page)  # Rotate the current page
            self.fileModified = True
            self.tempFileOpen = True
            self.fileOpen = False
            self.open_in_viewer(self.temp_file_path)
            self.jump_to_int_page(current_page)  # Jump back to the current page

        except Exception as e:
            messagebox_warn(self.main_window, "Ошибка", f"Не удалось повернуть страницы: {str(e)}")

    @Slot()
    def on_actionRotateCurrentPageCounterclockwise_triggered(self):
        """Rotate pages clockwise in a temp file (for saving)."""
        if not hasattr(self, 'pdf_viewer_doc') or (not self.fileOpen and not self.tempFileOpen):
            return  # no open pdf files check

        self.ensure_temp_file()

        current_page = self.nav.currentPage()  # Get the current page number

        try:
            rotate_pdf_pages(self.temp_file_path, 270, page_number=current_page)  # Rotate the current page
            self.fileModified = True
            self.tempFileOpen = True
            self.fileOpen = False
            self.open_in_viewer(self.temp_file_path)
            self.jump_to_int_page(current_page)  # Jump back to the current page

        except Exception as e:
            messagebox_warn(self.main_window, "Ошибка", f"Не удалось повернуть страницы: {str(e)}")

    # endregion Page Manipulation

    # ------------------------ Miscellaneous ------------------------ (?/? complete - low priority)
    # region Miscellaneous

    @Slot()
    def on_actionPrint_triggered(self):
        # Check if there is an open PDF file
        if not hasattr(self, 'current_file_path') or not self.current_file_path:
            messagebox_info(self.main_window, "Предупреждение", "Пожалуйста, сначала откройте файл PDF.")
            return

        try:
            # Set up printer in high resolution
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self.main_window)

            # Show print dialog and exit if user cancels
            if dialog.exec() != QPrintDialog.Accepted:
                return

            # Open the PDF document
            pdf_document = fitz.open(self.current_file_path)
            painter = QPainter()

            # Start the painter with the printer
            if not painter.begin(printer):
                messagebox_info(self.main_window, "Ошибка печати", "Невозможно открыть устройство печати.")
                return

            # Iterate through pages of the document
            for page_num in range(pdf_document.page_count):
                if page_num > 0:
                    printer.newPage()

                page = pdf_document[page_num]

                # Determine page orientation
                pdf_rect = page.rect
                is_landscape = pdf_rect.width > pdf_rect.height
                is_portrait = pdf_rect.height > pdf_rect.width

                # Set printer page layout
                layout = QPageLayout()
                page_layout = printer.pageLayout()
                if is_landscape and (page_layout.orientation() == QPageLayout.Portrait):
                    page.set_rotation(90)
                elif is_portrait and (page_layout.orientation() == QPageLayout.Landscape):
                    page.set_rotation(90)

                printer.setPageLayout(layout)

                # Render page at high resolution
                zoom_factor = 2  # Adjust for print quality
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom_factor, zoom_factor))
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)

                # Get the page rect from printer in device pixels
                paint_rect = printer.pageRect(QPrinter.DevicePixel)

                # Scale image to fit the page while maintaining aspect ratio
                scaled_image = image.scaled(
                    QSize(paint_rect.width(), paint_rect.height()),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                # Center the image on the page
                x = (paint_rect.width() - scaled_image.width()) // 2
                y = (paint_rect.height() - scaled_image.height()) // 2
                painter.drawImage(QRect(x, y, scaled_image.width(), scaled_image.height()), scaled_image)

            # End the painter and close document
            painter.end()
            pdf_document.close()

        except Exception as e:
            message = f"Ошибка при печати: {str(e)}"
            messagebox_info(self.main_window, "Ошибка", message)

    def print_selected_pages(self, printer, start_page, end_page):
        if not hasattr(self, "pdf_viewer_doc") or (not self.fileOpen and not self.tempFileOpen):
            return  # No open PDF files, return early

        self.main_window, "PRINTING!", "IN PROGRESS"

        self.ensure_temp_file()

        # Open the PDF document
        pdf_document = fitz.open(self.temp_file_path)
        total_pages = pdf_document.page_count

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.warning(
                self.main_window, "Ошибка печати", "Невозможно открыть устройство печати."
            )
            return

        # Validate the page range
        if start_page > total_pages:
            QMessageBox.critical(
                self.main_window,
                "Ошибка",
                f"Ошибка печати документа: начальная страница ({start_page}) вне диапазона.",
            )
        elif end_page is None or end_page > total_pages:
            end_page = total_pages

        # Iterate through the selected page range
        for page_num in range(start_page - 1, end_page):
            # Start a new page for all but the first page in the range
            if page_num > start_page - 1:
                printer.newPage()

            # Load the current page
            page = pdf_document.load_page(page_num)

            # Determine page orientation
            pdf_rect = page.rect
            is_landscape = pdf_rect.width > pdf_rect.height
            is_portrait = pdf_rect.height > pdf_rect.width

            # Set printer page layout
            page_layout = printer.pageLayout()
            if is_landscape and page_layout.orientation() == QPageLayout.Portrait:
                page_layout.setRotation(90)
            elif is_portrait and page_layout.orientation() == QPageLayout.Landscape:
                page_layout.setRotation(90)

            # Determine the best fit page size (A4 or A3)
            aspect_ratio = pdf_rect.width / pdf_rect.height
            if 1.3 < aspect_ratio <= 1.4:
                page_layout.setPageSize(QPageSize(QPageSize.A4))
            elif 1.4 < aspect_ratio <= 1.45:
                page_layout.setPageSize(QPageSize(QPageSize.A3))
            else:
                page_layout.setPageSize(QPageSize(QPageSize.A4))  # Default to A4

            printer.setPageLayout(page_layout)

            # Render the page at high resolution
            zoom_factor = 2  # Increase for higher quality, decrease for faster rendering
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom_factor, zoom_factor))
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

            # Get the paint rectangle
            paint_rect = printer.pageRect(QPrinter.DevicePixel)
            scaled_image = image.scaled(
                QSize(paint_rect.width(), paint_rect.height()),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

            # Center the image on the page
            x = (paint_rect.width() - scaled_image.width()) // 2
            y = (paint_rect.height() - scaled_image.height()) // 2
            painter.drawImage(QRect(x, y, scaled_image.width(), scaled_image.height()), scaled_image)

        # Finish the printing process
        painter.end()
        pdf_document.close()

    @Slot()
    def on_actionEnumeratePages_triggered(self):
        messagebox_about(self.main_window, "Системная ошибка 16", "Данный функционал пока не реализован.")
        # Code is commented

    @Slot()
    def on_actionDraw_triggered(self):
        self.ui_module.actionDraw.setChecked(self.in_draw_mode)

        # Logic for checking if the file is open
        if self.fileOpen != True and self.tempFileOpen != True:
            return

        # Toggle the active/inactive state of toolbar buttons
        for action in self.ui_module.mainToolBar.actions():
            if action != self.ui_module.actionDraw:  # Exclude the 'Draw' action from toggling
                action.setEnabled(not action.isEnabled())

        self.ui_module.actionDraw.setChecked(not self.in_draw_mode)
        self.in_draw_mode = not self.in_draw_mode

    @Slot()
    def on_actionAboutPdf_triggered(self):
        if self.fileModified:
            doc = get_document(self, self.temp_file_path)
            self.tempFileOpen = True
            self.fileOpen = False
        else:
            doc = get_document(self, self.current_file_path)
            self.tempFileOpen = False
            self.fileOpen = True

        if doc:
            display_pdf_metadata(self.main_window, doc, self.current_file_path)
            doc.close()

    @Slot()
    def on_actionAbout_triggered(self):
        QMessageBox.about(self.main_window, "О программе «Альт PDF»",
                          "Программа для просмотра и редактирования PDF-документов"
                          "\n\n\n"
                          "Разработка ПУ АсуНефть ГИСиСАПР"
                          "\n"
                          "Версия 0.320.1")

    @Slot()
    def on_actionQuit_triggered(self, via_system=False):
        """Closes the PDF editor and deletes temp files."""
        if not via_system:
            self.on_actionClosePdf_triggered()
            self.main_window.close()

        # if self.fileModified:
        #     response = self.prompt_save_unsaved_changes()
        #     if response == QMessageBox.Yes:
        #         # Save changes
        #         self.on_actionSave_triggered()
        #     elif response == QMessageBox.Cancel:
        #         return  # Don't quit if the user cancels the action
        #
        #
        # # Delete the temporary file if it exists
        # if self.temp_file_path and os.path.exists(self.temp_file_path):
        #     try:
        #         os.remove(self.temp_file_path)
        #         self.temp_file_path = None  # Clear the reference after deletion
        #     except OSError as e:
        #         print(f"Ошибка при удалении временного файла: {e}")

    @Slot()
    def on_actionToggle_Panel_triggered(self):
        """Toggle the visibility of the sidebar panel."""
        self.ui_module.tabButtonsWidget.setVisible(not self.ui_module.tabButtonsWidget.isVisible())
        self.ui_module.sidePanelContent.setVisible(self.ui_module.tabButtonsWidget.isVisible())

    @Slot()
    def on_actionEmail_triggered(self):
        if not self.current_file_path:
            messagebox_about(self.main_window, "Внимание", "Пожалуйста, сначала откройте файл PDF.")
            return

        subject = self.current_file_path.split("/")[-1]
        pdf_document = self.current_file_path

        if sys.platform == "win32":
            try:
                ol_app = win32.Dispatch('Outlook.Application')
                ol_ns = ol_app.GetNameSpace('MAPI')

                mail_item = ol_app.CreateItem(0)
                mail_item.Subject = subject
                mail_item.Attachments.Add(pdf_document)
                mail_item.Display()
            except Exception as e:
                messagebox_warn(self.main_window, "Ошибка", f"Outlook не обнаружен на устройстве: {e}")

        elif sys.platform == "linux":
            r7_organizer_path = "/opt/r7-office/organizer/r7organizer"
            command = [r7_organizer_path, "-compose", f"subject='{subject}',attachment='{pdf_document}'"]
            subprocess.run(command)

    # endregion Miscellaneous

    # ------------------------ Navigation ------------------------ (7/7 complete)
    # region Navigation

    @Slot(int)
    def jump_to_int_page(self, page):
        pass
        # if 0 <= page < self.pdf_viewer_doc.pageCount():
        #     self.nav.jump(page, QPoint(), self.nav.currentZoom())
        # else:
        #     # messagebox_warn(self.main_window, "Некорректное значение", "Страница вне пределов открытого документа.")
        #     pass

    @Slot()
    def on_actionJumpToFirstPage_triggered(self):
        pass
        # if self.nav:
        #     self.jump_to_int_page(0)

    @Slot()
    def on_actionJumpToLastPage_triggered(self):
        pass
        # if self.nav:
        #     self.jump_to_int_page(self.pdf_viewer_doc.pageCount() - 1)

    @Slot()
    def on_actionPrevious_Page_triggered(self):
        pass
        # if self.nav:
        #     self.jump_to_int_page(self.nav.currentPage() - 1)

    @Slot()
    def on_actionNext_Page_triggered(self):
        pass
        # if self.nav:
        #     self.jump_to_int_page(self.nav.currentPage() + 1)

    @Slot()
    def jump_to_textbox_page(self):
        """Jumps to the page number entered by the user after sanitizing the input."""
        page_text = self.ui_module.m_pageInput.text().strip()

        # Extract numbers from the text, ignoring any other characters
        import re
        numbers = re.findall(r'\d+', page_text)

        if not numbers:
            # No valid numbers found, show warning and revert to current page
            # messagebox_warn(self.main_window, "Неверный ввод", "Неверный номер страницы.")
            return

        # Take the first number found
        page_number = int(numbers[0])

        # Clamp the page number within the valid range
        max_page = self.pdf_viewer_doc.pageCount() - 1  # Adjust for zero-based indexing
        page_number = max(0, min(max_page, page_number - 1))  # Subtract 1 for zero-based index

        # Update the text to show the cleaned page number
        self.ui_module.m_pageInput.setText(str(page_number + 1))  # Convert back to 1-based for display

        # Jump to the specified page
        self.jump_to_int_page(page_number)

    @Slot(QModelIndex)
    def bookmark_selected(self, index):
        if index.isValid():
            page = index.data(int(QPdfBookmarkModel.Role.Page))
            self.jump_to_int_page(page)

    # endregion Navigation

    # region Navigation (thumbnails)

    def generate_thumbnails(self):
        # Clear current thumbnails to start fresh
        self.ui_module.thumbnailList.clear()
        file_path = None

        if hasattr(self, 'temp_file_path') and self.temp_file_path:
            self.tempFileOpen = True
            self.fileOpen = False
            file_path = self.temp_file_path
        elif hasattr(self, 'current_file_path') and self.current_file_path:
            self.tempFileOpen = False
            self.fileOpen = True
            file_path = self.current_file_path

        # If no document is open, exit the function
        if not file_path:
            # message = "PDF документ должен быть открыт, чтобы отображать миниатюры."
            # messagebox_info(self.main_window, "Ошибка", message)
            return

        # If generating a new document's thumbnails, cancel previous generation
        self.cancel_thumbnail_generation = False

        try:
            # Open the PDF document
            doc = fitz.open(file_path)

            # Set thumbnail quality and matrix
            quality = self.get_thumbnail_quality()
            self.current_thumbnail_quality = quality
            matrix = fitz.Matrix(quality, quality)

            # Generate thumbnails for each page
            for page_num in range(doc.page_count):
                # Check if thumbnail generation was canceled due to a new file being opened
                if self.cancel_thumbnail_generation:
                    break

                # Generate thumbnail directly
                page = doc[page_num]
                pix = page.get_pixmap(matrix=matrix)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(img)

                # Create thumbnail widget
                thumbnail_widget = ThumbnailWidget(pixmap, page_num)
                thumbnail_widget.setThumbnailSize(self.get_thumbnail_size())

                # Add to list
                item = QListWidgetItem(self.ui_module.thumbnailList)
                item.setSizeHint(thumbnail_widget.sizeHint())
                self.ui_module.thumbnailList.addItem(item)
                self.ui_module.thumbnailList.setItemWidget(item, thumbnail_widget)
                item.setData(Qt.UserRole, page_num)

                # Process events to keep UI responsive
                QApplication.processEvents()

            # Adjust the thumbnail list grid size
            self.ui_module.thumbnailList.adjust_grid_size()
            doc.close()

        except Exception as e:
            message = f"Ошибка при генерации миниатюр: {str(e)}"
            messagebox_info(self.main_window, "Ошибка", message)

    def create_placeholder_thumbnail(self, page_num):
        placeholder = QLabel(f"Загрузка\nстр. {page_num + 1}")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("background-color: #f0f0f0; border: 1px solid #d0d0d0;")
        size = self.get_thumbnail_size()
        placeholder.setFixedSize(size, size)
        return placeholder

    def update_thumbnail(self, page_num, pixmap):
        item = self.ui_module.thumbnailList.item(page_num)
        if item:
            thumbnail_widget = ThumbnailWidget(pixmap, page_num)
            thumbnail_widget.setThumbnailSize(self.get_thumbnail_size())
            item.setSizeHint(thumbnail_widget.sizeHint())
            self.ui_module.thumbnailList.setItemWidget(item, thumbnail_widget)
        self.ui_module.thumbnailList.adjust_grid_size()

    def get_thumbnail_quality(self):
        value = self.ui_module.thumbnail_size_slider.value()
        if value <= 4:
            return 0.25
        elif value <= 9:
            return 0.4
        elif value <= 14:
            return 0.55
        else:
            return 0.75

    def get_thumbnail_size(self):
        value = self.ui_module.thumbnail_size_slider.value()
        return 90 + (value * 10)

    def adjust_thumbnail_size(self):
        size = self.get_thumbnail_size()
        for i in range(self.ui_module.thumbnailList.count()):
            item = self.ui_module.thumbnailList.item(i)
            widget = self.ui_module.thumbnailList.itemWidget(item)
            if isinstance(widget, ThumbnailWidget):
                widget.setThumbnailSize(size)
                item.setSizeHint(widget.sizeHint())
        self.ui_module.thumbnailList.adjust_grid_size()

        # Regenerate thumbnails if quality changed
        new_quality = self.get_thumbnail_quality()
        if hasattr(self, 'current_thumbnail_quality') and self.current_thumbnail_quality != new_quality:
            self.generate_thumbnails()
        self.current_thumbnail_quality = new_quality

    @Slot(QListWidgetItem)
    def thumbnail_clicked(self, item):
        # # Reset styles for all items
        # for i in range(self.ui_module.thumbnailList.count()):
        #     other_item = self.ui_module.thumbnailList.item(i)
        #     # self.ui_module.thumbnailList.selectedItems(other_item, False)
        #     self.ui_module.thumbnailList.itemWidget(other_item).setStyleSheet("border: none;")
        #
        # # Highlight the selected item
        # item_widget = self.ui_module.thumbnailList.itemWidget(item)
        # item_widget.setStyleSheet("border: 2px solid #0078d7;")  # Windows 11 blue

        # Perform the jump to the clicked page
        page_num = item.data(Qt.UserRole)
        self.jump_to_int_page(page_num)

    def initialize_thumbnail_components(self):
        self.thumbnail_timer = QTimer()
        self.thumbnail_timer.setSingleShot(True)

    def restart_thumbnail_timer(self):
        self.thumbnail_timer.start(100)

    # endregion Navigation (thumbnails)

    # region Navigation (helper)

    def initialize_bookmarks_panel(self):
        self.bookmark_model = QPdfBookmarkModel(self.main_window)
        self.bookmark_model.setDocument(self.pdf_viewer.doc)
        self.ui_module.bookmarkView.setModel(self.bookmark_model)

    # endregion Navigation (helper)


# ------------------------ Action Connections ------------------------
# region Action Connections

def connect_ui_actions(self):
    """
    Connect UI actions to their respective slots.

    This function establishes connections between user interface elements and their corresponding
    event handlers, enabling the application to respond to user interactions.
    """
    # Default signal connections:
    self.ui_module.m_pageInput.returnPressed.connect(self.jump_to_textbox_page)
    # self.pdf_viewer.pageNavigator().currentPageChanged.connect(self.update_page_display)
    self.ui_module.bookmarkView.activated.connect(self.bookmark_selected)
    self.ui_module.actionToggle_Panel.triggered.connect(self.on_actionToggle_Panel_triggered)
    self.ui_module.actionOpen.triggered.connect(self.on_actionOpen_triggered)
    self.ui_module.actionClosePdf.triggered.connect(self.on_actionClosePdf_triggered)
    self.ui_module.actionSave.triggered.connect(self.on_actionSave_triggered)
    self.ui_module.actionSaveAs.triggered.connect(self.on_actionSaveAs_triggered)
    self.ui_module.actionSave_Page_As_Image.triggered.connect(self.on_actionSave_Page_As_Image_triggered)
    self.ui_module.actionQuit.triggered.connect(self.on_actionQuit_triggered)
    self.ui_module.actionAbout.triggered.connect(self.on_actionAbout_triggered)
    self.ui_module.actionAboutPdf.triggered.connect(self.on_actionAboutPdf_triggered)
    self.ui_module.actionCompress.triggered.connect(self.on_actionCompress_triggered)
    self.ui_module.actionAddFile.triggered.connect(self.on_actionAddFile_triggered)
    self.ui_module.actionPasswordDoc.triggered.connect(self.on_actionPasswordDoc_triggered)
    self.ui_module.actionPrint.triggered.connect(self.on_actionPrint_triggered)
    self.ui_module.actionEnumeratePages.triggered.connect(self.on_actionEnumeratePages_triggered)
    self.ui_module.actionJumpToFirstPage.triggered.connect(self.on_actionJumpToFirstPage_triggered)
    self.ui_module.actionJumpToLastPage.triggered.connect(self.on_actionJumpToLastPage_triggered)
    self.ui_module.actionPrevious_Page.triggered.connect(self.on_actionPrevious_Page_triggered)
    self.ui_module.actionNext_Page.triggered.connect(self.on_actionNext_Page_triggered)
    self.ui_module.actionZoom_In.triggered.connect(self.on_actionZoom_In_triggered)
    self.ui_module.actionZoom_Out.triggered.connect(self.on_actionZoom_Out_triggered)
    self.ui_module.actionFitToWidth.triggered.connect(self.on_actionFitToWidth_triggered)
    self.ui_module.actionFitToHeight.triggered.connect(self.on_actionFitToHeight_triggered)
    self.ui_module.actionRotateViewClockwise.triggered.connect(self.on_actionRotateViewClockwise_triggered)
    self.ui_module.actionRotateViewCounterclockwise.triggered.connect(
        self.on_actionRotateViewCounterclockwise_triggered)
    self.ui_module.actionDeletePage.triggered.connect(self.on_actionDeletePage_triggered)
    self.ui_module.actionDeleteSpecificPages.triggered.connect(self.on_actionDeleteSpecificPages_triggered)
    self.ui_module.actionMovePageDown.triggered.connect(self.on_actionMovePageDown_triggered)
    self.ui_module.actionMovePageUp.triggered.connect(self.on_actionMovePageUp_triggered)
    self.ui_module.actionRotateCurrentPageClockwise.triggered.connect(
        self.on_actionRotateCurrentPageClockwise_triggered)
    self.ui_module.actionRotateCurrentPageCounterclockwise.triggered.connect(
        self.on_actionRotateCurrentPageCounterclockwise_triggered)
    self.ui_module.actionRotateSpecificPages.triggered.connect(
        self.on_actionRotateSpecificPages_triggered)
    self.ui_module.actionDraw.triggered.connect(self.on_actionDraw_triggered)
    self.ui_module.actionEmail.triggered.connect(self.on_actionEmail_triggered)

    # Extra elements and overwritten signal connections:
    self.ui_module.bookmarkView.clicked.connect(self.bookmark_selected)  # Single-click to jump to bookmark

    # self.pdf_viewer.zoomFactorChanged.connect(self.ui_module.m_zoomSelector.set_zoom_factor)
    # self.ui_module.m_zoomSelector.zoom_mode_changed.connect(self.pdf_viewer.setZoomMode)
    # self.ui_module.m_zoomSelector.zoom_factor_changed.connect(self.pdf_viewer.setZoomFactor)
    # self.ui_module.m_zoomSelector.reset()
    # self.pdf_viewer.viewport().installEventFilter(self.main_window)

    # Thumbnail panel:
    self.ui_module.thumbnailList.itemClicked.connect(self.thumbnail_clicked)
    self.ui_module.thumbnail_size_slider.valueChanged.connect(self.adjust_thumbnail_size)
    self.thumbnail_timer.timeout.connect(self.generate_thumbnails)
    self.ui_module.thumbnailList.setContextMenuPolicy(Qt.CustomContextMenu)
    self.ui_module.thumbnailList.customContextMenuRequested.connect(self.show_thumbnail_context_menu)


# endregion Action Connections

# ------------------------ Helper functions ------------------------
# region SORT THESE HELPER FUNCTIONS

def get_pages_in_range(page_range, page_type):
    """
    Get the list of pages based on the range and type (all, odd, even).
    :param page_range: Tuple indicating start and end page (1-based).
    :param page_type: String ('каждой странице', 'четным страницам', 'нечетным страницам').
    :return: List of pages to process (0-based indices).
    """
    start_page, end_page = page_range

    # Ensure 1-based pages are converted to 0-based correctly
    start_page -= 1
    end_page -= 1

    # Prevent page range from going negative
    start_page = max(start_page, 0)
    end_page = max(end_page, 0)

    pages = list(range(start_page, end_page + 1))  # Corrected to be 0-based range

    # Apply page type filtering (even/odd/all)
    if page_type == "четным страницам":
        pages = [p for p in pages if (p + 1) % 2 == 0]
    elif page_type == "нечетным страницам":
        pages = [p for p in pages if (p + 1) % 2 != 0]

    return pages


def rotate_pdf_pages(file_path, rotation_angle, page_number=None):
    """
    Rotate specified pages in a PDF file.

    :param file_path: Path to the PDF file
    :param rotation_angle: Angle to rotate (positive for clockwise, negative for counterclockwise)
    :param page_number: Page number (0-based index) to rotate. If None, all pages will be rotated.
    """
    with fitz.open(file_path) as doc:
        try:
            if page_number is None:  # Rotate all pages
                for page_num in range(doc.page_count):
                    page = doc.load_page(page_num)
                    current_rotation = page.rotation
                    new_rotation = (current_rotation + rotation_angle) % 360
                    page.set_rotation(new_rotation)
            else:  # Rotate a specific page or list of pages
                if isinstance(page_number, list):  # Rotate multiple pages
                    pages_to_rotate = page_number
                else:  # Rotate single page
                    pages_to_rotate = [page_number]

                for page_num in pages_to_rotate:
                    page = doc.load_page(page_num)
                    current_rotation = page.rotation
                    new_rotation = (current_rotation + rotation_angle) % 360
                    page.set_rotation(new_rotation)

            doc.save(file_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        except Exception as e:
            raise Exception(f"Failed to rotate pages: {str(e)}")


def get_document(self, path_to_open):
    """Helper function to open the document and return the fitz document object."""
    if not path_to_open:
        messagebox_warn(self.main_window, "Ошибка", "Файл PDF не загружен.")
        return None
    try:
        doc = fitz.open(path_to_open)
        return doc
    except Exception as e:
        messagebox_warn(self.main_window, "Ошибка", f"Не удалось открыть PDF: {str(e)}")
        return None


def display_pdf_metadata(main_window, doc, file_path):
    """Extracts metadata from the document and displays it in a message box."""
    # Metadata information
    metadata = doc.metadata
    num_pages = doc.page_count
    file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
    is_encrypted = "Да" if doc.is_encrypted else "Нет"
    has_toc = "Да" if doc.get_toc() else "Нет"

    # Helper function to format metadata fields
    def get_field(field):
        return metadata.get(field, '') or "Не указано"

    # Helper function to format PDF dates
    def format_pdf_date(date_str):
        try:
            return datetime.strptime(date_str[2:16], "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return "Не указано"

    # Extract and format metadata
    title = get_field('title')
    author = get_field('author')
    subject = get_field('subject')
    keywords = get_field('keywords')
    creation_date = format_pdf_date(get_field('creationDate'))
    modification_date = format_pdf_date(get_field('modDate'))
    producer = get_field('producer')
    creator = get_field('creator')

    # Format all information into a readable message
    info_message = (
        f"Название: {title}\n"
        f"Автор: {author}\n"
        f"Тема: {subject}\n"
        f"Ключевые слова: {keywords}\n"
        f"Создано: {creation_date}\n"
        f"Изменено: {modification_date}\n"
        f"Создатель документа: {creator}\n"
        f"Программа-создатель: {producer}\n"
        f"Число страниц: {num_pages}\n"
        f"Размер файла: {file_size:.2f} МБ\n"
        f"Зашифрован: {is_encrypted}\n"
        f"Содержит закладки: {has_toc}"
    )

    # Show the formatted information in a message box
    messagebox_about(main_window, "Сведения о документе", info_message)


def get_page_format(width_mm, height_mm):
    formats = {
        'A4': (210, 297),
        'A3': (297, 420),
        'Письмо': (215.9, 279.4),
        'Официальный': (215.9, 355.6)
    }
    # Always compare with the smaller dimension as width and the larger as height
    page_width, page_height = min(width_mm, height_mm), max(width_mm, height_mm)

    for format_name, (format_width, format_height) in formats.items():
        format_width, format_height = min(format_width, format_height), max(format_width, format_height)
        if (abs(page_width - format_width) < 5 and abs(page_height - format_height) < 5):
            return format_name
    return "Неопределённый"


class InsertPageDialog(QDialog):
    def __init__(self, parent=None, max_pages=1, current_page=1):
        super().__init__(parent)
        self.max_pages = max_pages
        self.current_page = current_page
        self.setWindowTitle("Вставить файл")
        self.setModal(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Insert before or after the selected page
        position_group = QGroupBox("Место для вставки")
        position_layout = QHBoxLayout()
        self.before_radio = QRadioButton("До указанной страницы")
        self.after_radio = QRadioButton("После указанной страницы")
        self.after_radio.setChecked(True)  # Default to after
        position_layout.addWidget(self.before_radio)
        position_layout.addWidget(self.after_radio)
        position_group.setLayout(position_layout)
        layout.addWidget(position_group)

        # Page selection (First, Last, Specific)
        page_group = QGroupBox("Страница")
        page_layout = QVBoxLayout()
        self.first_page_radio = QRadioButton(f"Первая страница (1)")
        self.last_page_radio = QRadioButton(f"Последняя страница ({self.max_pages})")
        self.specific_page_radio = QRadioButton(f"Выбранная:")
        self.specific_page_radio.setChecked(True)

        self.page_spinbox = QSpinBox()
        self.page_spinbox.setRange(1, self.max_pages)
        self.page_spinbox.setValue(self.current_page)

        page_layout.addWidget(self.first_page_radio)
        page_layout.addWidget(self.last_page_radio)
        page_layout.addWidget(self.specific_page_radio)
        page_layout.addWidget(self.page_spinbox)

        page_group.setLayout(page_layout)
        layout.addWidget(page_group)

        # Buttons (OK/Cancel)
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Отмена")
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # Connect signals
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.first_page_radio.toggled.connect(self.toggle_page_selection)
        self.last_page_radio.toggled.connect(self.toggle_page_selection)
        self.specific_page_radio.toggled.connect(self.toggle_page_selection)

    def toggle_page_selection(self):
        self.page_spinbox.setEnabled(self.specific_page_radio.isChecked())

    def get_insertion_settings(self):
        """Return the insertion position (before/after) and the specific page."""
        insert_before_position = self.before_radio.isChecked()
        if self.first_page_radio.isChecked():
            specific_page = 0
        elif self.last_page_radio.isChecked():
            specific_page = self.max_pages - 1
        else:
            specific_page = self.page_spinbox.value() - 1  # Convert to 0-based
        return insert_before_position, specific_page


def insert_file_into_pdf(main_pdf_file, insertion_file, insert_before_position, specified_page):
    """
    Insert a PDF or image into a PDF at a specific location.

    :param main_pdf_file: The PDF file to insert into.
    :param insertion_file: The file to insert (PDF or image).
    :param insert_before_position: Boolean indicating insertion before (True) or after (False) the page.
    :param specified_page: 0-based page index to insert before/after.
    """
    with fitz.open(main_pdf_file) as doc:
        insert_doc = fitz.open(insertion_file)

        file_extension = os.path.splitext(insertion_file)[1].lower()

        # Insert pages based on whether it's before or after
        if insert_before_position:
            insert_at = specified_page
        else:
            insert_at = specified_page + 1  # Insert after the selected page

        # If the inserted file is an image, convert it to a single-page PDF
        if file_extension in [".png", ".jpg", ".jpeg", ".bmp"]:
            # Convert the image to a PDF and insert it
            img = fitz.open(insertion_file)
            pdfbytes = img.convert_to_pdf()
            imgPDF = fitz.open("pdf", pdfbytes)
            doc.insert_pdf(imgPDF, start_at=insert_at)
            insert_at += 1
            img.close()
        elif file_extension == ".pdf":
            # Insert PDF pages
            doc.insert_pdf(insert_doc, start_at=insert_at)
        else:
            return

        # Save changes
        doc.save(main_pdf_file, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)


# endregion SORT THESE FUNCTIONS

# ------------------------ Message Dialogs ------------------------
# region Message Dialogs

def messagebox_crit(self, title, message):
    """Displays critical error message dialog with the provided message."""
    QMessageBox.critical(self, title, message)


def messagebox_warn(self, title, message):
    """Displays warning error message dialog with the provided message."""
    QMessageBox.warning(self, title, message)


def messagebox_about(self, title, message):
    """Displays about message dialog with the provided message."""
    QMessageBox.about(self, title, message)


def messagebox_info(self, title, message):
    """Displays information message dialog with the provided message."""
    QMessageBox.information(self, title, message)


def messagebox_question(self, title, message):
    """Displays question message dialog with the provided message."""
    QMessageBox.question(self, title, message)


# endregion Message Dialogs

# ------------------------ Thumbnail Widget ------------------------
# region Thumbnail Widget

class ThumbnailWidget(QWidget):
    def __init__(self, pixmap, page_number, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.image_label = QLabel()
        self.image_label.setScaledContents(True)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setPixmap(pixmap)
        self.page_label = QLabel(f"Страница {page_number + 1}")
        self.page_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)
        layout.addWidget(self.page_label)
        self.setLayout(layout)

    def setThumbnailSize(self, size):
        self.image_label.setFixedSize(size, size)
        self.setFixedSize(size + 10, size + 30)  # Add some padding


# Thumbnails
class ThumbnailWorkerSignals(QObject):
    finished = Signal(int, QPixmap)


# Thumbnails
class ThumbnailWorker(QRunnable):
    def __init__(self, page, page_num, matrix):
        super().__init__()
        self.page = page
        self.page_num = page_num
        self.matrix = matrix
        self.signals = ThumbnailWorkerSignals()

    def run(self):
        pix = self.page.get_pixmap(matrix=self.matrix)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(img)
        self.signals.finished.emit(self.page_num, pixmap)


# endregion Thumbnail Widget


def delete_pdf_page(file_path, page_number):
    """
    Delete a specific page in a PDF file.

    :param file_path: Path to the PDF file.
    :param page_number: 0-based index of the page to delete.
    """
    with fitz.open(file_path) as doc:
        try:
            doc.delete_page(page_number)
            doc.save(file_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        except Exception as e:
            raise Exception(f"Не удалось удалить страницу: {str(e)}")


def move_pdf_page(file_path, page_from, page_to):
    """
    Move a page from one position to another in a PDF file.

    :param file_path: Path to the PDF file.
    :param page_from: The original position of the page (0-based).
    :param page_to: The new position of the page (0-based).
    """
    with fitz.open(file_path) as doc:
        try:
            doc.move_page(page_from, page_to)
            doc.save(file_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        except Exception as e:
            raise Exception(f"Не удалось переместить страницу: {str(e)}")
