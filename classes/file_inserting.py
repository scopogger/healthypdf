import os
import tempfile
import fitz
from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QInputDialog, QLineEdit, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QRadioButton,
    QSpinBox, QDialogButtonBox, QGroupBox, QCheckBox, QDoubleSpinBox,
    QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


# A4 and friends in points (1 pt = 1/72 inch)
PAGE_SIZES_PT = {
    "A0": (2383.94, 3370.39),
    "A1": (1683.78, 2383.94),
    "A2": (1190.55, 1683.78),
    "A3": (841.89, 1190.55),
    "A4": (595.28, 841.89),
}


class ImagePlacementDialog(QDialog):
    """
    Shown after the user picks an image file.
    Lets them choose page format, orientation, alignment and sizing.
    """

    def __init__(self, parent=None, image_path: str = ""):
        super().__init__(parent)
        self.image_path = image_path
        self.setWindowTitle("Параметры вставки изображения")
        self.setModal(True)
        self.setMinimumWidth(360)

        # Read image dimensions once for "auto orientation" and proportion lock
        self._img_w, self._img_h = self._read_image_size(image_path)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Page format ──────────────────────────────────────────────────
        fmt_group = QGroupBox("Формат страницы")
        fmt_layout = QHBoxLayout(fmt_group)

        self.formatCombo = QComboBox()
        self.formatCombo.addItems(list(PAGE_SIZES_PT.keys()))
        self.formatCombo.setCurrentText("A4")
        fmt_layout.addWidget(self.formatCombo)
        layout.addWidget(fmt_group)

        # ── Orientation ──────────────────────────────────────────────────
        ori_group = QGroupBox("Ориентация")
        ori_layout = QVBoxLayout(ori_group)

        self.oriPortrait   = QRadioButton("Книжная")
        self.oriLandscape  = QRadioButton("Альбомная")
        self.oriAuto       = QRadioButton("Определить по изображению")
        self.oriAuto.setChecked(True)

        ori_layout.addWidget(self.oriPortrait)
        ori_layout.addWidget(self.oriLandscape)
        ori_layout.addWidget(self.oriAuto)
        layout.addWidget(ori_group)

        # ── Horizontal alignment ─────────────────────────────────────────
        halign_group = QGroupBox("Выравнивание по горизонтали")
        halign_layout = QHBoxLayout(halign_group)

        self.halignLeft   = QRadioButton("По левому краю")
        self.halignCenter = QRadioButton("По центру")
        self.halignRight  = QRadioButton("По правому краю")
        self.halignCenter.setChecked(True)

        halign_layout.addWidget(self.halignLeft)
        halign_layout.addWidget(self.halignCenter)
        halign_layout.addWidget(self.halignRight)
        layout.addWidget(halign_group)

        # ── Vertical alignment ───────────────────────────────────────────
        valign_group = QGroupBox("Выравнивание по вертикали")
        valign_layout = QHBoxLayout(valign_group)

        self.valignTop    = QRadioButton("По верхнему краю")
        self.valignMiddle = QRadioButton("По центру")
        self.valignBottom = QRadioButton("По нижнему краю")
        self.valignMiddle.setChecked(True)

        valign_layout.addWidget(self.valignTop)
        valign_layout.addWidget(self.valignMiddle)
        valign_layout.addWidget(self.valignBottom)
        layout.addWidget(valign_group)

        # ── Size ─────────────────────────────────────────────────────────
        size_group = QGroupBox("Размер")
        size_vlay = QVBoxLayout(size_group)

        self.sizeFit     = QRadioButton("Вписать в страницу")
        self.sizeOriginal = QRadioButton("Не изменять")
        self.sizeCustom  = QRadioButton("Свой размер")
        self.sizeFit.setChecked(True)

        size_vlay.addWidget(self.sizeFit)
        size_vlay.addWidget(self.sizeOriginal)
        size_vlay.addWidget(self.sizeCustom)

        # Custom size fields
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Ш:"))
        self.customW = QDoubleSpinBox()
        self.customW.setRange(1, 5000)
        self.customW.setSuffix(" пт")
        self.customW.setValue(float(self._img_w) if self._img_w else 200.0)
        custom_row.addWidget(self.customW)

        custom_row.addWidget(QLabel("В:"))
        self.customH = QDoubleSpinBox()
        self.customH.setRange(1, 5000)
        self.customH.setSuffix(" пт")
        self.customH.setValue(float(self._img_h) if self._img_h else 200.0)
        custom_row.addWidget(self.customH)

        self.keepAspect = QCheckBox("Сохранить пропорции")
        self.keepAspect.setChecked(True)

        size_vlay.addLayout(custom_row)
        size_vlay.addWidget(self.keepAspect)
        layout.addWidget(size_group)

        # Wire custom-size enable/disable
        for rb in (self.sizeFit, self.sizeOriginal, self.sizeCustom):
            rb.toggled.connect(self._on_size_mode_changed)
        self._on_size_mode_changed()

        # Wire proportion lock
        self._updating_size = False
        self.customW.valueChanged.connect(self._on_w_changed)
        self.customH.valueChanged.connect(self._on_h_changed)

        # ── Buttons ──────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    def _read_image_size(self, path: str):
        """Return (width_pt, height_pt) of the image, or (0, 0) on failure."""
        try:
            doc = fitz.open(path)
            page = doc[0]
            r = page.rect
            w, h = r.width, r.height
            doc.close()
            return w, h
        except Exception:
            pass
        try:
            pm = QPixmap(path)
            if not pm.isNull():
                return pm.width(), pm.height()
        except Exception:
            pass
        return 0, 0

    def _on_size_mode_changed(self):
        custom = self.sizeCustom.isChecked()
        self.customW.setEnabled(custom)
        self.customH.setEnabled(custom)
        self.keepAspect.setEnabled(custom)

    def _on_w_changed(self, val: float):
        if self._updating_size or not self.keepAspect.isChecked():
            return
        if not self._img_w or not self._img_h:
            return
        self._updating_size = True
        self.customH.setValue(val * self._img_h / self._img_w)
        self._updating_size = False

    def _on_h_changed(self, val: float):
        if self._updating_size or not self.keepAspect.isChecked():
            return
        if not self._img_w or not self._img_h:
            return
        self._updating_size = True
        self.customW.setValue(val * self._img_w / self._img_h)
        self._updating_size = False

    # ── Public getters ──────────────────────────────────────────────── #
    def get_page_size_pt(self):
        """Return (width_pt, height_pt) after applying orientation."""
        base_w, base_h = PAGE_SIZES_PT[self.formatCombo.currentText()]
        if self.oriPortrait.isChecked():
            w, h = min(base_w, base_h), max(base_w, base_h)
        elif self.oriLandscape.isChecked():
            w, h = max(base_w, base_h), min(base_w, base_h)
        else:  # auto
            if self._img_w and self._img_h and self._img_w > self._img_h:
                w, h = max(base_w, base_h), min(base_w, base_h)
            else:
                w, h = min(base_w, base_h), max(base_w, base_h)
        return w, h

    def get_halign(self) -> str:
        if self.halignLeft.isChecked():
            return "left"
        if self.halignRight.isChecked():
            return "right"
        return "center"

    def get_valign(self) -> str:
        if self.valignTop.isChecked():
            return "top"
        if self.valignBottom.isChecked():
            return "bottom"
        return "middle"

    def get_size_mode(self) -> str:
        if self.sizeOriginal.isChecked():
            return "original"
        if self.sizeCustom.isChecked():
            return "custom"
        return "fit"

    def get_custom_size_pt(self):
        return self.customW.value(), self.customH.value()


class InsertFile:

    def __init__(self, main_window, ui, pv):
        self.merged_doc = None
        self.cur_doc = None
        self.new_doc = None
        self.main_window = main_window
        self.ui = ui
        self.pv = pv

    def add_file_to_document(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Выберите файл для добавления",
            "",
            "PDF Files and Images (*.pdf *.png *.bmp *.jpg *.jpeg)"
        )
        if not file_path:
            return

        is_image = file_path.upper().endswith(('.JPG', '.JPEG', '.BMP', '.PNG'))
        is_pdf   = file_path.upper().endswith('.PDF')

        try:
            if is_image:
                self._insert_image(file_path)
            elif is_pdf:
                self._insert_pdf(file_path)
            else:
                QMessageBox.warning(self.main_window, "Ошибка",
                                    "Неподдерживаемый формат файла.")
        except Exception as e:
            QMessageBox.critical(self.main_window, "Ошибка",
                                 f"Ошибка при вставке файла:\n{e}")
        finally:
            self.new_doc = None
            self.cur_doc = None
            self.merged_doc = None

    # ------------------------------------------------------------------ #
    # Image insertion
    # ------------------------------------------------------------------ #
    def _insert_image(self, file_path: str):
        # Step 1: placement dialog
        placement = ImagePlacementDialog(self.main_window, file_path)
        if placement.exec() != QDialog.Accepted:
            return

        page_w, page_h = placement.get_page_size_pt()
        halign    = placement.get_halign()
        valign    = placement.get_valign()
        size_mode = placement.get_size_mode()

        # Step 2: build a one-page PDF containing the image
        img_doc  = fitz.open(file_path)
        img_page = img_doc[0]
        img_rect = img_page.rect
        img_w    = img_rect.width
        img_h    = img_rect.height
        img_doc.close()

        # Determine image display size
        if size_mode == "fit":
            scale = min(page_w / img_w, page_h / img_h)
            disp_w, disp_h = img_w * scale, img_h * scale
        elif size_mode == "original":
            disp_w, disp_h = img_w, img_h
        else:  # custom
            disp_w, disp_h = placement.get_custom_size_pt()

        # Horizontal position
        if halign == "left":
            x0 = 0.0
        elif halign == "right":
            x0 = page_w - disp_w
        else:
            x0 = (page_w - disp_w) / 2.0

        # Vertical position
        if valign == "top":
            y0 = 0.0
        elif valign == "bottom":
            y0 = page_h - disp_h
        else:
            y0 = (page_h - disp_h) / 2.0

        target_rect = fitz.Rect(x0, y0, x0 + disp_w, y0 + disp_h)

        # Build a temporary single-page PDF with the image placed on it
        tmp_doc  = fitz.open()
        tmp_page = tmp_doc.new_page(width=page_w, height=page_h)

        # Insert image onto the page
        img_bytes = open(file_path, "rb").read()
        tmp_page.insert_image(target_rect, stream=img_bytes)

        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        tmp_doc.save(tmp_path)
        tmp_doc.close()

        # Step 3: position dialog (reuse existing InsertPageDialogue)
        self.new_doc = fitz.open(tmp_path)
        self._do_merge_flow(tmp_path)

    # ------------------------------------------------------------------ #
    # PDF insertion (unchanged logic, extracted to method)
    # ------------------------------------------------------------------ #
    def _insert_pdf(self, file_path: str):
        try:
            self.new_doc = fitz.open(file_path)
        except Exception as e:
            QMessageBox.critical(self.main_window, "Ошибка",
                                 f"Не удалось открыть файл:\n{e}")
            return

        if self.new_doc.needs_pass:
            authed = False
            for _ in range(3):
                pw, ok = QInputDialog.getText(
                    self.main_window, "Пароль",
                    f"Введите пароль для {os.path.basename(file_path)}:",
                    QLineEdit.Password
                )
                if not ok:
                    break
                if self.new_doc.authenticate(pw):
                    authed = True
                    break
            if not authed:
                QMessageBox.critical(self.main_window, "Ошибка",
                                     "Неверный пароль или операция была отменена.")
                self.new_doc.close()
                return

        self._do_merge_flow(file_path)

    # ------------------------------------------------------------------ #
    # Shared merge flow
    # ------------------------------------------------------------------ #
    def _do_merge_flow(self, source_path: str):
        self.cur_doc     = self.pv.document.current_doc
        current_page     = self.pv.get_current_page()

        dialog = InsertPageDialogue(
            self.main_window,
            max_pages=self.cur_doc.page_count,
            current_page=current_page
        )
        if dialog.exec() != QDialog.Accepted:
            self.new_doc.close()
            return

        location, target, page_num = dialog.get_insertion_settings()
        insert_at_page  = page_num - 1
        insert_before   = (location == "before")

        self.merged_doc = fitz.open()

        if target == "first":
            self._merging(insert_before, 0)
        elif target == "last":
            self._merging(insert_before, len(self.cur_doc) - 1)
        else:
            self._merging(insert_before, insert_at_page)

        fd, merged_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        self.merged_doc.save(merged_path)
        self.merged_doc.close()
        self.new_doc.close()

        self.pv.close_document()
        success = self.pv.open_document(merged_path)

        if success:
            self.pv.doc_path = merged_path
            if hasattr(self.ui, 'thumbnailList'):
                try:
                    self.ui.thumbnailList.set_document(self.pv.document)
                except Exception as e:
                    print(f"Thumbnail update failed: {e}")
            self.pv.is_modified = True
            self.main_window.is_document_modified = True
            self.main_window.update_ui_state()
            self.main_window.update_page_info()
            QMessageBox.information(self.main_window, "Успех",
                                    "Файл успешно вставлен!")
        else:
            QMessageBox.critical(self.main_window, "Ошибка",
                                 "Не удалось открыть результирующий документ.")

    def _merging(self, insert_before: bool, insert_at_page: int):
        if insert_before:
            if insert_at_page > 0:
                self.merged_doc.insert_pdf(self.cur_doc, to_page=insert_at_page - 1)
            self.merged_doc.insert_file(self.new_doc)
            if insert_at_page < self.cur_doc.page_count:
                self.merged_doc.insert_pdf(self.cur_doc, from_page=insert_at_page)
        else:
            if insert_at_page < self.cur_doc.page_count:
                self.merged_doc.insert_pdf(self.cur_doc, to_page=insert_at_page)
            self.merged_doc.insert_file(self.new_doc)
            if insert_at_page + 1 < self.cur_doc.page_count:
                self.merged_doc.insert_pdf(self.cur_doc, from_page=insert_at_page + 1)


class InsertPageDialogue(QDialog):
    def __init__(self, parent=None, max_pages=1, current_page=1):
        super().__init__(parent)
        self.setWindowTitle("Выберите позицию вставки")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        location_layout = QHBoxLayout()
        location_label = QLabel("Местоположение:")
        self.location_combo = QComboBox()
        self.location_combo.addItems(["Перед", "После"])
        self.location_combo.setCurrentIndex(1)
        location_layout.addWidget(location_label)
        location_layout.addWidget(self.location_combo)
        location_layout.addStretch()
        layout.addLayout(location_layout)

        self.first_page_radio  = QRadioButton("Первой страницы")
        self.last_page_radio   = QRadioButton("Последней страницей")
        self.last_page_radio.setChecked(True)
        layout.addWidget(self.first_page_radio)
        layout.addWidget(self.last_page_radio)

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

        for rb in (self.first_page_radio, self.last_page_radio, self.custom_page_radio):
            rb.toggled.connect(self._update_page_controls)
        self._update_page_controls()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_page_controls(self):
        self.page_spin.setEnabled(self.custom_page_radio.isChecked())
        if not any((self.first_page_radio.isChecked(),
                    self.last_page_radio.isChecked(),
                    self.custom_page_radio.isChecked())):
            self.last_page_radio.setChecked(True)

    def get_insertion_settings(self):
        location = "before" if self.location_combo.currentText() == "Перед" else "after"
        if self.first_page_radio.isChecked():
            return location, "first", 1
        if self.last_page_radio.isChecked():
            return location, "last", self.page_spin.maximum()
        return location, "page", self.page_spin.value()
