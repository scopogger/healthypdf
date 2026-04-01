import os
import tempfile
import fitz
from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog, QLineEdit, QDialog, QVBoxLayout, QHBoxLayout, \
    QLabel, QComboBox, QRadioButton, QSpinBox, QDialogButtonBox


class InsertFile:

    def __init__(self, main_window, ui, pv):
        self.merged_doc = None
        self.cur_doc = None
        self.new_doc = None
        self.main_window = main_window
        self.ui = ui
        self.pv = pv

    def add_file_to_document(self):
        # Select file to merge
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Выберите файл для добавления",
            "",
            "PDF Files and Images (*.pdf *.png *.bmp *.jpg)"
        )
        print(f"file_path {file_path}")
        if not file_path:
            return

        try:
            # Open the document to append
            if file_path.upper().endswith(('.JPG', '.BMP', '.PNG')):
                self.new_doc = fitz.open(file_path)  # new_doc = fitz.Image(file_path)
            elif file_path.upper().endswith('.PDF'):
                self.new_doc = fitz.open(file_path)
        except Exception as e:
            QMessageBox.critical(self.main_window, "Error", f"Failed to open file:\n{e}")
            return
        try:
            if self.new_doc.needs_pass:
                authed = False
                for _ in range(3):
                    pw, ok = QInputDialog.getText(self.main_window, "Password",
                                                  f"Введите пароль для {os.path.basename(file_path)}:",
                                                  QLineEdit.Password)
                    if not ok:
                        break
                    if self.new_doc.authenticate(pw):
                        authed = True
                        break
                if not authed:
                    QMessageBox.critical(self.main_window, "Error", "Неверный пароль или операция была отменена.")
                    self.new_doc.close()
                    return

            # Get current document
            self.cur_doc = self.pv.document.current_doc

            current_page = self.pv.get_current_page()

            dialog = InsertPageDialogue(self.main_window, max_pages=self.cur_doc.page_count, current_page=current_page)

            if dialog.exec() != QDialog.Accepted:
                self.new_doc.close()
                return

            location, target, page_num = dialog.get_insertion_settings()

            insert_at_page = page_num - 1  # 0-based index

            insert_before = location == "before"

            print(f"location: {location}, target: {target}, page_num: {page_num}, insert_at_page: {insert_at_page}")

            # Create a new merged document
            self.merged_doc = fitz.open()

            if target == "first":
                self._merging(insert_before, 0)

            elif target == "last":
                self._merging(insert_before, len(self.cur_doc) - 1)

            else:  # target == "page"
                self._merging(insert_before, insert_at_page)

            # Save merged document to a temporary file
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            self.merged_doc.save(temp_path)
            self.merged_doc.close()
            self.new_doc.close()

            # Close current document properly
            self.pv.close_document()

            # Load the merged document
            success = self.pv.open_document(temp_path)

            if success:
                # Update the document path to the temp file
                self.pv.doc_path = temp_path

                # Update thumbnails
                if hasattr(self.ui, 'thumbnailList'):
                    try:
                        self.ui.thumbnailList.set_document(self.pv.document)
                    except Exception as e:
                        print(f"Thumbnail update failed: {e}")

                # Mark as modified and update UI
                self.pv.is_modified = True
                self.main_window.is_document_modified = True
                self.main_window.update_ui_state()
                self.main_window.update_page_info()
                QMessageBox.information(self.main_window, "Успех", "Файлы успешно объединены!")
            else:
                QMessageBox.critical(self.main_window, "Ошибка", "Не удалось открыть объединённые документы.")

        except Exception as e:
            try:
                self.new_doc.close()
            except:
                pass
            QMessageBox.critical(self.main_window, "Ошибка", f"Ошибка при объединении документов: {e}")
        finally:
            self.new_doc = None
            self.cur_doc = None
            self.merged_doc = None

    def _merging(self, insert_before: bool, insert_at_page: int):
        if insert_before:
            if insert_at_page > 0:
                self.merged_doc.insert_pdf(self.cur_doc, to_page=insert_at_page - 1)
            self.merged_doc.insert_file(self.new_doc)  # insert_pdf
            if insert_at_page < self.cur_doc.page_count:
                self.merged_doc.insert_pdf(self.cur_doc, from_page=insert_at_page)
        else:  # insert after
            if insert_at_page < self.cur_doc.page_count:
                self.merged_doc.insert_pdf(self.cur_doc, to_page=insert_at_page)
            self.merged_doc.insert_file(self.new_doc)  # insert_pdf
            if insert_at_page + 1 < self.cur_doc.page_count:
                self.merged_doc.insert_pdf(self.cur_doc, from_page=insert_at_page + 1)


class InsertPageDialogue(QDialog):
    def __init__(self, parent=None, max_pages=1, current_page=1):
        super().__init__(parent)
        self.setWindowTitle("Выберите позицию вставки")

        layout = QVBoxLayout()

        # === Line 1: Местоположение + combobox ===
        location_layout = QHBoxLayout()
        location_label = QLabel("Местоположение:")
        self.location_combo = QComboBox()
        self.location_combo.addItems(["Перед", "После"])
        self.location_combo.setCurrentIndex(1)  # default to "После"
        location_layout.addWidget(location_label)
        location_layout.addWidget(self.location_combo)
        location_layout.addStretch()
        layout.addLayout(location_layout)

        # === Line 2: Первой страницы ===
        self.first_page_radio = QRadioButton("Первой страницы")
        layout.addWidget(self.first_page_radio)

        # === Line 3: Последней страницей ===
        self.last_page_radio = QRadioButton("Последней страницей")
        self.last_page_radio.setChecked(True)  # default
        layout.addWidget(self.last_page_radio)

        # === Line 4: Стр. [spin] из [max] ===
        custom_page_layout = QHBoxLayout()
        self.custom_page_radio = QRadioButton("Стр.")
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(max_pages)
        self.page_spin.setValue(current_page)
        self.total_pages_label = QLabel(f"из {max_pages}")

        custom_page_layout.addWidget(self.custom_page_radio)
        custom_page_layout.addWidget(self.page_spin)
        custom_page_layout.addWidget(self.total_pages_label)
        custom_page_layout.addStretch()
        layout.addLayout(custom_page_layout)

        # === Mutual exclusivity for page options ===
        self.first_page_radio.toggled.connect(self._update_page_controls)
        self.last_page_radio.toggled.connect(self._update_page_controls)
        self.custom_page_radio.toggled.connect(self._update_page_controls)

        self._update_page_controls()

        # === OK/Cancel buttons ===
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.setLayout(layout)

    def _update_page_controls(self):
        # Enable spinbox only when custom_page_radio is checked
        self.page_spin.setEnabled(self.custom_page_radio.isChecked())
        # Ensure only one of the three is checked (redundant but safe)
        if self.first_page_radio.isChecked():
            self.last_page_radio.setChecked(False)
            self.custom_page_radio.setChecked(False)
        elif self.last_page_radio.isChecked():
            self.first_page_radio.setChecked(False)
            self.custom_page_radio.setChecked(False)
        elif self.custom_page_radio.isChecked():
            self.first_page_radio.setChecked(False)
            self.last_page_radio.setChecked(False)
        # If none checked (e.g., programmatic change), default to last
        if not any((self.first_page_radio.isChecked(),
                    self.last_page_radio.isChecked(),
                    self.custom_page_radio.isChecked())):
            self.last_page_radio.setChecked(True)

    def get_insertion_settings(self):
        """
        Returns:
            location: "before" or "after"
            target: "first", "last", or "page"
            page_num: int (1 for first, max_pages for last, spin value for page)
        """
        location = "before" if self.location_combo.currentText() == "Перед" else "after"

        if self.first_page_radio.isChecked():
            target = "first"
            page_num = 1
        elif self.last_page_radio.isChecked():
            target = "last"
            page_num = self.page_spin.maximum()
        else:  # custom_page_radio
            target = "page"
            page_num = self.page_spin.value()

        return location, target, page_num
