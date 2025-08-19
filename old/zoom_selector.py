from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QComboBox, QMessageBox
from PySide6.QtCore import Signal, Slot


class ZoomSelector(QComboBox):

    zoom_mode_changed = Signal(QPdfView.ZoomMode)
    zoom_factor_changed = Signal(float)

    def __init__(self, parent):
        super().__init__(parent)
        self.pdf_viewer = None
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)  # Prevent adding new items

        # Store the default items
        self._default_items = [
            "По ширине",
            "По высоте",
            "50%",
            "75%",
            "100%",
            "125%",
            "150%",
            "200%",
            "400%",
            "800%",
            "1600%"
        ]

        # Add the default items
        for item in self._default_items:
            super().addItem(item)

        self.currentTextChanged.connect(self.on_current_text_changed)
        self.lineEdit().editingFinished.connect(self._editing_finished)

    @Slot(float)
    def set_zoom_factor(self, zoom_factor):
        # Check if the zoom mode is custom, otherwise skip percentage setting
        if zoom_factor == QPdfView.ZoomMode.FitToWidth:
            self.setCurrentText("По ширине")
        elif zoom_factor == QPdfView.ZoomMode.FitInView:
            self.setCurrentText("По высоте")
        else:
            percent = int(zoom_factor * 100)
            self.setCurrentText(f"{percent}%")

    @Slot()
    def reset(self):
        self.setCurrentIndex(4)  # 100%

    @Slot(str)
    def on_current_text_changed(self, text):
        if text == "По ширине":
            self.zoom_mode_changed.emit(QPdfView.ZoomMode.FitToWidth)
        elif text == "По высоте":
            self.zoom_mode_changed.emit(QPdfView.ZoomMode.FitInView)
        elif text.endswith("%"):
            zoom_level = int(text[:-1])
            factor = zoom_level / 100.0
            self.zoom_mode_changed.emit(QPdfView.ZoomMode.Custom)
            self.zoom_factor_changed.emit(factor)

    def set_pdf_viewer(self, viewer):
        self.pdf_viewer = viewer

    @Slot()
    def _editing_finished(self):
        text = self.lineEdit().text().strip()

        # Extract numbers from the text, ignoring any other characters
        import re
        numbers = re.findall(r'\d+', text)

        if not numbers:
            # No numbers found, revert to previous value
            self.set_zoom_factor(self.pdf_viewer.zoomFactor())
            return

        # Take the first number found
        zoom_level = int(numbers[0])

        # Clamp the value between 10 and 10000
        zoom_level = max(10, min(10000, zoom_level))

        # Update the text to show the cleaned and clamped value
        self.setCurrentText(f"{zoom_level}%")

        # Emit the zoom change signals
        factor = zoom_level / 100.0
        self.zoom_mode_changed.emit(QPdfView.ZoomMode.Custom)
        self.zoom_factor_changed.emit(factor)


    # Override all item insertion methods to prevent adding new items
    def addItem(self, *args, **kwargs):
        pass

    def addItems(self, *args, **kwargs):
        pass

    def insertItem(self, *args, **kwargs):
        pass

    def insertItems(self, *args, **kwargs):
        pass

    def setItemText(self, *args, **kwargs):
        pass
