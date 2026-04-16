import os
import sys
from argparse import ArgumentParser, RawTextHelpFormatter

from PySide6.QtCore import QLocale, Qt, QTranslator, QLibraryInfo
from PySide6.QtGui import QIcon, QPalette, QGuiApplication, QColor
from PySide6.QtWidgets import QApplication

# Add current directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main_window import MainWindow


def install_russian_qt_translations(app: QApplication) -> None:
    """
    Install Qt's own Russian translations so that built-in dialogs
    (QColorDialog, QPrintDialog, QFileDialog, etc.) display in Russian
    regardless of the system locale.
    """
    ru_locale = QLocale(QLocale.Language.Russian, QLocale.Country.Russia)
    QLocale.setDefault(ru_locale)

    qt_translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)

    for catalog in ("qtbase_ru", "qt_ru"):
        translator = QTranslator(app)
        if translator.load(catalog, qt_translations_path):
            app.installTranslator(translator)
            break  # one successful load is enough


def setup_application():
    """Setup application properties and style"""
    argument_parser = ArgumentParser(description="AltPDF",
                                     formatter_class=RawTextHelpFormatter)
    argument_parser.add_argument("file", help="The file to open",
                                 nargs='?', type=str)

    if sys.platform.startswith("win32"):
        sys.argv += ['-platform', 'windows:darkmode=1']

    app = QApplication(sys.argv)

    # Install Russian translations for all built-in Qt dialogs
    # (QColorDialog, QPrintDialog, QFileDialog, etc.)
    install_russian_qt_translations(app)

    if sys.platform.startswith("linux"):
        app.setStyle("Fusion")

        # Explicitly set light palette
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#f5f5f5"))
        palette.setColor(QPalette.WindowText, Qt.black)
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.Text, Qt.black)
        palette.setColor(QPalette.Button, QColor("#f0f0f0"))
        palette.setColor(QPalette.AlternateBase, Qt.lightGray)
        palette.setColor(QPalette.ButtonText, Qt.black)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor("#0066cc"))
        palette.setColor(QPalette.Highlight, Qt.blue)
        palette.setColor(QPalette.HighlightedText, Qt.white)
        app.setPalette(palette)

        QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)

    # Set application properties
    app.setApplicationName("Редактор PDF Альт")
    app.setApplicationVersion("0.8.12")
    app.setApplicationDisplayName("Редактор PDF Альт")
    app.setOrganizationName("PDF Tools")
    app.setOrganizationDomain("sng.ru")

    # Set application icon if available
    try:
        app.setWindowIcon(QIcon(":/icons/app_icon.png"))
    except Exception:
        pass

    return app


def get_system_language():
    """Get system language for localization"""
    locale = QLocale.system()
    language = locale.name()

    language = 'ru'  # Overwritten for personal purposes

    # Map system locales to our supported languages
    if language.startswith('ru'):
        return 'ru-RU'
    elif language.startswith('en'):
        return 'en-US'
    else:
        return 'ru-RU'  # Default to Russian


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
