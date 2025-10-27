from PySide6.QtCore import (QMetaObject, QRect,
                            QSize, Qt, QTimer, QPointF)
from PySide6.QtGui import (QAction, QIcon, QPainter)
from PySide6.QtWidgets import (QMenu, QMenuBar,
                               QSizePolicy, QSplitter, QStatusBar, QTabWidget,
                               QToolBar, QVBoxLayout, QWidget, QListWidget, QHBoxLayout, QLineEdit,
                               QLabel, QFrame, QSlider, QTreeView, QToolButton, QStyleOptionToolButton, QStyle)

# Import the integrated components
from integrated_pdf_viewer import IntegratedPDFViewer, IntegratedThumbnailWidget, ZoomSelector

try:
    import resources  # icons
except ImportError:
    pass  # Handle case where resources aren't available


class UiMainWindow(object):
    def __init__(self):
        self.menuEdit = None
        self.m_pageLabel = None
        self.menuHelp = None
        self.menuView = None
        self.menuFile = None
        self.menuRotation = None
        self.menuNavigation = None
        self.menuZoom = None
        self.menuBar = None
        self.m_pageInput = None
        self.spacerMiddle = None
        self.page_widget = None
        self.spacerLeft = None
        self.mainToolBar = None
        self.m_zoomSelector = None
        self.statusBar = None
        self.thumbnail_size_slider = None
        self.thumbnailList = None
        self.pagesTabLayout = None
        self.verticalLayout = None
        self.verticalLayout_2 = None
        self.verticalLayout_3 = None
        self.pdfView = None
        self.pagesTab = None
        self.bookmarkView = None
        self.bookmarkTab = None
        self.tabWidget = None
        self.widget = None
        self.centralWidget = None
        self.splitter = None

    def setup_ui(self, main_window, localization_language="en"):
        if not main_window.objectName():
            main_window.setObjectName("mainWindow")

        self.setup_layout(main_window)
        self.setup_sidepanel_tab_widget()
        self.setup_pdf_view()
        self.add_statusbar_ui(main_window)

        self.setup_actions(main_window)

        self.define_menus_ui(main_window)
        self.connect_menus_ui()
        self.define_toolbar_elements(main_window)
        self.connect_toolbar_ui()

        # Setup icons if resources are available
        try:
            self.setup_action_icons("light_theme_v2")
        except:
            pass  # Skip icons if resources not available

        main_window.resize(1200, 700)

        # Set initially open tab to "Pages"
        self.pagesButton.setChecked(True)
        self.pagesTab.show()
        self.sidePanelContent.show()

        self.splitter.setChildrenCollapsible(False)

        # Import localization
        try:
            import ui_localization
            ui_localization.translate_ui(self, main_window, localization_language)
            ui_localization.shortcuts_ui(self)
        except ImportError:
            pass  # Handle case where localization isn't available

    def setup_layout(self, main_window):
        self.centralWidget = QWidget(main_window)
        self.centralWidget.setObjectName("centralWidget")
        main_window.setCentralWidget(self.centralWidget)

        self.verticalLayout = QVBoxLayout(self.centralWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(0)

        self.splitter = QSplitter(self.centralWidget)
        self.splitter.setObjectName("splitter")
        self.splitter.setOrientation(Qt.Horizontal)
        self.verticalLayout.addWidget(self.splitter)

    def setup_sidepanel_tab_widget(self):
        # Create a widget to hold the tab buttons (vertical stripe)
        self.tabButtonsWidget = QWidget(self.splitter)
        self.tabButtonsLayout = QVBoxLayout(self.tabButtonsWidget)
        self.tabButtonsLayout.setContentsMargins(0, 0, 0, 0)
        self.tabButtonsLayout.setSpacing(0)

        # Create the two tab buttons
        self.bookmarksButton = VerticalButton("Закладки", self.tabButtonsWidget)
        self.bookmarksButton.clicked.connect(self.toggle_bookmark_tab)

        self.pagesButton = VerticalButton("Страницы", self.tabButtonsWidget)
        self.pagesButton.clicked.connect(self.toggle_pages_tab)

        # Add the buttons to the vertical layout
        self.tabButtonsLayout.addWidget(self.bookmarksButton)
        self.tabButtonsLayout.addWidget(self.pagesButton)
        self.tabButtonsLayout.addStretch()

        # Set fixed size for the tabButtonsWidget
        self.tabButtonsWidget.setMinimumWidth(25)
        self.tabButtonsWidget.setMaximumWidth(25)
        self.tabButtonsWidget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # Create a widget to act as the contents panel
        self.sidePanelContent = QWidget(self.splitter)
        self.sidePanelContentLayout = QVBoxLayout(self.sidePanelContent)
        self.sidePanelContentLayout.setContentsMargins(0, 0, 0, 0)

        # Set up the existing bookmark and pages tabs
        self.setup_bookmarks_tab()
        self.setup_pages_tab()

        # Add these to the content layout, initially hidden
        self.sidePanelContentLayout.addWidget(self.bookmarkTab)
        self.sidePanelContentLayout.addWidget(self.pagesTab)
        self.bookmarkTab.hide()
        self.pagesTab.hide()

        # Set the stretch factors in the splitter
        self.splitter.setStretchFactor(0, 0)  # No resizing for the tabButtonsWidget
        self.splitter.setStretchFactor(1, 1)  # sidePanelContent resizable

    def toggle_bookmark_tab(self):
        if self.bookmarksButton.isChecked():
            self.pagesButton.setChecked(False)
            self.pagesTab.hide()
            self.bookmarkTab.show()
            self.sidePanelContent.show()
        else:
            self.sidePanelContent.hide()

    def toggle_pages_tab(self):
        if self.pagesButton.isChecked():
            self.bookmarksButton.setChecked(False)
            self.bookmarkTab.hide()
            self.pagesTab.show()
            self.sidePanelContent.show()
        else:
            self.sidePanelContent.hide()

    def setup_bookmarks_tab(self):
        """Setup bookmarks tab content with QPdfBookmarkModel"""
        self.bookmarkTab = QWidget()
        self.verticalLayout_3 = QVBoxLayout(self.bookmarkTab)
        self.verticalLayout_3.setContentsMargins(2, 2, 2, 2)
        self.verticalLayout_3.setSpacing(0)

        self.bookmarkView = QTreeView(self.bookmarkTab)
        self.bookmarkView.setObjectName("bookmarkView")
        self.bookmarkView.setHeaderHidden(True)

        # Set up the bookmark model (from old code)
        self.bookmark_model = QPdfBookmarkModel(self.bookmarkTab)
        self.bookmark_model.setDocument(self.m_document)
        self.bookmarkView.setModel(self.bookmark_model)

        # REMOVE THIS LINE - we'll connect in main_window.py instead
        # self.bookmarkView.clicked.connect(self.on_bookmark_clicked)

        self.verticalLayout_3.addWidget(self.bookmarkView)

    def setup_pages_tab(self):
        self.pagesTab = QWidget()
        self.pagesTabLayout = QVBoxLayout(self.pagesTab)
        self.pagesTabLayout.setContentsMargins(0, 0, 0, 0)
        self.pagesTabLayout.setSpacing(0)

        # Pages label at the top of the sidepanel
        thumbnail_label = QLabel("Миниатюры страниц")
        thumbnail_label.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        thumbnail_label.setAlignment(Qt.AlignCenter)
        self.pagesTabLayout.addWidget(thumbnail_label)

        # Use the integrated thumbnail widget instead of the old one
        self.thumbnailList = IntegratedThumbnailWidget()
        self.thumbnailList.setStyleSheet("background-color: rgb(190, 190, 190);")
        self.thumbnailList.setMinimumWidth(150)
        self.pagesTabLayout.addWidget(self.thumbnailList)

        # Slider for changing thumbnails' size
        self.thumbnail_size_slider = QSlider(Qt.Horizontal)
        self.thumbnail_size_slider.setRange(0, 19)
        self.thumbnail_size_slider.setValue(1)
        self.thumbnail_size_slider.setTickPosition(QSlider.TicksBelow)
        self.thumbnail_size_slider.setTickInterval(1)
        self.pagesTabLayout.addWidget(self.thumbnail_size_slider)

    def setup_pdf_view(self):
        # Use the integrated PDF viewer instead of QPdfView
        self.pdfView = IntegratedPDFViewer(self.splitter)
        self.pdfView.setObjectName("pdfView")
        size_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        size_policy.setHorizontalStretch(10)
        self.pdfView.setSizePolicy(size_policy)

    def setup_actions(self, main_window):
        self.actionToggle_Panel = QAction(main_window)
        self.actionToggle_Panel.setObjectName("actionToggle_Panel")

        self.actionOpen = QAction(main_window)
        self.actionOpen.setObjectName("actionOpen")

        self.actionClosePdf = QAction(main_window)
        self.actionClosePdf.setObjectName("actionClosePdf")

        self.actionSave = QAction(main_window)
        self.actionSave.setObjectName("actionSave")

        self.actionSaveAs = QAction(main_window)
        self.actionSaveAs.setObjectName("actionSaveAs")

        self.actionSave_Page_As_Image = QAction(main_window)
        self.actionSave_Page_As_Image.setObjectName("actionSave_Page_As_Image")

        self.actionQuit = QAction(main_window)
        self.actionQuit.setObjectName("actionQuit")

        self.actionAbout = QAction(main_window)
        self.actionAbout.setObjectName("actionAbout")

        self.actionAboutPdf = QAction(main_window)
        self.actionAboutPdf.setObjectName("actionAboutPdf")

        self.actionCompress = QAction(main_window)
        self.actionCompress.setObjectName("actionCompress")

        self.actionAddFile = QAction(main_window)
        self.actionAddFile.setObjectName("actionAddFile")

        self.actionPasswordDoc = QAction(main_window)
        self.actionPasswordDoc.setObjectName("actionPasswordDoc")

        self.actionPrint = QAction(main_window)
        self.actionPrint.setObjectName("actionPrint")

        self.actionEmail = QAction(main_window)
        self.actionEmail.setObjectName("actionEmail")

        self.actionEnumeratePages = QAction(main_window)
        self.actionEnumeratePages.setObjectName("actionEnumeratePages")

        self.actionJumpToFirstPage = QAction(main_window)
        self.actionJumpToFirstPage.setObjectName("actionJumpToFirstPage")

        self.actionJumpToLastPage = QAction(main_window)
        self.actionJumpToLastPage.setObjectName("actionJumpToLastPage")

        # Page navigation menu items
        self.actionPrevious_Page = QAction(main_window)
        self.actionPrevious_Page.setObjectName("actionPrevious_Page")

        self.actionNext_Page = QAction(main_window)
        self.actionNext_Page.setObjectName("actionNext_Page")

        self.actionZoom_In = QAction(main_window)
        self.actionZoom_In.setObjectName("actionZoom_In")

        self.actionZoom_Out = QAction(main_window)
        self.actionZoom_Out.setObjectName("actionZoom_Out")

        self.actionFitToWidth = QAction(main_window)
        self.actionFitToWidth.setObjectName("actionFitToWidth")

        self.actionFitToHeight = QAction(main_window)
        self.actionFitToHeight.setObjectName("actionFitToHeight")

        self.actionRotateViewClockwise = QAction(main_window)
        self.actionRotateViewClockwise.setObjectName("actionRotateViewClockwise")

        self.actionRotateViewCounterclockwise = QAction(main_window)
        self.actionRotateViewCounterclockwise.setObjectName("actionRotateViewCounterclockwise")

        self.actionDeletePage = QAction(main_window)
        self.actionDeletePage.setObjectName("actionDeletePage")

        self.actionDeleteSpecificPages = QAction(main_window)
        self.actionDeleteSpecificPages.setObjectName("actionDeleteSpecificPages")

        self.actionMovePageDown = QAction(main_window)
        self.actionMovePageDown.setObjectName("actionMovePageDown")

        self.actionMovePageUp = QAction(main_window)
        self.actionMovePageUp.setObjectName("actionMovePageUp")

        self.actionRotateCurrentPageClockwise = QAction(main_window)
        self.actionRotateCurrentPageClockwise.setObjectName("actionRotateCurrentPageClockwise")

        self.actionRotateCurrentPageCounterclockwise = QAction(main_window)
        self.actionRotateCurrentPageCounterclockwise.setObjectName("actionRotateCurrentPageCounterclockwise")

        self.actionRotateSpecificPages = QAction(main_window)
        self.actionRotateSpecificPages.setObjectName("actionRotateSpecificPages")

        self.actionDraw = QAction(main_window)
        self.actionDraw.setObjectName("actionDraw")

    def define_menus_ui(self, main_window):
        self.menuBar = QMenuBar(main_window)
        self.menuBar.setObjectName("menuBar")
        self.menuBar.setGeometry(QRect(0, 0, 1200, 33))

        self.menuFile = QMenu(self.menuBar)
        self.menuFile.setObjectName("menuFile")

        self.menuView = QMenu(self.menuBar)
        self.menuView.setObjectName("menuView")

        self.menuEdit = QMenu(self.menuBar)
        self.menuEdit.setObjectName("menuEdit")

        self.menuHelp = QMenu(self.menuBar)
        self.menuHelp.setObjectName("menuHelp")

        main_window.setMenuBar(self.menuBar)

        self.menuBar.addAction(self.menuFile.menuAction())
        self.menuBar.addAction(self.menuView.menuAction())
        self.menuBar.addAction(self.menuEdit.menuAction())
        self.menuBar.addAction(self.menuHelp.menuAction())

        # Add submenus to the View menu
        self.menuRotation = QMenu("rotationSubmenu", self.menuView)
        self.menuView.addMenu(self.menuRotation)
        self.menuNavigation = QMenu("navigationSubmenu", self.menuView)
        self.menuView.addMenu(self.menuNavigation)
        self.menuZoom = QMenu("zoomSubmenu", self.menuView)
        self.menuView.addMenu(self.menuZoom)

    def connect_menus_ui(self):
        self.menuFile.addAction(self.actionOpen)
        self.menuFile.addAction(self.actionSave)
        self.menuFile.addAction(self.actionSaveAs)
        self.menuFile.addAction(self.actionClosePdf)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionPrint)
        self.menuFile.addAction(self.actionEmail)
        self.menuFile.addAction(self.actionCompress)
        self.menuFile.addAction(self.actionAboutPdf)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionQuit)

        self.menuView.addSeparator()
        self.menuView.addAction(self.actionToggle_Panel)

        # Add actions to submenus
        self.menuRotation.addAction(self.actionRotateViewClockwise)
        self.menuRotation.addAction(self.actionRotateViewCounterclockwise)
        self.menuNavigation.addAction(self.actionJumpToFirstPage)
        self.menuNavigation.addAction(self.actionJumpToLastPage)
        self.menuNavigation.addAction(self.actionNext_Page)
        self.menuNavigation.addAction(self.actionPrevious_Page)
        self.menuZoom.addAction(self.actionZoom_In)
        self.menuZoom.addAction(self.actionZoom_Out)
        self.menuZoom.addAction(self.actionFitToHeight)
        self.menuZoom.addAction(self.actionFitToWidth)

        self.menuEdit.addAction(self.actionAddFile)
        self.menuEdit.addAction(self.actionDeletePage)
        self.menuEdit.addAction(self.actionDeleteSpecificPages)
        self.menuEdit.addAction(self.actionMovePageDown)
        self.menuEdit.addAction(self.actionMovePageUp)
        self.menuEdit.addAction(self.actionRotateSpecificPages)

        self.menuHelp.addAction(self.actionAbout)

    def define_toolbar_elements(self, main_window):
        self.mainToolBar = QToolBar(main_window)
        self.mainToolBar.setObjectName("mainToolBar")
        self.mainToolBar.setMovable(False)
        self.mainToolBar.setFloatable(False)
        main_window.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.mainToolBar)

        # Use the integrated zoom selector
        self.m_zoomSelector = ZoomSelector(main_window)
        self.m_zoomSelector.set_pdf_viewer(self.pdfView)
        self.m_zoomSelector.setMaximumWidth(150)

        self.m_pageInput = QLineEdit(main_window)
        self.m_pageLabel = QLabel(main_window)
        page_layout = QHBoxLayout()
        page_layout.addWidget(self.m_pageInput)
        page_layout.addWidget(self.m_pageLabel)
        self.page_widget = QWidget(main_window)
        self.page_widget.setLayout(page_layout)
        self.page_widget.setFixedWidth(100)

        font_metrics = self.m_pageInput.fontMetrics()
        character_width = font_metrics.horizontalAdvance("0")
        self.m_pageInput.setFixedWidth(character_width * 6)
        self.m_pageLabel.setFixedWidth(character_width * 6)
        self.m_pageInput.setPlaceholderText("")

        # Adding spacers for toolbar layout
        self.spacerLeft = QWidget()
        self.spacerLeft.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.spacerMiddle = QWidget()
        self.spacerMiddle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def connect_toolbar_ui(self):
        self.mainToolBar.addAction(self.actionOpen)
        self.mainToolBar.addAction(self.actionSave)
        self.mainToolBar.addAction(self.actionSaveAs)
        self.mainToolBar.addAction(self.actionPrint)
        self.mainToolBar.addAction(self.actionClosePdf)

        self.mainToolBar.addWidget(self.spacerLeft)

        self.mainToolBar.addAction(self.actionPrevious_Page)
        self.mainToolBar.addAction(self.actionNext_Page)
        self.mainToolBar.addAction(self.actionRotateViewCounterclockwise)
        self.mainToolBar.addAction(self.actionRotateViewClockwise)
        self.mainToolBar.addWidget(self.page_widget)
        self.mainToolBar.addAction(self.actionZoom_In)
        self.mainToolBar.addAction(self.actionZoom_Out)
        self.mainToolBar.addWidget(self.m_zoomSelector)
        self.mainToolBar.addAction(self.actionFitToHeight)
        self.mainToolBar.addAction(self.actionFitToWidth)

        self.mainToolBar.addWidget(self.spacerMiddle)

        self.mainToolBar.addAction(self.actionDeletePage)
        self.mainToolBar.addAction(self.actionMovePageDown)
        self.mainToolBar.addAction(self.actionMovePageUp)
        self.mainToolBar.addAction(self.actionRotateCurrentPageCounterclockwise)
        self.mainToolBar.addAction(self.actionRotateCurrentPageClockwise)
        self.mainToolBar.addAction(self.actionDraw)

    def setup_action_icons(self, theme):
        if 'resources' not in globals():
            return  # Skip if resources not available

        self.menuRotation.setIcon(QIcon(f":/{theme}/rotate_temp_clockwise.png"))
        self.menuNavigation.setIcon(QIcon(f":/{theme}/jump_to_first.png"))
        self.menuZoom.setIcon(QIcon(f":/{theme}/zoom_in.png"))

        icon_mapping = {
            self.actionToggle_Panel: "pages.png",
            self.actionOpen: "open_file.png",
            self.actionClosePdf: "close.png",
            self.actionSave: "save.png",
            self.actionSaveAs: "save_as.png",
            self.actionSave_Page_As_Image: "image_download.png",
            self.actionQuit: "exit.png",
            self.actionAbout: "help.png",
            self.actionAboutPdf: "information.png",
            self.actionCompress: "compress.png",
            self.actionAddFile: "add_file.png",
            self.actionPasswordDoc: "password_doc.png",
            self.actionPrint: "print.png",
            self.actionEmail: "email.png",
            self.actionEnumeratePages: "enumerate_pages.png",
            self.actionJumpToFirstPage: "jump_to_first.png",
            self.actionJumpToLastPage: "jump_to_last.png",
            self.actionPrevious_Page: "page_up.png",
            self.actionNext_Page: "page_down.png",
            self.actionZoom_In: "zoom_in.png",
            self.actionZoom_Out: "zoom_out.png",
            self.actionFitToWidth: "fit_to_width.png",
            self.actionFitToHeight: "fit_to_height.png",
            self.actionRotateViewCounterclockwise: "rotate_temp_counterclockwise.png",
            self.actionRotateViewClockwise: "rotate_temp_clockwise.png",
            self.actionDeletePage: "delete_pages.png",
            self.actionDeleteSpecificPages: "delete_pages.png",
            self.actionMovePageDown: "move_page_down.png",
            self.actionMovePageUp: "move_page_up.png",
            self.actionRotateCurrentPageCounterclockwise: "rotate_pages_counterclockwise.png",
            self.actionRotateCurrentPageClockwise: "rotate_pages_clockwise.png",
            self.actionRotateSpecificPages: "rotate_pages_180_degrees.png",
            self.actionDraw: "drawing.png",
        }

        for action, icon_name in icon_mapping.items():
            icon_name = f":/{theme}/{icon_name}"
            action.setIcon(QIcon(icon_name))

    def add_statusbar_ui(self, main_window):
        self.statusBar = QStatusBar(main_window)
        self.statusBar.setObjectName("statusBar")
        main_window.setStatusBar(self.statusBar)


class VerticalButton(QToolButton):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)

    def sizeHint(self):
        size = super().sizeHint()
        font_metrics = self.fontMetrics()
        text_width = font_metrics.horizontalAdvance(self.text())
        return QSize(25, text_width + 30)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        option = QStyleOptionToolButton()
        self.initStyleOption(option)

        painter.setClipRect(self.rect())
        self.style().drawPrimitive(QStyle.PE_PanelButtonTool, option, painter, self)

        painter.save()

        # Calculate text rectangle
        font_metrics = painter.fontMetrics()
        text_width = font_metrics.horizontalAdvance(self.text())
        text_height = font_metrics.height()

        # Calculate the rotation point (center of the button)
        center_x = self.width() / 2
        center_y = self.height() / 2

        # Translate to the center, rotate, then translate back
        painter.translate(center_x, center_y)
        painter.rotate(-90)
        painter.translate(-center_y, -center_x)

        # Calculate text position
        text_x = (self.height() - text_width) / 2
        text_y = (self.width() - text_height) / 2 + font_metrics.ascent()

        # Draw the text
        painter.drawText(QPointF(text_x, text_y), self.text())

        painter.restore()
