"""
Complete UI Main Window - Combines all UI components with proper menu structure
"""

from PySide6.QtWidgets import (
    QMainWindow, QMenuBar, QToolBar, QStatusBar, QWidget, QHBoxLayout, 
    QVBoxLayout, QSplitter, QFrame, QLabel, QLineEdit, QPushButton, 
    QSlider, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QIcon

from zoom_selector import ZoomSelector


class UiMainWindow:
    """UI setup for the main window"""

    def setup_ui(self, main_window, language="en"):
        """Setup the complete UI"""
        main_window.setObjectName("MainWindow")
        main_window.resize(1400, 800)

        # Create central widget
        self.centralwidget = QWidget()
        self.centralwidget.setObjectName("centralwidget")
        main_window.setCentralWidget(self.centralwidget)

        # Main layout
        self.main_layout = QHBoxLayout(self.centralwidget)
        self.main_layout.setContentsMargins(4, 4, 4, 4)

        # Create splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("mainSplitter")

        # Create side panel
        self.setup_side_panel()
        
        # Create main content area
        self.setup_main_content()

        # Add to splitter
        self.splitter.addWidget(self.sidePanelContent)
        self.splitter.addWidget(self.mainContent)
        
        # Set initial splitter sizes (side panel smaller)
        self.splitter.setSizes([250, 1150])
        self.splitter.setCollapsible(0, True)  # Side panel can be collapsed
        self.splitter.setCollapsible(1, False)  # Main content cannot be collapsed

        self.main_layout.addWidget(self.splitter)

        # Setup menus, toolbar, and status bar
        self.setup_menu_bar(main_window)
        self.setup_toolbar(main_window)
        self.setup_status_bar(main_window)

        # Set window properties
        main_window.setWindowTitle("PDF Editor")
        main_window.setMinimumSize(800, 600)

        # Apply translations
        self.retranslate_ui(main_window, language)

    def setup_side_panel(self):
        """Setup the side panel with thumbnails"""
        self.sidePanelContent = QWidget()
        self.sidePanelContent.setObjectName("sidePanelContent")
        self.sidePanelContent.setMinimumWidth(150)
        self.sidePanelContent.setMaximumWidth(300)

        # Side panel layout
        side_layout = QVBoxLayout(self.sidePanelContent)
        side_layout.setContentsMargins(4, 4, 4, 4)

        # Thumbnails label
        thumbnails_label = QLabel("Page Thumbnails")
        thumbnails_label.setObjectName("thumbnailsLabel")
        thumbnails_label.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        thumbnails_label.setAlignment(Qt.AlignCenter)
        thumbnails_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 4px;
                font-weight: bold;
            }
        """)
        side_layout.addWidget(thumbnails_label)

        # Placeholder for thumbnail list (will be replaced)
        self.thumbnailList = QLabel("Thumbnails will appear here")
        self.thumbnailList.setObjectName("thumbnailList")
        self.thumbnailList.setAlignment(Qt.AlignCenter)
        self.thumbnailList.setStyleSheet("""
            QLabel {
                border: 1px solid #ddd;
                background-color: #fafafa;
                color: #888;
            }
        """)
        side_layout.addWidget(self.thumbnailList)

        # Thumbnail size controls
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Size:"))
        
        self.thumbnailSizeSlider = QSlider(Qt.Horizontal)
        self.thumbnailSizeSlider.setObjectName("thumbnailSizeSlider")
        self.thumbnailSizeSlider.setRange(50, 200)
        self.thumbnailSizeSlider.setValue(100)
        self.thumbnailSizeSlider.setMaximumWidth(100)
        size_layout.addWidget(self.thumbnailSizeSlider)
        
        size_layout.addStretch()
        side_layout.addLayout(size_layout)

    def setup_main_content(self):
        """Setup the main content area"""
        self.mainContent = QWidget()
        self.mainContent.setObjectName("mainContent")

        # Main content layout
        main_content_layout = QVBoxLayout(self.mainContent)
        main_content_layout.setContentsMargins(0, 0, 0, 0)

        # Placeholder for PDF view (will be replaced)
        self.pdfView = QLabel("PDF content will appear here")
        self.pdfView.setObjectName("pdfView")
        self.pdfView.setAlignment(Qt.AlignCenter)
        self.pdfView.setStyleSheet("""
            QLabel {
                border: 1px solid #ddd;
                background-color: #ffffff;
                color: #888;
                font-size: 18px;
            }
        """)
        main_content_layout.addWidget(self.pdfView)

    def setup_menu_bar(self, main_window):
        """Setup the menu bar with all menus"""
        self.menubar = QMenuBar(main_window)
        self.menubar.setObjectName("menubar")
        main_window.setMenuBar(self.menubar)

        # File Menu
        self.menuFile = self.menubar.addMenu("File")
        self.menuFile.setObjectName("menuFile")

        self.actionOpen = QAction("Open...", main_window)
        self.actionOpen.setObjectName("actionOpen")
        self.actionOpen.setShortcut(QKeySequence.Open)
        self.actionOpen.setStatusTip("Open a PDF file")
        self.menuFile.addAction(self.actionOpen)

        self.actionSave = QAction("Save", main_window)
        self.actionSave.setObjectName("actionSave")
        self.actionSave.setShortcut(QKeySequence.Save)
        self.actionSave.setStatusTip("Save the current document")
        self.actionSave.setEnabled(False)
        self.menuFile.addAction(self.actionSave)

        self.actionSaveAs = QAction("Save As...", main_window)
        self.actionSaveAs.setObjectName("actionSaveAs")
        self.actionSaveAs.setShortcut(QKeySequence.SaveAs)
        self.actionSaveAs.setStatusTip("Save the document with a new name")
        self.actionSaveAs.setEnabled(False)
        self.menuFile.addAction(self.actionSaveAs)

        self.menuFile.addSeparator()

        self.actionClosePdf = QAction("Close", main_window)
        self.actionClosePdf.setObjectName("actionClosePdf")
        self.actionClosePdf.setShortcut(QKeySequence.Close)
        self.actionClosePdf.setStatusTip("Close the current document")
        self.actionClosePdf.setEnabled(False)
        self.menuFile.addAction(self.actionClosePdf)

        self.menuFile.addSeparator()

        self.actionQuit = QAction("Exit", main_window)
        self.actionQuit.setObjectName("actionQuit")
        self.actionQuit.setShortcut(QKeySequence.Quit)
        self.actionQuit.setStatusTip("Exit the application")
        self.menuFile.addAction(self.actionQuit)

        # Edit Menu
        self.menuEdit = self.menubar.addMenu("Edit")
        self.menuEdit.setObjectName("menuEdit")

        self.actionDeletePage = QAction("Delete Current Page", main_window)
        self.actionDeletePage.setObjectName("actionDeletePage")
        self.actionDeletePage.setShortcut("Delete")
        self.actionDeletePage.setStatusTip("Delete the current page")
        self.actionDeletePage.setEnabled(False)
        self.menuEdit.addAction(self.actionDeletePage)

        self.menuEdit.addSeparator()

        self.actionMovePageUp = QAction("Move Page Up", main_window)
        self.actionMovePageUp.setObjectName("actionMovePageUp")
        self.actionMovePageUp.setShortcut("Ctrl+Up")
        self.actionMovePageUp.setStatusTip("Move the current page up")
        self.actionMovePageUp.setEnabled(False)
        self.menuEdit.addAction(self.actionMovePageUp)

        self.actionMovePageDown = QAction("Move Page Down", main_window)
        self.actionMovePageDown.setObjectName("actionMovePageDown")
        self.actionMovePageDown.setShortcut("Ctrl+Down")
        self.actionMovePageDown.setStatusTip("Move the current page down")
        self.actionMovePageDown.setEnabled(False)
        self.menuEdit.addAction(self.actionMovePageDown)

        self.menuEdit.addSeparator()

        self.actionRotateCurrentPageClockwise = QAction("Rotate Page Clockwise", main_window)
        self.actionRotateCurrentPageClockwise.setObjectName("actionRotateCurrentPageClockwise")
        self.actionRotateCurrentPageClockwise.setShortcut("Ctrl+R")
        self.actionRotateCurrentPageClockwise.setStatusTip("Rotate the current page clockwise")
        self.actionRotateCurrentPageClockwise.setEnabled(False)
        self.menuEdit.addAction(self.actionRotateCurrentPageClockwise)

        self.actionRotateCurrentPageCounterclockwise = QAction("Rotate Page Counterclockwise", main_window)
        self.actionRotateCurrentPageCounterclockwise.setObjectName("actionRotateCurrentPageCounterclockwise")
        self.actionRotateCurrentPageCounterclockwise.setShortcut("Ctrl+Shift+R")
        self.actionRotateCurrentPageCounterclockwise.setStatusTip("Rotate the current page counterclockwise")
        self.actionRotateCurrentPageCounterclockwise.setEnabled(False)
        self.menuEdit.addAction(self.actionRotateCurrentPageCounterclockwise)

        # View Menu
        self.menuView = self.menubar.addMenu("View")
        self.menuView.setObjectName("menuView")

        self.actionZoom_In = QAction("Zoom In", main_window)
        self.actionZoom_In.setObjectName("actionZoom_In")
        self.actionZoom_In.setShortcut("Ctrl++")
        self.actionZoom_In.setStatusTip("Zoom in")
        self.actionZoom_In.setEnabled(False)
        self.menuView.addAction(self.actionZoom_In)

        self.actionZoom_Out = QAction("Zoom Out", main_window)
        self.actionZoom_Out.setObjectName("actionZoom_Out")
        self.actionZoom_Out.setShortcut("Ctrl+-")
        self.actionZoom_Out.setStatusTip("Zoom out")
        self.actionZoom_Out.setEnabled(False)
        self.menuView.addAction(self.actionZoom_Out)

        self.menuView.addSeparator()

        self.actionFitToWidth = QAction("Fit to Width", main_window)
        self.actionFitToWidth.setObjectName("actionFitToWidth")
        self.actionFitToWidth.setShortcut("Ctrl+1")
        self.actionFitToWidth.setStatusTip("Fit document to window width")
        self.actionFitToWidth.setEnabled(False)
        self.menuView.addAction(self.actionFitToWidth)

        self.actionFitToHeight = QAction("Fit to Height", main_window)
        self.actionFitToHeight.setObjectName("actionFitToHeight")
        self.actionFitToHeight.setShortcut("Ctrl+2")
        self.actionFitToHeight.setStatusTip("Fit document to window height")
        self.actionFitToHeight.setEnabled(False)
        self.menuView.addAction(self.actionFitToHeight)

        self.menuView.addSeparator()

        self.actionRotateViewClockwise = QAction("Rotate View Clockwise", main_window)
        self.actionRotateViewClockwise.setObjectName("actionRotateViewClockwise")
        self.actionRotateViewClockwise.setShortcut("Ctrl+Shift+Right")
        self.actionRotateViewClockwise.setStatusTip("Rotate the view clockwise")
        self.actionRotateViewClockwise.setEnabled(False)
        self.menuView.addAction(self.actionRotateViewClockwise)

        self.actionRotateViewCounterclockwise = QAction("Rotate View Counterclockwise", main_window)
        self.actionRotateViewCounterclockwise.setObjectName("actionRotateViewCounterclockwise")
        self.actionRotateViewCounterclockwise.setShortcut("Ctrl+Shift+Left")
        self.actionRotateViewCounterclockwise.setStatusTip("Rotate the view counterclockwise")
        self.actionRotateViewCounterclockwise.setEnabled(False)
        self.menuView.addAction(self.actionRotateViewCounterclockwise)

        self.menuView.addSeparator()

        self.actionToggle_Panel = QAction("Toggle Side Panel", main_window)
        self.actionToggle_Panel.setObjectName("actionToggle_Panel")
        self.actionToggle_Panel.setShortcut("F9")
        self.actionToggle_Panel.setStatusTip("Toggle side panel visibility")
        self.actionToggle_Panel.setCheckable(True)
        self.actionToggle_Panel.setChecked(True)
        self.menuView.addAction(self.actionToggle_Panel)

        # Help Menu
        self.menuHelp = self.menubar.addMenu("Help")
        self.menuHelp.setObjectName("menuHelp")

        self.actionAbout = QAction("About", main_window)
        self.actionAbout.setObjectName("actionAbout")
        self.actionAbout.setStatusTip("About this application")
        self.menuHelp.addAction(self.actionAbout)

    def setup_toolbar(self, main_window):
        """Setup the toolbar"""
        self.toolBar = QToolBar("Main Toolbar")
        self.toolBar.setObjectName("mainToolBar")
        self.toolBar.setMovable(False)
        main_window.addToolBar(Qt.TopToolBarArea, self.toolBar)

        # File actions
        self.toolBar.addAction(self.actionOpen)
        self.toolBar.addAction(self.actionSave)
        self.toolBar.addAction(self.actionSaveAs)
        self.toolBar.addSeparator()

        # Navigation controls
        self.actionPrevious_Page = QAction("Previous Page", main_window)
        self.actionPrevious_Page.setObjectName("actionPrevious_Page")
        self.actionPrevious_Page.setShortcut("Left")
        self.actionPrevious_Page.setStatusTip("Go to previous page")
        self.actionPrevious_Page.setEnabled(False)
        self.toolBar.addAction(self.actionPrevious_Page)

        self.actionNext_Page = QAction("Next Page", main_window)
        self.actionNext_Page.setObjectName("actionNext_Page")
        self.actionNext_Page.setShortcut("Right")
        self.actionNext_Page.setStatusTip("Go to next page")
        self.actionNext_Page.setEnabled(False)
        self.toolBar.addAction(self.actionNext_Page)

        self.toolBar.addSeparator()

        # Page navigation
        self.actionJumpToFirstPage = QAction("First Page", main_window)
        self.actionJumpToFirstPage.setObjectName("actionJumpToFirstPage")
        self.actionJumpToFirstPage.setShortcut("Home")
        self.actionJumpToFirstPage.setStatusTip("Go to first page")
        self.actionJumpToFirstPage.setEnabled(False)
        self.toolBar.addAction(self.actionJumpToFirstPage)

        # Page input
        self.m_pageInput = QLineEdit()
        self.m_pageInput.setObjectName("pageInput")
        self.m_pageInput.setFixedWidth(60)
        self.m_pageInput.setPlaceholderText("Page")
        self.m_pageInput.setAlignment(Qt.AlignCenter)
        self.toolBar.addWidget(self.m_pageInput)

        self.m_pageLabel = QLabel("of 0")
        self.m_pageLabel.setObjectName("pageLabel")
        self.toolBar.addWidget(self.m_pageLabel)

        self.actionJumpToLastPage = QAction("Last Page", main_window)
        self.actionJumpToLastPage.setObjectName("actionJumpToLastPage")
        self.actionJumpToLastPage.setShortcut("End")
        self.actionJumpToLastPage.setStatusTip("Go to last page")
        self.actionJumpToLastPage.setEnabled(False)
        self.toolBar.addAction(self.actionJumpToLastPage)

        self.toolBar.addSeparator()

        # Zoom controls
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setObjectName("zoomOutBtn")
        zoom_out_btn.setFixedSize(30, 30)
        zoom_out_btn.setStatusTip("Zoom out")
        self.toolBar.addWidget(zoom_out_btn)

        self.m_zoomSelector = ZoomSelector()
        self.m_zoomSelector.setObjectName("zoomSelector")
        self.toolBar.addWidget(self.m_zoomSelector)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setObjectName("zoomInBtn")
        zoom_in_btn.setFixedSize(30, 30)
        zoom_in_btn.setStatusTip("Zoom in")
        self.toolBar.addWidget(zoom_in_btn)

        # Connect zoom buttons to actions
        zoom_out_btn.clicked.connect(lambda: self.actionZoom_Out.trigger())
        zoom_in_btn.clicked.connect(lambda: self.actionZoom_In.trigger())

        self.toolBar.addSeparator()

        # Page manipulation
        self.toolBar.addAction(self.actionDeletePage)
        self.toolBar.addAction(self.actionMovePageUp)
        self.toolBar.addAction(self.actionMovePageDown)
        self.toolBar.addAction(self.actionRotateCurrentPageClockwise)
        self.toolBar.addAction(self.actionRotateCurrentPageCounterclockwise)

        # Add spacer to push remaining items to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolBar.addWidget(spacer)

        # View controls
        self.toolBar.addAction(self.actionFitToWidth)
        self.toolBar.addAction(self.actionFitToHeight)

    def setup_status_bar(self, main_window):
        """Setup the status bar"""
        self.statusbar = QStatusBar(main_window)
        self.statusbar.setObjectName("statusbar")
        main_window.setStatusBar(self.statusbar)

        # Add permanent widgets to status bar
        self.statusLabel = QLabel("Ready")
        self.statusLabel.setObjectName("statusLabel")
        self.statusbar.addWidget(self.statusLabel)

        # Add stretch
        self.statusbar.addPermanentWidget(QLabel(""))

    def retranslate_ui(self, main_window, language="en"):
        """Set UI text based on language"""
        # This method can be extended for internationalization
        # For now, we keep English text as set above
        pass