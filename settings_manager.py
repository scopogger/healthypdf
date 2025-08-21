from PySide6.QtCore import QSettings, QSize, QPoint, QStandardPaths


class SettingsManager:
    DEFAULT_SIZE = QSize(1400, 800)
    DEFAULT_POSITION = QPoint(200, 200)
    MAX_RECENT_FILES = 10

    def __init__(self):
        self.settings = QSettings("YourCompany", "PDFEditor")

    def save_window_state(self, size: QSize, position: QPoint, maximized: bool):
        """Save window state"""
        self.settings.setValue("window/size", size)
        self.settings.setValue("window/position", position)
        self.settings.setValue("window/maximized", maximized)

    def load_window_state(self):
        """Load window state"""
        size = self.settings.value("window/size", self.DEFAULT_SIZE)
        position = self.settings.value("window/position", self.DEFAULT_POSITION)
        maximized = self.settings.value("window/maximized", False, type=bool)
        return size, position, maximized

    def save_last_directory(self, directory: str):
        """Save last used directory"""
        self.settings.setValue("last_directory", directory)

    def get_last_directory(self):
        """Get last used directory"""
        return self.settings.value(
            "last_directory",
            QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        )

    def add_recent_file(self, file_path: str):
        """Add file to recent files list"""
        recent_files = self.get_recent_files()

        # Remove if already exists
        if file_path in recent_files:
            recent_files.remove(file_path)

        # Add to beginning
        recent_files.insert(0, file_path)

        # Limit to maximum
        recent_files = recent_files[:self.MAX_RECENT_FILES]

        # Save back to settings
        self.settings.setValue("recent_files", recent_files)

    def get_recent_files(self):
        """Get list of recent files"""
        return self.settings.value("recent_files", [], type=list)

    def remove_recent_file(self, file_path: str):
        """Remove file from recent files list"""
        recent_files = self.get_recent_files()
        if file_path in recent_files:
            recent_files.remove(file_path)
            self.settings.setValue("recent_files", recent_files)

    def clear_recent_files(self):
        """Clear all recent files"""
        self.settings.setValue("recent_files", [])

    def save_panel_state(self, panel_visible: bool, panel_width: int, active_tab: str):
        """Save side panel state"""
        self.settings.setValue("panel/visible", panel_visible)
        self.settings.setValue("panel/width", panel_width)
        self.settings.setValue("panel/active_tab", active_tab)

    def load_panel_state(self):
        """Load side panel state"""
        visible = self.settings.value("panel/visible", True, type=bool)
        width = self.settings.value("panel/width", 250, type=int)
        active_tab = self.settings.value("panel/active_tab", "pages", type=str)
        return visible, width, active_tab

    def save_thumbnail_size(self, size: int):
        """Save thumbnail size setting"""
        self.settings.setValue("thumbnails/size", size)

    def get_thumbnail_size(self):
        """Get thumbnail size setting"""
        return self.settings.value("thumbnails/size", 150, type=int)

    def save_zoom_level(self, zoom: float):
        """Save last zoom level"""
        self.settings.setValue("view/zoom", zoom)

    def get_zoom_level(self):
        """Get last zoom level"""
        return self.settings.value("view/zoom", 1.0, type=float)

    def save_encryption_passwords(self, file_path: str, password: str):
        """Save password for encrypted PDF (use with caution!)"""
        # Note: This stores passwords in plaintext - consider encryption in production
        self.settings.setValue(f"passwords/{file_path}", password)

    def get_encryption_password(self, file_path: str):
        """Get stored password for encrypted PDF"""
        return self.settings.value(f"passwords/{file_path}", "", type=str)

    def remove_encryption_password(self, file_path: str):
        """Remove stored password"""
        self.settings.remove(f"passwords/{file_path}")


# Global instance
settings_manager = SettingsManager()
