import os
import sys
from argparse import ArgumentParser, RawTextHelpFormatter

from PySide6.QtCore import QLocale, Qt, QTranslator, QLibraryInfo
from PySide6.QtGui import QIcon, QPalette, QGuiApplication, QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyle, QProxyStyle

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
        # app.setStyle("Fusion")
        app.setStyle(DialogIconStyle("Fusion"))

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


class DialogIconStyle(QProxyStyle):
    """
    Replaces dialog button icons that render as white (invisible on light
    backgrounds on some Alt Linux icon themes) with programmatically drawn
    dark symbols that always have good contrast.
    """

    _ICON_SIZE = 16

    def standardIcon(self, standard_pixmap, option=None, widget=None):
        icon = self._make_icon(standard_pixmap)
        if icon is not None:
            return icon
        return super().standardIcon(standard_pixmap, option, widget)

    def _make_icon(self, sp) -> QIcon | None:
        SP = QStyle.StandardPixmap
        s = self._ICON_SIZE
        dispatch = {
            SP.SP_DialogOkButton:      self._draw_checkmark,
            SP.SP_DialogCancelButton:  self._draw_cross,
            SP.SP_DialogCloseButton:   self._draw_cross,
            SP.SP_DialogYesButton:     self._draw_checkmark,
            SP.SP_DialogNoButton:      self._draw_cross,
            SP.SP_DialogApplyButton:   self._draw_checkmark,
            SP.SP_DialogSaveButton:    self._draw_floppy,
            SP.SP_DialogOpenButton:    self._draw_folder,
            SP.SP_DialogResetButton:   self._draw_reset,
            SP.SP_DialogDiscardButton: self._draw_cross,
            SP.SP_DialogHelpButton:    self._draw_question,
            SP.SP_MessageBoxCritical:  self._draw_error,
            SP.SP_MessageBoxWarning:   self._draw_warning,
            SP.SP_MessageBoxInformation: self._draw_info,
            SP.SP_MessageBoxQuestion:  self._draw_question_msg,
        }
        fn = dispatch.get(sp)
        if fn is None:
            return None
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        fn(p, s)
        p.end()
        return QIcon(pm)

    # ── Symbol drawers ────────────────────────────────────────────────
    @staticmethod
    def _draw_checkmark(p: QPainter, s: int):
        from PySide6.QtGui import QPen
        p.setPen(QPen(QColor("#2e7d32"), max(2, s // 7), Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        m = s * 0.15
        p.drawLine(int(m), int(s * 0.55),
                   int(s * 0.42), int(s - m))
        p.drawLine(int(s * 0.42), int(s - m),
                   int(s - m), int(m))

    @staticmethod
    def _draw_cross(p: QPainter, s: int):
        from PySide6.QtGui import QPen
        p.setPen(QPen(QColor("#c62828"), max(2, s // 7), Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        m = int(s * 0.2)
        p.drawLine(m, m, s - m, s - m)
        p.drawLine(s - m, m, m, s - m)

    @staticmethod
    def _draw_floppy(p: QPainter, s: int):
        from PySide6.QtGui import QPen
        color = QColor("#1565c0")
        p.setPen(QPen(color, 1))
        p.setBrush(color)
        m = int(s * 0.1)
        p.drawRoundedRect(m, m, s - 2 * m, s - 2 * m, 2, 2)
        p.setBrush(QColor("#ffffff"))
        p.drawRect(int(s * 0.3), m, int(s * 0.4), int(s * 0.3))
        p.setBrush(QColor("#bbdefb"))
        p.drawRect(int(s * 0.2), int(s * 0.55),
                   int(s * 0.6), int(s * 0.35))

    @staticmethod
    def _draw_folder(p: QPainter, s: int):
        from PySide6.QtGui import QPen
        color = QColor("#f57f17")
        p.setPen(QPen(color, 1))
        p.setBrush(color)
        m = int(s * 0.1)
        p.drawRect(m, int(s * 0.35), s - 2 * m, int(s * 0.55))
        p.setBrush(QColor("#ffca28"))
        p.drawRect(m, int(s * 0.25), int(s * 0.45), int(s * 0.15))

    @staticmethod
    def _draw_reset(p: QPainter, s: int):
        from PySide6.QtGui import QPen, QPainterPath
        p.setPen(QPen(QColor("#6a1b9a"), max(2, s // 7), Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        from PySide6.QtCore import QRectF
        m = int(s * 0.2)
        p.drawArc(QRectF(m, m, s - 2*m, s - 2*m).toRect(), 30 * 16, 300 * 16)
        # arrowhead
        p.drawLine(s - m, int(s * 0.25), s - m, int(s * 0.5))
        p.drawLine(s - m, int(s * 0.25), int(s * 0.7), int(s * 0.25))

    @staticmethod
    def _draw_question(p: QPainter, s: int):
        from PySide6.QtGui import QPen
        p.setPen(QPen(QColor("#1565c0"), max(2, s // 8), Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        from PySide6.QtCore import QRectF
        m = int(s * 0.25)
        p.drawArc(QRectF(m, int(s*0.1), s - 2*m, s*0.5).toRect(), 0, 200 * 16)
        p.drawLine(s // 2, int(s * 0.62), s // 2, int(s * 0.72))
        p.drawPoint(s // 2, int(s * 0.85))

    @staticmethod
    def _draw_error(p: QPainter, s: int):
        from PySide6.QtGui import QPen
        m = int(s * 0.1)
        p.setBrush(QColor("#c62828"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(m, m, s - 2*m, s - 2*m)
        p.setPen(QPen(Qt.white, max(2, s // 7), Qt.SolidLine, Qt.RoundCap))
        mm = int(s * 0.28)
        p.drawLine(mm, mm, s - mm, s - mm)
        p.drawLine(s - mm, mm, mm, s - mm)

    @staticmethod
    def _draw_warning(p: QPainter, s: int):
        from PySide6.QtGui import QPen, QPolygon
        from PySide6.QtCore import QPoint
        pts = QPolygon([
            QPoint(s // 2, int(s * 0.08)),
            QPoint(int(s * 0.94), int(s * 0.92)),
            QPoint(int(s * 0.06), int(s * 0.92)),
        ])
        p.setBrush(QColor("#f9a825"))
        p.setPen(Qt.NoPen)
        p.drawPolygon(pts)
        p.setPen(QPen(QColor("#5d4037"), max(2, s // 8), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(s // 2, int(s * 0.35), s // 2, int(s * 0.62))
        p.drawPoint(s // 2, int(s * 0.78))

    @staticmethod
    def _draw_info(p: QPainter, s: int):
        from PySide6.QtGui import QPen
        m = int(s * 0.1)
        p.setBrush(QColor("#1565c0"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(m, m, s - 2*m, s - 2*m)
        p.setPen(QPen(Qt.white, max(2, s // 7), Qt.SolidLine, Qt.RoundCap))
        cx = s // 2
        p.drawLine(cx, int(s * 0.28), cx, int(s * 0.32))
        p.drawLine(cx, int(s * 0.42), cx, int(s * 0.75))

    @staticmethod
    def _draw_question_msg(p: QPainter, s: int):
        from PySide6.QtGui import QPen
        m = int(s * 0.1)
        p.setBrush(QColor("#6a1b9a"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(m, m, s - 2*m, s - 2*m)
        p.setPen(QPen(Qt.white, max(2, s // 8), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        from PySide6.QtCore import QRectF
        mm = int(s * 0.28)
        p.drawArc(QRectF(mm, int(s*0.18), s - 2*mm, s*0.42).toRect(), 0, 200 * 16)
        p.drawLine(s // 2, int(s * 0.62), s // 2, int(s * 0.70))
        p.drawPoint(s // 2, int(s * 0.82))


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
