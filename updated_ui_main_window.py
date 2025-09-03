from PySide6.QtCore import (QMetaObject, QRect, QSize, Qt, QTimer, QPointF)
from PySide6.QtGui import (QAction, QIcon, QPainter, QKeySequence)
from PySide6.QtWidgets import (QMenu, QMenuBar, QSizePolicy, QSplitter, QStatusBar,
                               QToolBar, QVBoxLayout, QWidget, QListWidget, QHBoxLayout,
                               QLineEdit, QLabel, QFrame, QTreeView, QToolButton,
                               QStyleOptionToolButton, QStyle, QScrollArea)
import sys
import os
from thumbnail_widget import ThumbnailWidget
from pdf_viewer import PDFViewer

# Try to import resources, but don't fail if it's not available
try:
    import resources
except ImportError:
    print("Warning: resources module not found. Icons may not display correctly.")


class ZoomSelector(QWidget):
    """Simple zoom selector widget"""
    from PySide6.QtCore import Signal

    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_input = None
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.zoom_input = QLineEdit()
        self.zoom_input.setMaximumWidth(80)
        self.zoom_input.setText("100%")
        self.zoom_input.returnPressed.connect(self.on_zoom_input)
        layout.addWidget(self.zoom_input)

    def on_zoom_input(self):
        try:
            text = self.zoom_input.text().replace('%', '')
            zoom = float(text) / 100.0
            self.zoom_changed.emit(zoom)
        except ValueError:
            pass

    def set_zoom_value(self, zoom):
        self.zoom_input.setText(f"{int(zoom * 100)}%")


class UiMainWindow(object):
    def __init__(self):
        # Initialize all UI components to None
        self.thumbnailWidget = None
        self.menuEdit = None
        self.m_pageLabel = None
        self.menuHelp = None
        self.menuView = None
        self.menuFile = None
        self.menuOpenRecent = None  # New submenu for recent files
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
        self.thumbnailList = None
        self.pagesTabLayout = None
        self.verticalLayout = None
        self.verticalLayout_2 = None
        self.verticalLayout_3 = None
        self.pdfView = None  # This will be the actual PDFViewer now
        self.pagesTab = None
        self.bookmarkView = None
        self.bookmarkTab = None
        self.tabWidget = None
        self.widget = None
        self.centralWidget = None
        self.splitter = None
        self.sidePanelContent = None
        self.tabButtonsWidget = None

    def setup_ui(self, main_window, localization_language):
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

        self.setup_action_icons("light_theme_v2")

        main_window.resize(1400, 800)

        # Set initially open tab to "Pages"
        self.pagesButton.setChecked(True)
        self.pagesTab.show()
        self.sidePanelContent.show()

        self.splitter.setChildrenCollapsible(False)

        # Set initial sidebar width constraints
        self.setup_initial_sidebar_size()

        # Import and apply localization
        try:
            import ui_localization
            ui_localization.translate_ui(self, main_window, localization_language)
            ui_localization.shortcuts_ui(self)
        except ImportError:
            print("Warning: ui_localization module not found. Using default text.")

    def setup_layout(self, main_window):
        """Setup main layout with central widget and splitter"""
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
        """Setup the side panel with tabs and proper size constraints"""
        # Create tab buttons widget (vertical stripe)
        self.tabButtonsWidget = QWidget(self.splitter)
        self.tabButtonsLayout = QVBoxLayout(self.tabButtonsWidget)
        self.tabButtonsLayout.setContentsMargins(0, 0, 0, 0)
        self.tabButtonsLayout.setSpacing(0)

        # Create tab buttons
        self.bookmarksButton = VerticalButton("Bookmarks", self.tabButtonsWidget)
        self.bookmarksButton.clicked.connect(self.toggle_bookmark_tab)

        self.pagesButton = VerticalButton("Pages", self.tabButtonsWidget)
        self.pagesButton.clicked.connect(self.toggle_pages_tab)

        # Add buttons to layout
        self.tabButtonsLayout.addWidget(self.bookmarksButton)
        self.tabButtonsLayout.addWidget(self.pagesButton)
        self.tabButtonsLayout.addStretch()

        # Set fixed size for tab buttons widget
        self.tabButtonsWidget.setMinimumWidth(25)
        self.tabButtonsWidget.setMaximumWidth(25)
        self.tabButtonsWidget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # Create side panel content widget
        self.sidePanelContent = QWidget(self.splitter)
        self.sidePanelContentLayout = QVBoxLayout(self.sidePanelContent)
        self.sidePanelContentLayout.setContentsMargins(0, 0, 0, 0)

        # Set size constraints for the side panel content
        self.sidePanelContent.setMinimumWidth(150)
        self.sidePanelContent.setMaximumWidth(300)
        self.sidePanelContent.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Setup tabs
        self.setup_bookmarks_tab()
        self.setup_pages_tab()

        # Add tabs to content layout
        self.sidePanelContentLayout.addWidget(self.bookmarkTab)
        self.sidePanelContentLayout.addWidget(self.pagesTab)
        self.bookmarkTab.hide()
        self.pagesTab.hide()

        # Set stretch factors - these are critical for proper sizing
        self.splitter.setStretchFactor(0, 0)  # Tab buttons don't resize (fixed 25px)
        self.splitter.setStretchFactor(1, 0)  # Sidebar content limited resize (150-300px)
        self.splitter.setStretchFactor(2, 1)  # PDF view gets all remaining space

    def setup_initial_sidebar_size(self):
        """Set up the initial sidebar size to be as narrow as allowed"""
        if hasattr(self, 'splitter') and hasattr(self, 'sidePanelContent'):
            # Set initial sizes: 25px for tab buttons, 150px for content, rest for PDF view
            initial_total_width = 1400  # Default window width
            tab_buttons_width = 25
            sidebar_content_width = 150  # Minimum allowed width
            pdf_view_width = initial_total_width - tab_buttons_width - sidebar_content_width

            # Set the initial sizes
            self.splitter.setSizes([tab_buttons_width, sidebar_content_width, pdf_view_width])

            # Ensure the splitter respects our size constraints
            self.splitter.setCollapsible(0, False)  # Tab buttons can't be collapsed
            self.splitter.setCollapsible(1, False)  # Sidebar can't be collapsed (use toggle instead)
            self.splitter.setCollapsible(2, False)  # PDF view can't be collapsed

    def toggle_bookmark_tab(self):
        """Toggle bookmark tab visibility"""
        if self.bookmarksButton.isChecked():
            self.pagesButton.setChecked(False)
            self.pagesTab.hide()
            self.bookmarkTab.show()
            self.sidePanelContent.show()

            # Restore sidebar size if it was hidden
            if hasattr(self, 'splitter'):
                current_sizes = self.splitter.sizes()
                if current_sizes[1] == 0:  # Sidebar is hidden
                    tab_buttons_width = 25
                    sidebar_content_width = 150
                    remaining_width = sum(current_sizes) - tab_buttons_width - sidebar_content_width
                    self.splitter.setSizes([tab_buttons_width, sidebar_content_width, remaining_width])
        else:
            self.bookmarkTab.hide()
            if not self.pagesButton.isChecked():
                self.sidePanelContent.hide()
                # Collapse sidebar when both tabs are unchecked
                if hasattr(self, 'splitter'):
                    current_sizes = self.splitter.sizes()
                    total_width = sum(current_sizes)
                    self.splitter.setSizes([25, 0, total_width - 25])

    def toggle_pages_tab(self):
        """Toggle pages tab visibility"""
        if self.pagesButton.isChecked():
            self.bookmarksButton.setChecked(False)
            self.bookmarkTab.hide()
            self.pagesTab.show()
            self.sidePanelContent.show()

            # Restore sidebar size if it was hidden
            if hasattr(self, 'splitter'):
                current_sizes = self.splitter.sizes()
                if current_sizes[1] == 0:  # Sidebar is hidden
                    tab_buttons_width = 25
                    sidebar_content_width = 150
                    remaining_width = sum(current_sizes) - tab_buttons_width - sidebar_content_width
                    self.splitter.setSizes([tab_buttons_width, sidebar_content_width, remaining_width])
        else:
            self.pagesTab.hide()
            if not self.bookmarksButton.isChecked():
                self.sidePanelContent.hide()
                # Collapse sidebar when both tabs are unchecked
                if hasattr(self, 'splitter'):
                    current_sizes = self.splitter.sizes()
                    total_width = sum(current_sizes)
                    self.splitter.setSizes([25, 0, total_width - 25])

    def setup_bookmarks_tab(self):
        """Setup bookmarks tab content"""
        self.bookmarkTab = QWidget()
        self.verticalLayout_3 = QVBoxLayout(self.bookmarkTab)
        self.verticalLayout_3.setContentsMargins(2, 2, 2, 2)
        self.verticalLayout_3.setSpacing(0)

        self.bookmarkView = QTreeView(self.bookmarkTab)
        self.bookmarkView.setObjectName("bookmarkView")
        self.bookmarkView.setHeaderHidden(True)
        # Remove fixed width - let the parent container handle sizing
        self.verticalLayout_3.addWidget(self.bookmarkView)

    def setup_pages_tab(self):
        """Setup pages tab content"""
        self.pagesTab = QWidget()
        self.pagesTabLayout = QVBoxLayout(self.pagesTab)
        self.pagesTabLayout.setContentsMargins(0, 0, 0, 0)
        self.pagesTabLayout.setSpacing(0)

        # Mount the custom thumbnail widget (it contains its own slider)
        self.thumbnailWidget = ThumbnailWidget(self.pagesTab)
        self.pagesTabLayout.addWidget(self.thumbnailWidget)

        # Expose inner controls under old names, so other code keeps working
        self.thumbnailList = self.thumbnailWidget
        # No separate thumbnail_size_slider - it's inside thumbnailWidget

    def setup_pdf_view(self):
        """Setup PDF viewer widget"""
        self.pdfView = PDFViewer(self.splitter)
        self.pdfView.setObjectName("pdfView")
        size_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        size_policy.setHorizontalStretch(10)
        self.pdfView.setSizePolicy(size_policy)

    def setup_actions(self, main_window):
        """Initialize all actions"""
        # File actions
        self.actionOpen = QAction(main_window)
        self.actionOpen.setObjectName("actionOpen")

        self.actionSave = QAction(main_window)
        self.actionSave.setObjectName("actionSave")

        self.actionSaveAs = QAction(main_window)
        self.actionSaveAs.setObjectName("actionSaveAs")

        self.actionClosePdf = QAction(main_window)
        self.actionClosePdf.setObjectName("actionClosePdf")

        self.actionPrint = QAction(main_window)
        self.actionPrint.setObjectName("actionPrint")

        self.actionEmail = QAction(main_window)
        self.actionEmail.setObjectName("actionEmail")

        self.actionCompress = QAction(main_window)
        self.actionCompress.setObjectName("actionCompress")

        self.actionAboutPdf = QAction(main_window)
        self.actionAboutPdf.setObjectName("actionAboutPdf")

        self.actionQuit = QAction(main_window)
        self.actionQuit.setObjectName("actionQuit")

        # View actions
        self.actionToggle_Panel = QAction(main_window)
        self.actionToggle_Panel.setObjectName("actionToggle_Panel")

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

        # Navigation actions
        self.actionPrevious_Page = QAction(main_window)
        self.actionPrevious_Page.setObjectName("actionPrevious_Page")

        self.actionNext_Page = QAction(main_window)
        self.actionNext_Page.setObjectName("actionNext_Page")

        self.actionJumpToFirstPage = QAction(main_window)
        self.actionJumpToFirstPage.setObjectName("actionJumpToFirstPage")

        self.actionJumpToLastPage = QAction(main_window)
        self.actionJumpToLastPage.setObjectName("actionJumpToLastPage")

        # Edit actions
        self.actionDeletePage = QAction(main_window)
        self.actionDeletePage.setObjectName("actionDeletePage")

        self.actionDeleteSpecificPages = QAction(main_window)
        self.actionDeleteSpecificPages.setObjectName("actionDeleteSpecificPages")

        self.actionMovePageUp = QAction(main_window)
        self.actionMovePageUp.setObjectName("actionMovePageUp")

        self.actionMovePageDown = QAction(main_window)
        self.actionMovePageDown.setObjectName("actionMovePageDown")

        self.actionRotateCurrentPageClockwise = QAction(main_window)
        self.actionRotateCurrentPageClockwise.setObjectName("actionRotateCurrentPageClockwise")

        self.actionRotateCurrentPageCounterclockwise = QAction(main_window)
        self.actionRotateCurrentPageCounterclockwise.setObjectName("actionRotateCurrentPageCounterclockwise")

        self.actionRotateSpecificPages = QAction(main_window)
        self.actionRotateSpecificPages.setObjectName("actionRotateSpecificPages")

        self.actionAddFile = QAction(main_window)
        self.actionAddFile.setObjectName("actionAddFile")

        # Drawing/annotation actions
        self.actionDraw = QAction(main_window)
        self.actionDraw.setObjectName("actionDraw")
        self.actionDraw.setCheckable(True)

        # Additional actions from old version
        self.actionSave_Page_As_Image = QAction(main_window)
        self.actionSave_Page_As_Image.setObjectName("actionSave_Page_As_Image")

        self.actionPasswordDoc = QAction(main_window)
        self.actionPasswordDoc.setObjectName("actionPasswordDoc")

        self.actionEnumeratePages = QAction(main_window)
        self.actionEnumeratePages.setObjectName("actionEnumeratePages")

        # Help actions
        self.actionAbout = QAction(main_window)
        self.actionAbout.setObjectName("actionAbout")

        # Recent files management actions
        self.actionClearRecentFiles = QAction(main_window)
        self.actionClearRecentFiles.setObjectName("actionClearRecentFiles")
        self.actionClearRecentFiles.setText("Clear recent files")

    def define_menus_ui(self, main_window):
        """Create menu bar and menus"""
        self.menuBar = QMenuBar(main_window)
        self.menuBar.setObjectName("menuBar")
        self.menuBar.setGeometry(QRect(0, 0, 1400, 33))

        # Main menus
        self.menuFile = QMenu(self.menuBar)
        self.menuFile.setObjectName("menuFile")

        self.menuView = QMenu(self.menuBar)
        self.menuView.setObjectName("menuView")

        self.menuEdit = QMenu(self.menuBar)
        self.menuEdit.setObjectName("menuEdit")

        self.menuHelp = QMenu(self.menuBar)
        self.menuHelp.setObjectName("menuHelp")

        main_window.setMenuBar(self.menuBar)

        # Add menus to menu bar
        self.menuBar.addAction(self.menuFile.menuAction())
        self.menuBar.addAction(self.menuView.menuAction())
        self.menuBar.addAction(self.menuEdit.menuAction())
        self.menuBar.addAction(self.menuHelp.menuAction())

        # Create recent files submenu
        self.menuOpenRecent = QMenu("Open recent...", self.menuFile)
        self.menuOpenRecent.setObjectName("menuOpenRecent")

        # Add submenus to View menu
        self.menuRotation = QMenu("Rotation", self.menuView)
        self.menuView.addMenu(self.menuRotation)

        self.menuNavigation = QMenu("Navigation", self.menuView)
        self.menuView.addMenu(self.menuNavigation)

        self.menuZoom = QMenu("Zoom", self.menuView)
        self.menuView.addMenu(self.menuZoom)

    def connect_menus_ui(self):
        """Connect menu actions"""
        # File menu
        self.menuFile.addAction(self.actionOpen)
        self.menuFile.addMenu(self.menuOpenRecent)  # Add recent files submenu after Open
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionSave)
        self.menuFile.addAction(self.actionSaveAs)
        self.menuFile.addAction(self.actionClosePdf)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionPrint)
        self.menuFile.addAction(self.actionEmail)
        self.menuFile.addAction(self.actionCompress)
        self.menuFile.addAction(self.actionSave_Page_As_Image)
        self.menuFile.addAction(self.actionEnumeratePages)
        self.menuFile.addAction(self.actionPasswordDoc)
        self.menuFile.addAction(self.actionAboutPdf)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionQuit)

        # View menu
        self.menuView.addAction(self.actionToggle_Panel)
        self.menuView.addSeparator()

        # View submenus
        self.menuRotation.addAction(self.actionRotateViewClockwise)
        self.menuRotation.addAction(self.actionRotateViewCounterclockwise)

        self.menuNavigation.addAction(self.actionJumpToFirstPage)
        self.menuNavigation.addAction(self.actionJumpToLastPage)
        self.menuNavigation.addAction(self.actionPrevious_Page)
        self.menuNavigation.addAction(self.actionNext_Page)

        self.menuZoom.addAction(self.actionZoom_In)
        self.menuZoom.addAction(self.actionZoom_Out)
        self.menuZoom.addAction(self.actionFitToWidth)
        self.menuZoom.addAction(self.actionFitToHeight)

        # Edit menu
        self.menuEdit.addAction(self.actionAddFile)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionDeletePage)
        self.menuEdit.addAction(self.actionDeleteSpecificPages)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionMovePageUp)
        self.menuEdit.addAction(self.actionMovePageDown)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionRotateCurrentPageClockwise)
        self.menuEdit.addAction(self.actionRotateCurrentPageCounterclockwise)
        self.menuEdit.addAction(self.actionRotateSpecificPages)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionDraw)

        # Help menu
        self.menuHelp.addAction(self.actionAbout)

    def define_toolbar_elements(self, main_window):
        """Create toolbar and its elements"""
        self.mainToolBar = QToolBar(main_window)
        self.mainToolBar.setObjectName("mainToolBar")
        self.mainToolBar.setMovable(False)
        self.mainToolBar.setFloatable(False)
        main_window.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.mainToolBar)

        # Zoom selector
        self.m_zoomSelector = ZoomSelector(main_window)
        self.m_zoomSelector.setMaximumWidth(150)

        # Page input and label
        self.m_pageInput = QLineEdit(main_window)
        self.m_pageLabel = QLabel(main_window)
        page_layout = QHBoxLayout()
        page_layout.addWidget(self.m_pageInput)
        page_layout.addWidget(self.m_pageLabel)
        self.page_widget = QWidget(main_window)
        self.page_widget.setLayout(page_layout)
        self.page_widget.setFixedWidth(120)

        # Set input field size
        font_metrics = self.m_pageInput.fontMetrics()
        character_width = font_metrics.horizontalAdvance("0")
        self.m_pageInput.setFixedWidth(character_width * 6)
        self.m_pageLabel.setFixedWidth(character_width * 8)
        self.m_pageInput.setPlaceholderText("Page")

        # Spacers
        self.spacerLeft = QWidget()
        self.spacerLeft.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.spacerMiddle = QWidget()
        self.spacerMiddle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def connect_toolbar_ui(self):
        """Connect toolbar elements"""
        # Left side - File operations
        self.mainToolBar.addAction(self.actionOpen)
        self.mainToolBar.addAction(self.actionSave)
        self.mainToolBar.addAction(self.actionSaveAs)
        self.mainToolBar.addAction(self.actionPrint)
        self.mainToolBar.addAction(self.actionClosePdf)

        self.mainToolBar.addWidget(self.spacerLeft)

        # Middle - Navigation and view
        self.mainToolBar.addAction(self.actionPrevious_Page)
        self.mainToolBar.addAction(self.actionNext_Page)
        self.mainToolBar.addSeparator()
        self.mainToolBar.addAction(self.actionRotateViewCounterclockwise)
        self.mainToolBar.addAction(self.actionRotateViewClockwise)
        self.mainToolBar.addSeparator()
        self.mainToolBar.addWidget(self.page_widget)
        self.mainToolBar.addSeparator()
        self.mainToolBar.addAction(self.actionZoom_In)
        self.mainToolBar.addAction(self.actionZoom_Out)
        self.mainToolBar.addWidget(self.m_zoomSelector)
        self.mainToolBar.addAction(self.actionFitToWidth)
        self.mainToolBar.addAction(self.actionFitToHeight)

        self.mainToolBar.addWidget(self.spacerMiddle)

        # Right side - Page operations
        self.mainToolBar.addAction(self.actionDeletePage)
        self.mainToolBar.addAction(self.actionMovePageUp)
        self.mainToolBar.addAction(self.actionMovePageDown)
        self.mainToolBar.addSeparator()
        self.mainToolBar.addAction(self.actionRotateCurrentPageCounterclockwise)
        self.mainToolBar.addAction(self.actionRotateCurrentPageClockwise)
        self.mainToolBar.addSeparator()
        self.mainToolBar.addAction(self.actionDraw)

    def setup_action_icons(self, theme):
        """Setup icons for actions"""
        # Set icons for submenus
        try:
            self.menuOpenRecent.setIcon(QIcon(f":/{theme}/open_file.png"))
            self.menuRotation.setIcon(QIcon(f":/{theme}/rotate_temp_clockwise.png"))
            self.menuNavigation.setIcon(QIcon(f":/{theme}/jump_to_first.png"))
            self.menuZoom.setIcon(QIcon(f":/{theme}/zoom_in.png"))
        except:
            pass

        # Icon mapping
        icon_mapping = {
            # File actions
            self.actionOpen: "open_file.png",
            self.actionSave: "save.png",
            self.actionSaveAs: "save_as.png",
            self.actionClosePdf: "close.png",
            self.actionPrint: "print.png",
            self.actionEmail: "email.png",
            self.actionCompress: "compress.png",
            self.actionAboutPdf: "information.png",
            self.actionQuit: "exit.png",
            self.actionSave_Page_As_Image: "image_download.png",
            self.actionPasswordDoc: "password_doc.png",
            self.actionEnumeratePages: "enumerate_pages.png",
            self.actionClearRecentFiles: "delete_pages.png",

            # View actions
            self.actionToggle_Panel: "pages.png",
            self.actionZoom_In: "zoom_in.png",
            self.actionZoom_Out: "zoom_out.png",
            self.actionFitToWidth: "fit_to_width.png",
            self.actionFitToHeight: "fit_to_height.png",
            self.actionRotateViewClockwise: "rotate_temp_clockwise.png",
            self.actionRotateViewCounterclockwise: "rotate_temp_counterclockwise.png",

            # Navigation actions
            self.actionPrevious_Page: "page_up.png",
            self.actionNext_Page: "page_down.png",
            self.actionJumpToFirstPage: "jump_to_first.png",
            self.actionJumpToLastPage: "jump_to_last.png",

            # Edit actions
            self.actionDeletePage: "delete_pages.png",
            self.actionDeleteSpecificPages: "delete_pages.png",
            self.actionMovePageUp: "move_page_up.png",
            self.actionMovePageDown: "move_page_down.png",
            self.actionRotateCurrentPageClockwise: "rotate_pages_clockwise.png",
            self.actionRotateCurrentPageCounterclockwise: "rotate_pages_counterclockwise.png",
            self.actionRotateSpecificPages: "rotate_pages_180_degrees.png",
            self.actionAddFile: "add_file.png",
            self.actionDraw: "drawing.png",

            # Help actions
            self.actionAbout: "help.png",
        }

        # Apply icons
        for action, icon_name in icon_mapping.items():
            try:
                icon_path = f":/{theme}/{icon_name}"
                action.setIcon(QIcon(icon_path))
            except:
                # Fallback to system icons or no icons if resources not available
                pass

    def add_statusbar_ui(self, main_window):
        """Add status bar"""
        self.statusBar = QStatusBar(main_window)
        self.statusBar.setObjectName("statusBar")
        main_window.setStatusBar(self.statusBar)


class VerticalButton(QToolButton):
    """Custom vertical button for tab switching"""

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

        # Calculate text positioning for vertical text
        font_metrics = painter.fontMetrics()
        text_width = font_metrics.horizontalAdvance(self.text())
        text_height = font_metrics.height()

        center_x = self.width() / 2
        center_y = self.height() / 2

        painter.translate(center_x, center_y)
        painter.rotate(-90)
        painter.translate(-center_y, -center_x)

        text_x = (self.height() - text_width) / 2
        text_y = (self.width() - text_height) / 2 + font_metrics.ascent()

        painter.drawText(QPointF(text_x, text_y), self.text())
        painter.restore()
