#!/usr/bin/env python3
"""
PDF Editor - Optimized PDF viewer and editor
Main application entry point
"""

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QIcon

# Add current directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main_window import MainWindow


def setup_application():
    """Setup application properties and style"""
    app = QApplication(sys.argv)

    # Set application properties
    app.setApplicationName("PDF Editor")
    app.setApplicationVersion("2.0")
    app.setApplicationDisplayName("PDF Editor")
    app.setOrganizationName("PDF Tools")
    app.setOrganizationDomain("sng.ru")

    # Set application icon if available
    try:
        app.setWindowIcon(QIcon(":/icons/app_icon.png"))
    except:
        pass

    return app


def get_system_language():
    """Get system language for localization"""
    locale = QLocale.system()
    language = locale.name()

    language = 'ru'  # Overwritten

    # Map system locales to our supported languages
    if language.startswith('ru'):
        return 'ru-RU'
    elif language.startswith('en'):
        return 'en-US'
    else:
        return 'en-US'  # Default to English


def main():
    """Main application entry point"""
    try:
        # Create application
        app = setup_application()

        # Determine language
        language = get_system_language()

        # Create and show main window
        window = MainWindow()

        # Apply localization
        try:
            import ui_localization
            ui_localization.translate_ui(window.ui, window, language)
            ui_localization.shortcuts_ui(window.ui)
        except ImportError:
            print("Warning: Could not load localization")

        window.show()

        # Handle command line arguments
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
            if os.path.exists(file_path) and file_path.lower().endswith('.pdf'):
                window.load_document(file_path)

        # Run application
        return app.exec()

    except Exception as e:
        print(f"Critical error starting application: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
