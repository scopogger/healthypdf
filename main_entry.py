import os
import sys

from PySide6.QtCore import QLocale, Qt, QTranslator, QLibraryInfo, QTimer, QUrl
from PySide6.QtGui import QIcon, QPalette, QGuiApplication, QColor
from PySide6.QtWidgets import QApplication

# Add current directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main_window import MainWindow


def _resolve_file_arg(raw: str) -> str:
    """Convert whatever the desktop environment passed us into a plain
    filesystem path.  File managers on Linux can hand us any of:

      /home/user/file.pdf           – plain path  (most common with %F)
      file:///home/user/file.pdf    – RFC-8089 URI (common with %U or Caja/Nautilus)
      file://localhost/home/user/…  – URI with explicit localhost authority

    QUrl handles all variants correctly.
    """
    raw = raw.strip()
    if raw.startswith(('file://', 'file:')):
        url = QUrl(raw)
        if url.isLocalFile():
            return url.toLocalFile()
    return raw


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

        # On some Alt Linux configurations the system icon theme has white
        # icons that become invisible against light backgrounds in Qt dialogs
        # (e.g. navigation arrows in QFileDialog).  Force a known good theme
        # with proper contrast, falling back to 'hicolor' if not installed.
        from PySide6.QtGui import QIcon
        _theme = QIcon.themeName()
        if not _theme or _theme in ('', 'hicolor'):
            # Prefer Adwaita (ships with most ALT desktops)
            for _candidate in ('Adwaita', 'breeze', 'gnome', 'oxygen'):
                QIcon.setThemeName(_candidate)
                if QIcon.hasThemeIcon('document-open'):
                    break
            else:
                QIcon.setThemeName('hicolor')

    # Set application properties
    # мб не устанавливать applicationDisplayName на альте так как DE склеивает их
    # в тайтле окна, делая некрасиво типа "Редактор PDF Альт — file.pdf — Редактор PDF Альт"?
    app.setApplicationName("Редактор PDF Альт")
    app.setApplicationVersion("0.8.85")
    # app.setApplicationDisplayName("Редактор PDF Альт")
    app.setOrganizationName("SngPdfTools")
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
        # ── Capture argv NOW, before QApplication(sys.argv) potentially
        # modifies the list in-place (PySide6 strips Qt-recognised flags).
        launch_args = sys.argv[:]

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

        # ── Open file passed by the desktop environment / CLI ──────────────
        # We defer with singleShot(0) so the window is fully laid out (all
        # resize/show events processed) before page rendering starts.
        if len(launch_args) > 1:
            file_path = _resolve_file_arg(launch_args[1])
            print(f"[main] File argument: {launch_args[1]!r}  →  resolved: {file_path!r}")
            if os.path.exists(file_path) and file_path.lower().endswith('.pdf'):
                QTimer.singleShot(0, lambda: window.load_document(file_path))
            else:
                print(f"[main] Skipping: path does not exist or is not a PDF: {file_path!r}")

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
