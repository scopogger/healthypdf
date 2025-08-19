from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QComboBox,
                               QLabel, QSpinBox, QPushButton, QGroupBox)


class PageOperationDialog(QDialog):
    def __init__(self, parent=None, max_pages=1, current_page=1, operation="rotate"):
        super().__init__(parent)
        self.max_pages = max_pages
        self.current_page = current_page
        self.operation = operation
        self.setWindowTitle(f"{'Поворот' if operation == 'rotate' else 'Удаление'} страниц")
        self.setModal(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        if self.operation == "rotate":
            # Rotation angle selection
            rotation_group = QGroupBox("Угол поворота")
            rotation_layout = QHBoxLayout()
            self.rotation_combo = QComboBox()
            self.rotation_combo.addItems(["90°", "-90°", "180°"])
            rotation_layout.addWidget(QLabel("Повернуть на:"))
            rotation_layout.addWidget(self.rotation_combo)
            rotation_group.setLayout(rotation_layout)
            layout.addWidget(rotation_group)

        # Page range selection
        range_group = QGroupBox("Диапазон страниц")
        range_layout = QVBoxLayout()
        self.current_page_radio = QRadioButton(f"Текущая страница ({self.current_page + 1})")
        self.all_pages_radio = QRadioButton("Все страницы")
        self.selected_pages_radio = QRadioButton("Выбранные в боковой панели")
        self.range_pages_radio = QRadioButton("Диапазон страниц")
        self.current_page_radio.setChecked(True)
        range_layout.addWidget(self.current_page_radio)
        # range_layout.addWidget(self.selected_pages_radio)  # Not finished
        if self.operation == "rotate":
            range_layout.addWidget(self.all_pages_radio)
        range_layout.addWidget(self.range_pages_radio)

        range_input_layout = QHBoxLayout()
        self.from_page_spin = QSpinBox()
        self.to_page_spin = QSpinBox()
        self.from_page_spin.setRange(1, self.max_pages)
        self.to_page_spin.setRange(1, self.max_pages)
        self.to_page_spin.setValue(self.max_pages)
        range_input_layout.addWidget(QLabel("С:"))
        range_input_layout.addWidget(self.from_page_spin)
        range_input_layout.addWidget(QLabel("До:"))
        range_input_layout.addWidget(self.to_page_spin)
        range_layout.addLayout(range_input_layout)

        range_group.setLayout(range_layout)
        layout.addWidget(range_group)

        # Page type selection
        type_group = QGroupBox("Тип страницы")
        type_layout = QHBoxLayout()
        self.page_type_combo = QComboBox()
        self.page_type_combo.addItems(["каждой странице", "четным страницам", "нечетным страницам"])
        type_layout.addWidget(QLabel("Применить к:"))
        type_layout.addWidget(self.page_type_combo)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Отмена")
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # Connect signals
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.current_page_radio.toggled.connect(self.toggle_range_inputs)
        self.all_pages_radio.toggled.connect(self.toggle_range_inputs)
        self.range_pages_radio.toggled.connect(self.toggle_range_inputs)

        # Disable at start
        self.from_page_spin.setEnabled(False)
        self.to_page_spin.setEnabled(False)
        self.page_type_combo.setEnabled(False)

    def toggle_range_inputs(self):
        range_enabled = self.range_pages_radio.isChecked()
        self.from_page_spin.setEnabled(range_enabled)
        self.to_page_spin.setEnabled(range_enabled)
        self.page_type_combo.setEnabled(not self.current_page_radio.isChecked())

    def get_operation_settings(self):
        if self.current_page_radio.isChecked():
            page_range = (self.current_page + 1, self.current_page + 1)
        elif self.all_pages_radio.isChecked():
            page_range = (1, self.max_pages)
        else:
            page_range = (self.from_page_spin.value(), self.to_page_spin.value())

        page_type = self.page_type_combo.currentText()

        if self.operation == "rotate":
            rotation = self.rotation_combo.currentText()
            return rotation, page_range, page_type
        else:
            return page_range, page_type
