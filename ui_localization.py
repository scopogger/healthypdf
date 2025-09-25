from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QKeySequence


def translate_ui(self, main_window, language):
    """Translate UI elements based on language"""

    if language == 'en' or language == 'en-US':
        # Window title
        main_window.setWindowTitle(QCoreApplication.translate("MainWindow", "PDF Editor", None))

        # File menu and actions
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", "&File", None))
        self.actionOpen.setText(QCoreApplication.translate("MainWindow", "&Open...", None))
        self.actionSave.setText(QCoreApplication.translate("MainWindow", "&Save", None))
        self.actionSaveAs.setText(QCoreApplication.translate("MainWindow", "Save &As...", None))
        self.actionClosePdf.setText(QCoreApplication.translate("MainWindow", "&Close", None))
        self.actionPrint.setText(QCoreApplication.translate("MainWindow", "&Print...", None))
        self.actionEmail.setText(QCoreApplication.translate("MainWindow", "Send by &Email...", None))
        self.actionCompress.setText(QCoreApplication.translate("MainWindow", "&Compress...", None))
        self.actionAboutPdf.setText(QCoreApplication.translate("MainWindow", "Document &Properties...", None))
        self.actionQuit.setText(QCoreApplication.translate("MainWindow", "&Quit", None))
        self.actionSave_Page_As_Image.setText(QCoreApplication.translate("MainWindow", "Save Page as &Image...", None))
        self.actionPasswordDoc.setText(QCoreApplication.translate("MainWindow", "Set Pass&word...", None))
        self.actionEnumeratePages.setText(QCoreApplication.translate("MainWindow", "&Enumerate Pages...", None))

        # View menu and actions
        self.menuView.setTitle(QCoreApplication.translate("MainWindow", "&View", None))
        self.actionToggle_Panel.setText(QCoreApplication.translate("MainWindow", "Toggle &Sidepanel", None))
        self.actionZoom_In.setText(QCoreApplication.translate("MainWindow", "Zoom &In", None))
        self.actionZoom_Out.setText(QCoreApplication.translate("MainWindow", "Zoom &Out", None))
        self.actionFitToWidth.setText(QCoreApplication.translate("MainWindow", "Fit to &Width", None))
        self.actionFitToHeight.setText(QCoreApplication.translate("MainWindow", "Fit to &Height", None))
        self.actionRotateViewClockwise.setText(QCoreApplication.translate("MainWindow", "Rotate View &Clockwise", None))
        self.actionRotateViewCounterclockwise.setText(
            QCoreApplication.translate("MainWindow", "Rotate View &Counterclockwise", None))

        # View submenus
        self.menuRotation.setTitle(QCoreApplication.translate("MainWindow", "&Rotation", None))
        self.menuNavigation.setTitle(QCoreApplication.translate("MainWindow", "&Navigation", None))
        self.menuZoom.setTitle(QCoreApplication.translate("MainWindow", "&Zoom", None))

        # Navigation actions
        self.actionPrevious_Page.setText(QCoreApplication.translate("MainWindow", "&Previous Page", None))
        self.actionNext_Page.setText(QCoreApplication.translate("MainWindow", "&Next Page", None))
        self.actionJumpToFirstPage.setText(QCoreApplication.translate("MainWindow", "&First Page", None))
        self.actionJumpToLastPage.setText(QCoreApplication.translate("MainWindow", "&Last Page", None))

        # Edit menu and actions
        self.menuEdit.setTitle(QCoreApplication.translate("MainWindow", "&Edit", None))
        self.actionDeletePage.setText(QCoreApplication.translate("MainWindow", "&Delete Current Page", None))
        self.actionDeleteSpecificPages.setText(
            QCoreApplication.translate("MainWindow", "Delete &Specific Pages...", None))
        self.actionMovePageUp.setText(QCoreApplication.translate("MainWindow", "Move Page &Up", None))
        self.actionMovePageDown.setText(QCoreApplication.translate("MainWindow", "Move Page &Down", None))
        self.actionRotateCurrentPageClockwise.setText(
            QCoreApplication.translate("MainWindow", "Rotate Page Cloc&kwise", None))
        self.actionRotateCurrentPageCounterclockwise.setText(
            QCoreApplication.translate("MainWindow", "Rotate Page Counter&clockwise", None))
        self.actionRotateSpecificPages.setText(
            QCoreApplication.translate("MainWindow", "&Rotate Specific Pages...", None))
        self.actionAddFile.setText(QCoreApplication.translate("MainWindow", "&Add File...", None))
        self.actionDraw.setText(QCoreApplication.translate("MainWindow", "D&raw/Annotate", None))

        # Help menu and actions
        self.menuHelp.setTitle(QCoreApplication.translate("MainWindow", "&Help", None))
        self.actionAbout.setText(QCoreApplication.translate("MainWindow", "&About PDF Editor", None))

        # Tab buttons
        self.bookmarksButton.setText(QCoreApplication.translate("MainWindow", "Bookmarks", None))
        self.pagesButton.setText(QCoreApplication.translate("MainWindow", "Pages", None))

        # Page input placeholder
        self.m_pageInput.setPlaceholderText(QCoreApplication.translate("MainWindow", "Page", None))
        self.m_pageLabel.setText(QCoreApplication.translate("MainWindow", "of 0", None))

    elif language == 'ru' or language == 'ru-RU':
        # Window title
        main_window.setWindowTitle(QCoreApplication.translate("MainWindow", "PDF Редактор", None))

        # File menu and actions
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", "&Файл", None))
        self.actionOpen.setText(QCoreApplication.translate("MainWindow", "&Открыть...", None))
        self.actionSave.setText(QCoreApplication.translate("MainWindow", "&Сохранить", None))
        self.actionSaveAs.setText(QCoreApplication.translate("MainWindow", "Сохранить &как...", None))
        self.actionClosePdf.setText(QCoreApplication.translate("MainWindow", "&Закрыть", None))
        self.actionPrint.setText(QCoreApplication.translate("MainWindow", "&Печать...", None))
        self.actionEmail.setText(QCoreApplication.translate("MainWindow", "Отправить по &почте...", None))
        self.actionCompress.setText(QCoreApplication.translate("MainWindow", "&Сжать...", None))
        self.actionAboutPdf.setText(QCoreApplication.translate("MainWindow", "&Свойства документа...", None))
        self.actionQuit.setText(QCoreApplication.translate("MainWindow", "&Выход", None))
        self.actionSave_Page_As_Image.setText(
            QCoreApplication.translate("MainWindow", "Сохранить страницу как &изображение...", None))
        self.actionPasswordDoc.setText(QCoreApplication.translate("MainWindow", "Пароль...", None))
        self.actionEnumeratePages.setText(QCoreApplication.translate("MainWindow", "&Нумерация страниц...", None))

        # View menu and actions
        self.menuView.setTitle(QCoreApplication.translate("MainWindow", "&Вид", None))
        self.actionToggle_Panel.setText(QCoreApplication.translate("MainWindow", "Переключить &боковую панель", None))
        self.actionZoom_In.setText(QCoreApplication.translate("MainWindow", "&Увеличить", None))
        self.actionZoom_Out.setText(QCoreApplication.translate("MainWindow", "&Уменьшить", None))
        self.actionFitToWidth.setText(QCoreApplication.translate("MainWindow", "По &ширине", None))
        self.actionFitToHeight.setText(QCoreApplication.translate("MainWindow", "По &высоте", None))
        self.actionRotateViewClockwise.setText(
            QCoreApplication.translate("MainWindow", "Повернуть вид по &часовой", None))
        self.actionRotateViewCounterclockwise.setText(
            QCoreApplication.translate("MainWindow", "Повернуть вид &против часовой", None))

        # View submenus
        self.menuRotation.setTitle(QCoreApplication.translate("MainWindow", "&Поворот", None))
        self.menuNavigation.setTitle(QCoreApplication.translate("MainWindow", "&Навигация", None))
        self.menuZoom.setTitle(QCoreApplication.translate("MainWindow", "&Масштаб", None))

        # Navigation actions
        self.actionPrevious_Page.setText(QCoreApplication.translate("MainWindow", "&Предыдущая страница", None))
        self.actionNext_Page.setText(QCoreApplication.translate("MainWindow", "&Следующая страница", None))
        self.actionJumpToFirstPage.setText(QCoreApplication.translate("MainWindow", "&Первая страница", None))
        self.actionJumpToLastPage.setText(QCoreApplication.translate("MainWindow", "&Последняя страница", None))

        # Edit menu and actions
        self.menuEdit.setTitle(QCoreApplication.translate("MainWindow", "&Правка", None))
        self.actionDeletePage.setText(QCoreApplication.translate("MainWindow", "&Удалить текущую страницу", None))
        self.actionDeleteSpecificPages.setText(
            QCoreApplication.translate("MainWindow", "Удалить &определенные страницы...", None))
        self.actionMovePageUp.setText(QCoreApplication.translate("MainWindow", "Переместить страницу &вверх", None))
        self.actionMovePageDown.setText(QCoreApplication.translate("MainWindow", "Переместить страницу в&низ", None))
        self.actionRotateCurrentPageClockwise.setText(
            QCoreApplication.translate("MainWindow", "Повернуть страницу по ча&совой", None))
        self.actionRotateCurrentPageCounterclockwise.setText(
            QCoreApplication.translate("MainWindow", "Повернуть страницу против ча&совой", None))
        self.actionRotateSpecificPages.setText(
            QCoreApplication.translate("MainWindow", "&Повернуть определенные страницы...", None))
        self.actionAddFile.setText(QCoreApplication.translate("MainWindow", "&Добавить файл...", None))
        self.actionDraw.setText(QCoreApplication.translate("MainWindow", "&Рисование/Аннотации", None))

        # Help menu and actions
        self.menuHelp.setTitle(QCoreApplication.translate("MainWindow", "&Справка", None))
        self.actionAbout.setText(QCoreApplication.translate("MainWindow", "&О программе PDF Редактор", None))

        # Tab buttons
        self.bookmarksButton.setText(QCoreApplication.translate("MainWindow", "Закладки", None))
        self.pagesButton.setText(QCoreApplication.translate("MainWindow", "Страницы", None))

        # Page input placeholder
        self.m_pageInput.setPlaceholderText(QCoreApplication.translate("MainWindow", "Страница", None))
        self.m_pageLabel.setText(QCoreApplication.translate("MainWindow", "из 0", None))

    # Add tooltips for better UX
    add_tooltips(self, language)


def add_tooltips(self, language):
    """Add tooltips to UI elements"""

    if language == 'en' or language == 'en-US':
        self.actionOpen.setToolTip("Open a PDF file")
        self.actionSave.setToolTip("Save changes to current document")
        self.actionSaveAs.setToolTip("Save document with a new name")
        self.actionClosePdf.setToolTip("Close current document")
        self.actionPrint.setToolTip("Print document")

        self.actionPrevious_Page.setToolTip("Go to previous page")
        self.actionNext_Page.setToolTip("Go to next page")
        self.actionJumpToFirstPage.setToolTip("Go to first page")
        self.actionJumpToLastPage.setToolTip("Go to last page")

        self.actionZoom_In.setToolTip("Zoom in")
        self.actionZoom_Out.setToolTip("Zoom out")
        self.actionFitToWidth.setToolTip("Fit document to window width")
        self.actionFitToHeight.setToolTip("Fit document to window height")

        self.actionRotateViewClockwise.setToolTip("Rotate view clockwise (temporary)")
        self.actionRotateViewCounterclockwise.setToolTip("Rotate view counterclockwise (temporary)")

        self.actionDeletePage.setToolTip("Delete current page")
        self.actionMovePageUp.setToolTip("Move current page up")
        self.actionMovePageDown.setToolTip("Move current page down")
        self.actionRotateCurrentPageClockwise.setToolTip("Rotate current page clockwise (permanent)")
        self.actionRotateCurrentPageCounterclockwise.setToolTip("Rotate current page counterclockwise (permanent)")

        self.actionToggle_Panel.setToolTip("Show/hide side panel")
        self.actionDraw.setToolTip("Draw annotations on document")

    elif language == 'ru' or language == 'ru-RU':
        self.actionOpen.setToolTip("Открыть PDF файл")
        self.actionSave.setToolTip("Сохранить изменения в текущем документе")
        self.actionSaveAs.setToolTip("Сохранить документ с новым именем")
        self.actionClosePdf.setToolTip("Закрыть текущий документ")
        self.actionPrint.setToolTip("Печать документа")

        self.actionPrevious_Page.setToolTip("Перейти к предыдущей странице")
        self.actionNext_Page.setToolTip("Перейти к следующей странице")
        self.actionJumpToFirstPage.setToolTip("Перейти к первой странице")
        self.actionJumpToLastPage.setToolTip("Перейти к последней странице")

        self.actionZoom_In.setToolTip("Увеличить масштаб")
        self.actionZoom_Out.setToolTip("Уменьшить масштаб")
        self.actionFitToWidth.setToolTip("Подогнать по ширине окна")
        self.actionFitToHeight.setToolTip("Подогнать по высоте окна")

        self.actionRotateViewClockwise.setToolTip("Повернуть вид по часовой стрелке (временно)")
        self.actionRotateViewCounterclockwise.setToolTip("Повернуть вид против часовой стрелки (временно)")

        self.actionDeletePage.setToolTip("Удалить текущую страницу")
        self.actionMovePageUp.setToolTip("Переместить текущую страницу вверх")
        self.actionMovePageDown.setToolTip("Переместить текущую страницу вниз")
        self.actionRotateCurrentPageClockwise.setToolTip("Повернуть текущую страницу по часовой стрелке (постоянно)")
        self.actionRotateCurrentPageCounterclockwise.setToolTip(
            "Повернуть текущую страницу против часовой стрелки (постоянно)")

        self.actionToggle_Panel.setToolTip("Показать/скрыть боковую панель")
        self.actionDraw.setToolTip("Рисовать аннотации на документе")


def shortcuts_ui(self):
    """Set keyboard shortcuts for actions"""

    # File operations
    self.actionOpen.setShortcut(QKeySequence.StandardKey.Open)  # Ctrl+O
    self.actionSave.setShortcut(QKeySequence.StandardKey.Save)  # Ctrl+S
    self.actionSaveAs.setShortcut(QKeySequence.StandardKey.SaveAs)  # Ctrl+Shift+S
    self.actionClosePdf.setShortcut(QKeySequence.StandardKey.Close)  # Ctrl+W
    self.actionPrint.setShortcut(QKeySequence.StandardKey.Print)  # Ctrl+P
    self.actionQuit.setShortcut(QKeySequence.StandardKey.Quit)  # Ctrl+Q

    # Navigation
    self.actionPrevious_Page.setShortcut(QCoreApplication.translate("MainWindow", "PgUp", None))
    self.actionNext_Page.setShortcut(QCoreApplication.translate("MainWindow", "PgDown", None))
    self.actionJumpToFirstPage.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+Home", None))
    self.actionJumpToLastPage.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+End", None))

    # View operations
    self.actionZoom_In.setShortcut(QKeySequence.StandardKey.ZoomIn)  # Ctrl++
    self.actionZoom_Out.setShortcut(QKeySequence.StandardKey.ZoomOut)  # Ctrl+-
    self.actionFitToWidth.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+1", None))
    self.actionFitToHeight.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+2", None))
    self.actionToggle_Panel.setShortcut(QCoreApplication.translate("MainWindow", "F9", None))

    # Rotation shortcuts
    self.actionRotateViewClockwise.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+R", None))
    self.actionRotateViewCounterclockwise.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+Shift+R", None))
    self.actionRotateCurrentPageClockwise.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+Alt+R", None))
    self.actionRotateCurrentPageCounterclockwise.setShortcut(
        QCoreApplication.translate("MainWindow", "Ctrl+Alt+Shift+R", None))

    # Page operations
    self.actionDeletePage.setShortcut(QCoreApplication.translate("MainWindow", "Del", None))
    self.actionMovePageUp.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+Up", None))
    self.actionMovePageDown.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+Down", None))

    # Other shortcuts
    self.actionDraw.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+D", None))
    self.actionAddFile.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+Shift+O", None))
