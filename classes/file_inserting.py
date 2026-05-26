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
    Left side: controls. Right side: live preview of placement.
    """

    _PREVIEW_W = 220
    _PREVIEW_H = 260

    def __init__(self, parent=None, image_path: str = ""):
        super().__init__(parent)
        self.image_path = image_path
        self.setWindowTitle("Параметры вставки изображения")
        self.setModal(True)
        self.setMinimumWidth(620)

        self._img_w, self._img_h = self._read_image_size(image_path)
        self._updating_size = False

        # ── Root layout: controls left, preview right ────────────────────
        root = QHBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(12, 12, 12, 12)

        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(8)
        root.addLayout(controls_layout, stretch=1)

        # ── Preview panel ────────────────────────────────────────────────
        preview_outer = QVBoxLayout()
        preview_label_title = QLabel("Предпросмотр")
        preview_label_title.setAlignment(Qt.AlignCenter)
        preview_label_title.setStyleSheet("font-weight: bold; font-size: 11px;")
        preview_outer.addWidget(preview_label_title)

        self.previewLabel = QLabel()
        self.previewLabel.setFixedSize(self._PREVIEW_W, self._PREVIEW_H)
        self.previewLabel.setAlignment(Qt.AlignCenter)
        self.previewLabel.setStyleSheet(
            "background: #e8e8e8; border: 1px solid #bbb; border-radius: 3px;"
        )
        preview_outer.addWidget(self.previewLabel)
        preview_outer.addStretch()
        root.addLayout(preview_outer)

        # ════════════════════════════════════════════════════════════════
        # Controls (top to bottom)
        # ════════════════════════════════════════════════════════════════

        # ── Row 1: Format + Orientation side by side ─────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        fmt_group = QGroupBox("Формат")
        fmt_lay = QVBoxLayout(fmt_group)
        fmt_lay.setContentsMargins(6, 4, 6, 4)
        self.formatCombo = QComboBox()
        self.formatCombo.addItems(list(PAGE_SIZES_PT.keys()))
        self.formatCombo.setCurrentText("A4")
        fmt_lay.addWidget(self.formatCombo)
        row1.addWidget(fmt_group)

        ori_group = QGroupBox("Ориентация")
        ori_lay = QVBoxLayout(ori_group)
        ori_lay.setContentsMargins(6, 4, 6, 4)
        ori_lay.setSpacing(2)
        self.oriPortrait  = QRadioButton("Книжная")
        self.oriLandscape = QRadioButton("Альбомная")
        self.oriAuto      = QRadioButton("По изображению")
        self.oriAuto.setChecked(True)
        for rb in (self.oriPortrait, self.oriLandscape, self.oriAuto):
            ori_lay.addWidget(rb)
        row1.addWidget(ori_group)

        controls_layout.addLayout(row1)

        # ── Row 2: Horizontal + Vertical alignment side by side ──────────
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        halign_group = QGroupBox("По горизонтали")
        halign_lay = QVBoxLayout(halign_group)
        halign_lay.setContentsMargins(6, 4, 6, 4)
        halign_lay.setSpacing(2)
        self.halignLeft   = QRadioButton("По левому краю")
        self.halignCenter = QRadioButton("По центру")
        self.halignRight  = QRadioButton("По правому краю")
        self.halignCenter.setChecked(True)
        for rb in (self.halignLeft, self.halignCenter, self.halignRight):
            halign_lay.addWidget(rb)
        row2.addWidget(halign_group)

        valign_group = QGroupBox("По вертикали")
        valign_lay = QVBoxLayout(valign_group)
        valign_lay.setContentsMargins(6, 4, 6, 4)
        valign_lay.setSpacing(2)
        self.valignTop    = QRadioButton("По верхнему краю")
        self.valignMiddle = QRadioButton("По центру")
        self.valignBottom = QRadioButton("По нижнему краю")
        self.valignMiddle.setChecked(True)
        for rb in (self.valignTop, self.valignMiddle, self.valignBottom):
            valign_lay.addWidget(rb)
        row2.addWidget(valign_group)

        controls_layout.addLayout(row2)

        # ── Row 3: Size ──────────────────────────────────────────────────
        size_group = QGroupBox("Размер")
        size_vlay = QVBoxLayout(size_group)
        size_vlay.setContentsMargins(6, 4, 6, 6)
        size_vlay.setSpacing(4)

        self.sizeFit      = QRadioButton("Вписать в страницу")
        self.sizeOriginal = QRadioButton("Без изменений")
        self.sizeCustom   = QRadioButton("Свой размер:")
        self.sizeFit.setChecked(True)

        size_vlay.addWidget(self.sizeFit)
        size_vlay.addWidget(self.sizeOriginal)
        size_vlay.addWidget(self.sizeCustom)

        custom_row = QHBoxLayout()
        custom_row.setSpacing(4)
        custom_row.addWidget(QLabel("Ш:"))
        self.customW = QDoubleSpinBox()
        self.customW.setRange(1, 5000)
        self.customW.setSuffix(" пт")
        self.customW.setValue(float(self._img_w) if self._img_w else 200.0)
        self.customW.setFixedWidth(90)
        custom_row.addWidget(self.customW)

        custom_row.addSpacing(6)
        custom_row.addWidget(QLabel("В:"))
        self.customH = QDoubleSpinBox()
        self.customH.setRange(1, 5000)
        self.customH.setSuffix(" пт")
        self.customH.setValue(float(self._img_h) if self._img_h else 200.0)
        self.customH.setFixedWidth(90)
        custom_row.addWidget(self.customH)
        custom_row.addStretch()

        self.keepAspect = QCheckBox("Сохранить пропорции")
        self.keepAspect.setChecked(True)

        size_vlay.addLayout(custom_row)
        size_vlay.addWidget(self.keepAspect)
        controls_layout.addWidget(size_group)

        # ── Buttons ──────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        controls_layout.addStretch()
        controls_layout.addWidget(buttons)

        # ── Wire all signals → preview ───────────────────────────────────
        for rb in (self.oriPortrait, self.oriLandscape, self.oriAuto,
                   self.halignLeft, self.halignCenter, self.halignRight,
                   self.valignTop, self.valignMiddle, self.valignBottom,
                   self.sizeFit, self.sizeOriginal, self.sizeCustom):
            rb.toggled.connect(self._refresh_preview)

        self.formatCombo.currentIndexChanged.connect(self._refresh_preview)

        for rb in (self.sizeFit, self.sizeOriginal, self.sizeCustom):
            rb.toggled.connect(self._on_size_mode_changed)
        self._on_size_mode_changed()

        self.customW.valueChanged.connect(self._on_w_changed)
        self.customH.valueChanged.connect(self._on_h_changed)
        self.customW.valueChanged.connect(self._refresh_preview)
        self.customH.valueChanged.connect(self._refresh_preview)
        self.keepAspect.stateChanged.connect(self._refresh_preview)

        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _read_image_size(self, path: str):
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
                return float(pm.width()), float(pm.height())
        except Exception:
            pass
        return 0.0, 0.0

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

    # ------------------------------------------------------------------ #
    # Live preview
    # ------------------------------------------------------------------ #
    def _refresh_preview(self):
        from PySide6.QtGui import QPainter, QColor, QPen, QBrush
        from PySide6.QtCore import QRectF

        pw, ph = self.get_page_size_pt()  # page dims in points
        iw = self._img_w or pw * 0.6
        ih = self._img_h or ph * 0.6

        # Image display size in points
        size_mode = self.get_size_mode()
        if size_mode == "fit":
            scale = min(pw / iw, ph / ih)
            disp_w, disp_h = iw * scale, ih * scale
        elif size_mode == "original":
            disp_w, disp_h = iw, ih
        else:
            disp_w, disp_h = self.get_custom_size_pt()

        # Clamp display size to page so preview doesn't look broken
        disp_w = min(disp_w, pw)
        disp_h = min(disp_h, ph)

        # Scale everything to fit inside _PREVIEW_W x _PREVIEW_H with margin
        margin = 16
        avail_w = self._PREVIEW_W - margin * 2
        avail_h = self._PREVIEW_H - margin * 2
        page_scale = min(avail_w / pw, avail_h / ph)

        page_px_w = pw * page_scale
        page_px_h = ph * page_scale
        img_px_w  = disp_w * page_scale
        img_px_h  = disp_h * page_scale

        # Page top-left offset to center page in preview widget
        page_x0 = (self._PREVIEW_W - page_px_w) / 2
        page_y0 = (self._PREVIEW_H - page_px_h) / 2

        # Image position on the page (in page-pixels)
        halign = self.get_halign()
        valign = self.get_valign()

        if halign == "left":
            img_x = 0.0
        elif halign == "right":
            img_x = page_px_w - img_px_w
        else:
            img_x = (page_px_w - img_px_w) / 2.0

        if valign == "top":
            img_y = 0.0
        elif valign == "bottom":
            img_y = page_px_h - img_px_h
        else:
            img_y = (page_px_h - img_px_h) / 2.0

        # ── Draw ─────────────────────────────────────────────────────────
        from PySide6.QtGui import QPixmap
        pm = QPixmap(self._PREVIEW_W, self._PREVIEW_H)
        pm.fill(QColor("#e8e8e8"))

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)

        # Drop shadow
        shadow_rect = QRectF(
            page_x0 + 3, page_y0 + 3, page_px_w, page_px_h
        )
        p.setBrush(QColor(0, 0, 0, 40))
        p.setPen(Qt.NoPen)
        p.drawRect(shadow_rect)

        # Page background
        page_rect = QRectF(page_x0, page_y0, page_px_w, page_px_h)
        p.setBrush(QColor("white"))
        p.setPen(QPen(QColor("#aaa"), 1))
        p.drawRect(page_rect)

        # Image rectangle — checkerboard fill to suggest an image
        img_abs_x = page_x0 + img_x
        img_abs_y = page_y0 + img_y
        img_rect_f = QRectF(img_abs_x, img_abs_y, img_px_w, img_px_h)

        # Checkerboard (2 colours of grey)
        cell = max(4, int(min(img_px_w, img_px_h) / 8))
        p.setClipRect(img_rect_f)
        cols = int(img_px_w / cell) + 2
        rows = int(img_px_h / cell) + 2
        for row in range(rows):
            for col in range(cols):
                color = QColor("#c8d8f0") if (row + col) % 2 == 0 else QColor("#a8b8e0")
                p.fillRect(
                    QRectF(img_abs_x + col * cell,
                           img_abs_y + row * cell,
                           cell, cell),
                    color
                )
        p.setClipping(False)

        # Image border
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#5080c0"), 1))
        p.drawRect(img_rect_f)

        # Small "image" icon lines inside
        if img_px_w > 12 and img_px_h > 12:
            p.setPen(QPen(QColor("#3060a0"), 1))
            cx = img_abs_x + img_px_w / 2
            cy = img_abs_y + img_px_h / 2
            r = min(img_px_w, img_px_h) * 0.18
            p.drawEllipse(QRectF(cx - r, cy - r * 1.5, r * 2, r * 2))
            # horizon line
            p.drawLine(
                int(img_abs_x + img_px_w * 0.1),
                int(img_abs_y + img_px_h * 0.65),
                int(img_abs_x + img_px_w * 0.9),
                int(img_abs_y + img_px_h * 0.65)
            )
            # mountain shape
            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            poly = QPolygonF([
                QPointF(img_abs_x + img_px_w * 0.1,  img_abs_y + img_px_h * 0.65),
                QPointF(img_abs_x + img_px_w * 0.38, img_abs_y + img_px_h * 0.38),
                QPointF(img_abs_x + img_px_w * 0.55, img_abs_y + img_px_h * 0.55),
                QPointF(img_abs_x + img_px_w * 0.70, img_abs_y + img_px_h * 0.42),
                QPointF(img_abs_x + img_px_w * 0.9,  img_abs_y + img_px_h * 0.65),
            ])
            p.drawPolyline(poly)

        p.end()
        self.previewLabel.setPixmap(pm)

    # ── Public getters ──────────────────────────────────────────────── #
    def get_page_size_pt(self):
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
=
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
