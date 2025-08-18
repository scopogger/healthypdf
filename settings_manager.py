from PySide6.QtCore import QSettings, QSize, QPoint, QStandardPaths


class SettingsManager:
    DEFAULT_SIZE = QSize(1200, 700)
    DEFAULT_POSITION = QPoint(200, 200)

    def __init__(self):
        self.settings = QSettings("YourCompany", "PDFEditor")

    def save_window_state(self, size: QSize, position: QPoint, maximized: bool):
        self.settings.setValue("window/size", size)
        self.settings.setValue("window/position", position)
        self.settings.setValue("window/maximized", maximized)

    def load_window_state(self):
        size = self.settings.value("window/size", self.DEFAULT_SIZE)
        position = self.settings.value("window/position", self.DEFAULT_POSITION)
        maximized = self.settings.value("window/maximized", False, type=bool)
        return size, position, maximized

    def save_last_directory(self, directory: str):
        self.settings.setValue("last_directory", directory)

    def get_last_directory(self):
        return self.settings.value("last_directory", QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation))


settings_manager = SettingsManager()
