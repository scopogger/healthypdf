from PySide6.QtCore import (QMetaObject, QRect, QSize, Qt, QTimer, QPointF)
from PySide6.QtGui import (QAction, QIcon, QPainter, QKeySequence, QColor, QPixmap)
from PySide6.QtWidgets import (QMenu, QMenuBar, QSizePolicy, QSplitter, QStatusBar,
                               QToolBar, QVBoxLayout, QWidget, QListWidget, QHBoxLayout,
                               QLineEdit, QLabel, QFrame, QTreeView, QToolButton,
                               QStyleOptionToolButton, QStyle, QScrollArea,
                               QStackedWidget, QPushButton, QButtonGroup, QColorDialog,
                               QSlider, QSpinBox)
from PySide6.QtPdf import QPdfDocument, QPdfBookmarkModel
from PySide6.QtPdfWidgets import QPdfView
import sys
import os
from thumbnail_widget import ThumbnailContainerWidget
from pdf_viewer import PDFViewer

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
        self.zoom_input.setMaximumWidth(50)
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
        self.sidePanelContentLayout = None
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
        self.page_widget = None
        self.spacerRight = None
        self.spacerMiddle = None
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

        # PDF document for bookmarks
        self.m_document = None

    def setup_ui(self, main_window, localization_language):
        if not main_window.objectName():
            main_window.setObjectName("mainWindow")

        # Initialize PDF document for bookmarks
        self.m_document = QPdfDocument(main_window)

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
        # ── Tab-button strip (vertical, fixed 25 px wide) ───────────────
        self.tabButtonsWidget = QWidget(self.splitter)
        self.tabButtonsLayout = QVBoxLayout(self.tabButtonsWidget)
        self.tabButtonsLayout.setContentsMargins(0, 0, 0, 0)
        self.tabButtonsLayout.setSpacing(0)

        self.bookmarksButton = VerticalButton("Bookmarks", self.tabButtonsWidget)
        self.bookmarksButton.clicked.connect(self.toggle_bookmark_tab)

        self.pagesButton = VerticalButton("Pages", self.tabButtonsWidget)
        self.pagesButton.clicked.connect(self.toggle_pages_tab)

        self.tabButtonsLayout.addWidget(self.bookmarksButton)
        self.tabButtonsLayout.addWidget(self.pagesButton)
        self.tabButtonsLayout.addStretch()

        self.tabButtonsWidget.setMinimumWidth(25)
        self.tabButtonsWidget.setMaximumWidth(25)
        self.tabButtonsWidget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # ── Side-panel content area ──────────────────────────────────────
        self.sidePanelContent = QWidget(self.splitter)
        self.sidePanelContentLayout = QVBoxLayout(self.sidePanelContent)
        self.sidePanelContentLayout.setContentsMargins(1, 1, 1, 1)
        self.sidePanelContent.setObjectName("sidePanelContent")
        self.sidePanelContent.setStyleSheet("""
            #sidePanelContent { background-color: #d0d0d0; }
        """)
        self.sidePanelContent.setMinimumWidth(120)
        self.sidePanelContent.setMaximumWidth(350)
        self.sidePanelContent.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # QStackedWidget lets us swap between normal tabs (index 0) and
        # the drawing tools panel (index 1) without touching the splitter.
        self.sidePanelStack = QStackedWidget(self.sidePanelContent)
        self.sidePanelContentLayout.addWidget(self.sidePanelStack)

        # ── Stack page 0: normal bookmarks / pages tabs ──────────────────
        self.normalTabsContainer = QWidget()
        normalTabsLayout = QVBoxLayout(self.normalTabsContainer)
        normalTabsLayout.setContentsMargins(0, 0, 0, 0)
        normalTabsLayout.setSpacing(0)

        self.setup_bookmarks_tab()
        self.setup_pages_tab()

        normalTabsLayout.addWidget(self.bookmarkTab)
        normalTabsLayout.addWidget(self.pagesTab)
        self.bookmarkTab.hide()
        self.pagesTab.hide()

        # ── Stack page 1: drawing tools panel ────────────────────────────
        self.setup_drawing_panel()

        self.sidePanelStack.addWidget(self.normalTabsContainer)  # index 0
        self.sidePanelStack.addWidget(self.drawingPanel)          # index 1
        self.sidePanelStack.setCurrentIndex(0)

        # Stretch factors
        self.splitter.setStretchFactor(0, 0)  # tab-button strip: fixed
        self.splitter.setStretchFactor(1, 0)  # sidepanel content: limited
        self.splitter.setStretchFactor(2, 1)  # PDF view: all remaining space

    #     self.splitter.splitterMoved.connect(self.on_sidebar_resized)
    #
    # def on_sidebar_resized(self):
    #     print("MOVED!!!")

    def setup_initial_sidebar_size(self):
        """Set up the initial sidebar size to be as narrow as allowed"""
        if hasattr(self, 'splitter') and hasattr(self, 'sidePanelContent'):
            # Set initial sizes: 25px for tab buttons, 150px for content, rest for PDF view
            initial_total_width = 1400  # Default window width
            tab_buttons_width = 25
            sidebar_content_width = 120  # Minimum allowed width
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
                    sidebar_content_width = 120
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
                    sidebar_content_width = 120
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
        """Setup bookmarks tab content with QPdfBookmarkModel"""
        self.bookmarkTab = QWidget()
        self.verticalLayout_3 = QVBoxLayout(self.bookmarkTab)
        self.verticalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_3.setSpacing(0)

        self.bookmarkView = QTreeView(self.bookmarkTab)
        self.bookmarkView.setObjectName("bookmarkView")
        self.bookmarkView.setHeaderHidden(True)

        # Set up the bookmark model (from old code)
        self.bookmark_model = QPdfBookmarkModel(self.bookmarkTab)
        self.bookmark_model.setDocument(self.m_document)
        self.bookmarkView.setModel(self.bookmark_model)

        self.verticalLayout_3.addWidget(self.bookmarkView)

    def setup_pages_tab(self):
        """Setup pages tab content"""
        self.pagesTab = QWidget()
        self.pagesTabLayout = QVBoxLayout(self.pagesTab)
        self.pagesTabLayout.setContentsMargins(0, 0, 0, 0)
        self.pagesTabLayout.setSpacing(0)

        self.thumbnailList = ThumbnailContainerWidget(self.pagesTab)
        self.pagesTabLayout.addWidget(self.thumbnailList)

    def setup_drawing_panel(self):
        """Build the drawing-tools panel shown in the sidebar during draw mode."""
        self.drawingPanel = QWidget()
        self.drawingPanel.setObjectName("drawingPanel")
        layout = QVBoxLayout(self.drawingPanel)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(6)

        # Title
        title = QLabel("Рисование")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sep0 = QFrame(); sep0.setFrameShape(QFrame.HLine); sep0.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep0)

        # ── Tool buttons ──────────────────────────────────────────────────
        tools_label = QLabel("Инструмент:")
        tools_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(tools_label)

        _draw_tool_group = QButtonGroup(self.drawingPanel)
        _draw_tool_group.setExclusive(True)

        _btn_style = (
            "QPushButton { padding: 4px; border: 1px solid #bbb; border-radius: 3px; background: #f0f0f0; }"
            "QPushButton:checked { background: #dce8f8; border: 2px solid #0078d7; font-weight: bold; }"
        )

        self.drawBrushBtn = QPushButton(self.drawingPanel)
        self.drawBrushBtn.setCheckable(True)
        self.drawBrushBtn.setChecked(True)
        self.drawBrushBtn.setObjectName("drawBrushBtn")
        self.drawBrushBtn.setIcon(QIcon(":/light_theme_v2/brush.png"))
        self.drawBrushBtn.setIconSize(QSize(22, 22))
        self.drawBrushBtn.setToolTip("Кисть")
        self.drawBrushBtn.setFixedHeight(34)
        self.drawBrushBtn.setStyleSheet(_btn_style)

        self.drawRectBtn = QPushButton(self.drawingPanel)
        self.drawRectBtn.setCheckable(True)
        self.drawRectBtn.setObjectName("drawRectBtn")
        self.drawRectBtn.setIcon(QIcon(":/light_theme_v2/rectangle.png"))
        self.drawRectBtn.setIconSize(QSize(22, 22))
        self.drawRectBtn.setToolTip("Прямоугольник")
        self.drawRectBtn.setFixedHeight(34)
        self.drawRectBtn.setStyleSheet(_btn_style)

        _draw_tool_group.addButton(self.drawBrushBtn)
        _draw_tool_group.addButton(self.drawRectBtn)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(4)
        tools_row.addWidget(self.drawBrushBtn)
        tools_row.addWidget(self.drawRectBtn)
        tools_row.addStretch()
        layout.addLayout(tools_row)

        sep_tools = QFrame(); sep_tools.setFrameShape(QFrame.HLine); sep_tools.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep_tools)

        # ── Brush settings ────────────────────────────────────────────────
        self.brushSettingsWidget = QWidget(self.drawingPanel)
        brush_layout = QVBoxLayout(self.brushSettingsWidget)
        brush_layout.setContentsMargins(0, 0, 0, 0)
        brush_layout.setSpacing(4)

        brush_color_label = QLabel("Цвет кисти:")
        brush_color_label.setStyleSheet("font-size: 11px;")
        brush_layout.addWidget(brush_color_label)

        self._draw_current_color = QColor(Qt.black)
        self.drawColorBtn = QPushButton(self.drawingPanel)
        self.drawColorBtn.setObjectName("drawColorBtn")
        self.drawColorBtn.setToolTip("Выбрать цвет кисти")
        self.drawColorBtn.setFixedHeight(30)
        self.drawColorBtn.setStyleSheet(
            "QPushButton { padding: 4px 8px; border: 1px solid #bbb; border-radius: 3px; "
            "background: #f0f0f0; text-align: left; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        self._update_draw_color_btn_icon()
        brush_layout.addWidget(self.drawColorBtn)

        # Brush size: label + slider + thickness-preview icon
        brush_size_label = QLabel("Толщина кисти:")
        brush_size_label.setStyleSheet("font-size: 11px;")
        brush_layout.addWidget(brush_size_label)

        brush_size_row = QHBoxLayout()
        brush_size_row.setSpacing(6)

        self.drawBrushSizeSlider = QSlider(Qt.Horizontal, self.drawingPanel)
        self.drawBrushSizeSlider.setMinimum(1)
        self.drawBrushSizeSlider.setMaximum(20)
        self.drawBrushSizeSlider.setValue(4)
        self.drawBrushSizeSlider.setToolTip("Толщина кисти")
        brush_size_row.addWidget(self.drawBrushSizeSlider)

        # Thickness preview: a small label showing a filled circle
        self.drawBrushSizePreview = QLabel(self.drawingPanel)
        self.drawBrushSizePreview.setFixedSize(32, 32)
        self.drawBrushSizePreview.setToolTip("Предпросмотр толщины")
        brush_size_row.addWidget(self.drawBrushSizePreview)
        brush_layout.addLayout(brush_size_row)

        # Wire slider → preview update
        self.drawBrushSizeSlider.valueChanged.connect(self._update_brush_size_preview)
        self._update_brush_size_preview(4)   # initial render

        # Brush opacity
        brush_opacity_label = QLabel("Прозрачность:")
        brush_opacity_label.setStyleSheet("font-size: 11px;")
        brush_layout.addWidget(brush_opacity_label)

        brush_opacity_row = QHBoxLayout()
        brush_opacity_row.setSpacing(6)

        self.drawBrushOpacitySlider = QSlider(Qt.Horizontal, self.drawingPanel)
        self.drawBrushOpacitySlider.setMinimum(10)
        self.drawBrushOpacitySlider.setMaximum(100)
        self.drawBrushOpacitySlider.setValue(100)
        self.drawBrushOpacitySlider.setToolTip("Прозрачность кисти (100 = непрозрачно)")
        brush_opacity_row.addWidget(self.drawBrushOpacitySlider)

        self.drawBrushOpacityValueLabel = QLabel("100%", self.drawingPanel)
        self.drawBrushOpacityValueLabel.setFixedWidth(34)
        self.drawBrushOpacityValueLabel.setStyleSheet("font-size: 10px;")
        brush_opacity_row.addWidget(self.drawBrushOpacityValueLabel)
        brush_layout.addLayout(brush_opacity_row)

        self.drawBrushOpacitySlider.valueChanged.connect(
            lambda v: self.drawBrushOpacityValueLabel.setText(f"{v}%")
        )

        layout.addWidget(self.brushSettingsWidget)

        # ── Rectangle settings ────────────────────────────────────────────
        self.rectSettingsWidget = QWidget(self.drawingPanel)
        rect_layout = QVBoxLayout(self.rectSettingsWidget)
        rect_layout.setContentsMargins(0, 0, 0, 0)
        rect_layout.setSpacing(4)

        # Fill colour
        rect_fill_label = QLabel("Цвет заливки:")
        rect_fill_label.setStyleSheet("font-size: 11px;")
        rect_layout.addWidget(rect_fill_label)

        self._draw_rect_fill_color = QColor(Qt.black)
        self.drawRectFillColorBtn = QPushButton(self.drawingPanel)
        self.drawRectFillColorBtn.setObjectName("drawRectFillColorBtn")
        self.drawRectFillColorBtn.setToolTip("Выбрать цвет заливки")
        self.drawRectFillColorBtn.setFixedHeight(30)
        self.drawRectFillColorBtn.setStyleSheet(
            "QPushButton { padding: 4px 8px; border: 1px solid #bbb; border-radius: 3px; "
            "background: #f0f0f0; text-align: left; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        self._update_rect_fill_btn_icon()
        rect_layout.addWidget(self.drawRectFillColorBtn)

        # Border colour
        rect_border_color_label = QLabel("Цвет рамки:")
        rect_border_color_label.setStyleSheet("font-size: 11px;")
        rect_layout.addWidget(rect_border_color_label)

        self._draw_rect_border_color = QColor(Qt.black)
        self.drawRectBorderColorBtn = QPushButton(self.drawingPanel)
        self.drawRectBorderColorBtn.setObjectName("drawRectBorderColorBtn")
        self.drawRectBorderColorBtn.setToolTip("Выбрать цвет рамки")
        self.drawRectBorderColorBtn.setFixedHeight(30)
        self.drawRectBorderColorBtn.setStyleSheet(
            "QPushButton { padding: 4px 8px; border: 1px solid #bbb; border-radius: 3px; "
            "background: #f0f0f0; text-align: left; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        self._update_rect_border_btn_icon()
        rect_layout.addWidget(self.drawRectBorderColorBtn)

        # Border width: label + slider + thickness-preview icon
        border_width_label = QLabel("Толщина рамки:")
        border_width_label.setStyleSheet("font-size: 11px;")
        rect_layout.addWidget(border_width_label)

        border_width_row = QHBoxLayout()
        border_width_row.setSpacing(6)

        self.drawRectBorderWidthSlider = QSlider(Qt.Horizontal, self.drawingPanel)
        self.drawRectBorderWidthSlider.setMinimum(0)
        self.drawRectBorderWidthSlider.setMaximum(10)
        self.drawRectBorderWidthSlider.setValue(0)
        self.drawRectBorderWidthSlider.setToolTip("0 = без рамки")
        border_width_row.addWidget(self.drawRectBorderWidthSlider)

        self.drawRectBorderWidthPreview = QLabel(self.drawingPanel)
        self.drawRectBorderWidthPreview.setFixedSize(32, 32)
        self.drawRectBorderWidthPreview.setToolTip("Предпросмотр толщины рамки")
        border_width_row.addWidget(self.drawRectBorderWidthPreview)
        rect_layout.addLayout(border_width_row)

        self.drawRectBorderWidthSlider.valueChanged.connect(self._update_border_width_preview)
        self._update_border_width_preview(0)   # initial render

        # Rect opacity
        rect_opacity_label = QLabel("Прозрачность:")
        rect_opacity_label.setStyleSheet("font-size: 11px;")
        rect_layout.addWidget(rect_opacity_label)

        rect_opacity_row = QHBoxLayout()
        rect_opacity_row.setSpacing(6)

        self.drawRectOpacitySlider = QSlider(Qt.Horizontal, self.drawingPanel)
        self.drawRectOpacitySlider.setMinimum(10)
        self.drawRectOpacitySlider.setMaximum(100)
        self.drawRectOpacitySlider.setValue(100)
        self.drawRectOpacitySlider.setToolTip("Прозрачность фигуры (100 = непрозрачно)")
        rect_opacity_row.addWidget(self.drawRectOpacitySlider)

        self.drawRectOpacityValueLabel = QLabel("100%", self.drawingPanel)
        self.drawRectOpacityValueLabel.setFixedWidth(34)
        self.drawRectOpacityValueLabel.setStyleSheet("font-size: 10px;")
        rect_opacity_row.addWidget(self.drawRectOpacityValueLabel)
        rect_layout.addLayout(rect_opacity_row)

        self.drawRectOpacitySlider.valueChanged.connect(
            lambda v: self.drawRectOpacityValueLabel.setText(f"{v}%")
        )

        layout.addWidget(self.rectSettingsWidget)
        self.rectSettingsWidget.hide()   # shown only when Rect tool is active

        # Switch sub-panels on tool toggle
        self.drawBrushBtn.toggled.connect(
            lambda checked: self._on_draw_tool_toggled("brush", checked))
        self.drawRectBtn.toggled.connect(
            lambda checked: self._on_draw_tool_toggled("rect", checked))

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine); sep1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep1)

        # ── Undo / Redo buttons ───────────────────────────────────────────
        _undo_redo_style = (
            "QPushButton { border: 1px solid #bbb; border-radius: 3px; background: #f0f0f0; }"
            "QPushButton:hover { background: #e0e0e0; }"
            "QPushButton:pressed { background: #d0d8e8; }"
        )
        undo_redo_row = QHBoxLayout()
        undo_redo_row.setSpacing(4)

        self.drawUndoBtn = QPushButton("↩ Отменить", self.drawingPanel)
        self.drawUndoBtn.setFixedHeight(30)
        self.drawUndoBtn.setToolTip("Отменить последнее действие (Ctrl+Z)")
        self.drawUndoBtn.setStyleSheet(_undo_redo_style)
        self.drawUndoBtn.setEnabled(False)  # greyed until something is drawn
        undo_redo_row.addWidget(self.drawUndoBtn)

        self.drawRedoBtn = QPushButton("↪ Вернуть", self.drawingPanel)
        self.drawRedoBtn.setFixedHeight(30)
        self.drawRedoBtn.setToolTip("Вернуть отменённое действие (Ctrl+Shift+Z)")
        self.drawRedoBtn.setStyleSheet(_undo_redo_style)
        self.drawRedoBtn.setEnabled(False)  # greyed until something is undone
        undo_redo_row.addWidget(self.drawRedoBtn)

        layout.addLayout(undo_redo_row)

        # ── Clear button ──────────────────────────────────────────────────
        self.drawClearAllBtn = QPushButton("Очистить всё", self.drawingPanel)
        self.drawClearAllBtn.setFixedHeight(32)
        self.drawClearAllBtn.setStyleSheet(
            "QPushButton { border: 1px solid #bbb; border-radius: 3px; background: #f0f0f0; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        layout.addWidget(self.drawClearAllBtn)

        layout.addStretch()

        # ── Close button at bottom ────────────────────────────────────────
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); sep2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep2)

        self.drawCloseBtn = QPushButton("✕  Закрыть", self.drawingPanel)
        self.drawCloseBtn.setFixedHeight(36)
        self.drawCloseBtn.setStyleSheet(
            "QPushButton { color: #c0392b; font-weight: bold; border: 1px solid #e0a0a0; "
            "border-radius: 3px; background: #fdf0f0; }"
            "QPushButton:hover { background: #fad7d7; }"
        )
        layout.addWidget(self.drawCloseBtn)
    def _on_draw_tool_toggled(self, tool: str, checked: bool):
        """Show the correct settings sub-panel when a tool button is toggled."""
        if not checked:
            return
        show_brush = (tool == "brush")
        self.brushSettingsWidget.setVisible(show_brush)
        self.rectSettingsWidget.setVisible(not show_brush)

    def _update_brush_size_preview(self, value: int):
        """Render a filled circle whose diameter reflects the brush size."""
        from PySide6.QtGui import QPainter, QColor
        from PySide6.QtCore import QSize
        sz = 32
        pm = QPixmap(sz, sz)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        # diameter scaled so max value (40) fills the icon
        diam = max(2, int(value / 20 * (sz - 4))) + 2
        x = (sz - diam) // 2
        color = getattr(self, '_draw_current_color', QColor(Qt.black))
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(x, x, diam, diam)
        p.end()
        self.drawBrushSizePreview.setPixmap(pm)

    def _update_border_width_preview(self, value: int):
        """Render a square outline whose stroke reflects the border width."""
        from PySide6.QtGui import QPainter, QPen, QColor
        sz = 32
        pm = QPixmap(sz, sz)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        if value == 0:
            # Diagonal slash = "no border"
            p.setPen(QPen(QColor("#aaa"), 1))
            p.drawLine(4, sz - 4, sz - 4, 4)
        else:
            # Cap pen width so the square outline stays visible at all values
            pen_w = max(1, min(int(value / 10 * 10), 10))  # 1–10 px in the icon
            color = getattr(self, '_draw_rect_border_color', QColor(Qt.black))
            p.setPen(QPen(color, pen_w, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
            p.setBrush(Qt.NoBrush)
            margin = pen_w // 2 + 2
            p.drawRect(margin, margin, sz - margin * 2, sz - margin * 2)
        p.end()
        self.drawRectBorderWidthPreview.setPixmap(pm)

    def _update_rect_fill_btn_icon(self):
        """Refresh the fill-colour swatch. None fill -> hatched icon."""
        fill = getattr(self, "_draw_rect_fill_color", None)
        px = QPixmap(18, 18)
        if fill is not None:
            px.fill(fill)
            text = "  Цвет заливки"
        else:
            px.fill(QColor("#f0f0f0"))
            from PySide6.QtGui import QPainter, QPen
            p = QPainter(px)
            p.setPen(QPen(QColor("#888"), 1))
            p.drawLine(0, 18, 18, 0)
            p.drawLine(0, 9, 9, 0)
            p.drawLine(9, 18, 18, 9)
            p.end()
            text = "  Без заливки"
        self.drawRectFillColorBtn.setIcon(QIcon(px))
        self.drawRectFillColorBtn.setIconSize(QSize(18, 18))
        self.drawRectFillColorBtn.setText(text)

    def _update_rect_border_btn_icon(self):
        """Refresh the border-colour swatch on the button."""
        color = getattr(self, "_draw_rect_border_color", QColor(Qt.black))
        px = QPixmap(18, 18)
        px.fill(color)
        self.drawRectBorderColorBtn.setIcon(QIcon(px))
        self.drawRectBorderColorBtn.setIconSize(QSize(18, 18))
        self.drawRectBorderColorBtn.setText("  Цвет рамки")
    def _update_draw_color_btn_icon(self):
        """Refresh the brush colour swatch on the colour picker button."""
        px = QPixmap(18, 18)
        px.fill(self._draw_current_color)
        self.drawColorBtn.setIcon(QIcon(px))
        self.drawColorBtn.setIconSize(QSize(18, 18))
        self.drawColorBtn.setText("  Цвет кисти")

    def show_drawing_panel(self):
        """Switch the sidepanel to drawing tools, hiding the tab-button strip."""
        self.tabButtonsWidget.hide()
        self.sidePanelContent.show()
        self.sidePanelStack.setCurrentIndex(1)
        # Ensure panel has reasonable width
        if hasattr(self, 'splitter'):
            sizes = self.splitter.sizes()
            total = sum(sizes)
            panel_w = sizes[1] if sizes[1] >= 120 else 160
            self.splitter.setSizes([0, panel_w, max(400, total - panel_w)])

    def hide_drawing_panel(self):
        """Restore the normal tab-button strip and content."""
        self.tabButtonsWidget.show()
        self.sidePanelStack.setCurrentIndex(0)
        # Re-show whichever tab was previously active
        if self.pagesButton.isChecked():
            self.pagesTab.show()
            self.sidePanelContent.show()
            if hasattr(self, 'splitter'):
                sizes = self.splitter.sizes()
                total = sum(sizes)
                panel_w = sizes[1] if sizes[1] >= 120 else 160
                self.splitter.setSizes([25, panel_w, max(400, total - 25 - panel_w)])
        elif self.bookmarksButton.isChecked():
            self.bookmarkTab.show()
            self.sidePanelContent.show()
            if hasattr(self, 'splitter'):
                sizes = self.splitter.sizes()
                total = sum(sizes)
                panel_w = sizes[1] if sizes[1] >= 120 else 160
                self.splitter.setSizes([25, panel_w, max(400, total - 25 - panel_w)])
        else:
            self.sidePanelContent.hide()
            if hasattr(self, 'splitter'):
                total = sum(self.splitter.sizes())
                self.splitter.setSizes([25, 0, max(0, total - 25)])

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
        self.actionExport_Pages = QAction(main_window)
        self.actionExport_Pages.setObjectName("actionExport_Pages")

        self.actionPasswordDoc = QAction(main_window)
        self.actionPasswordDoc.setObjectName("actionPasswordDoc")

        self.actionEnumeratePages = QAction(main_window)
        self.actionEnumeratePages.setObjectName("actionEnumeratePages")

        # Help actions
        self.actionAbout = QAction(main_window)
        self.actionAbout.setObjectName("actionAbout")

        self.actionOpenHelp = QAction(main_window)
        self.actionOpenHelp.setObjectName("actionOpenHelp")

        # Recent files management actions
        self.actionClearRecentFiles = QAction(main_window)
        self.actionClearRecentFiles.setObjectName("actionClearRecentFiles")

        self.actionToggleFullscreen = QAction(main_window)
        self.actionToggleFullscreen.setObjectName("actionToggleFullscreen")
        self.actionToggleFullscreen.triggered.connect(main_window.toggle_fullscreen)

        self.actionRotateAllPagesClockwise = QAction(main_window)
        self.actionRotateAllPagesClockwise.setObjectName("actionRotateAllPagesClockwise")

    # def toggle_fullscreen(self, main_window):
    #     if main_window.isFullScreen():
    #         main_window.showNormal()
    #     else:
    #         main_window.showFullScreen()

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
        self.menuOpenRecent = QMenu("Открыть недавние файлы...", self.menuFile)
        self.menuOpenRecent.setObjectName("menuOpenRecent")

        # Add submenus to View menu
        self.menuRotation = QMenu("Rotation", self.menuView)
        # self.menuView.addMenu(self.menuRotation)

        self.menuNavigation = QMenu("Navigation", self.menuView)
        # self.menuView.addMenu(self.menuNavigation)

        self.menuZoom = QMenu("Zoom", self.menuView)
        # self.menuView.addMenu(self.menuZoom)

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
        # if sys.platform == "win32":
        self.menuFile.addAction(self.actionEmail)
        self.menuFile.addAction(self.actionCompress)
            # self.menuFile.addAction(self.actionEnumeratePages)
            # self.menuFile.addAction(self.actionPasswordDoc)
        self.menuFile.addAction(self.actionAboutPdf)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionQuit)

        # View menu
        # self.menuView.addAction(self.actionToggle_Panel)
        # self.menuView.addSeparator()

        # # View submenus
        # self.menuRotation.addAction(self.actionRotateViewClockwise)
        # self.menuRotation.addAction(self.actionRotateViewCounterclockwise)

        # self.menuNavigation.addAction(self.actionJumpToFirstPage)
        # self.menuNavigation.addAction(self.actionJumpToLastPage)

        self.menuView.addAction(self.actionPrevious_Page)
        self.menuView.addAction(self.actionNext_Page)
        self.menuView.addAction(self.actionJumpToFirstPage)
        self.menuView.addAction(self.actionJumpToLastPage)
        self.menuView.addSeparator()
        self.menuView.addAction(self.actionZoom_In)
        self.menuView.addAction(self.actionZoom_Out)
        self.menuView.addSeparator()
        self.menuView.addAction(self.actionFitToWidth)
        self.menuView.addAction(self.actionFitToHeight)
        self.menuView.addSeparator()
        self.menuView.addAction(self.actionToggleFullscreen)

        # Edit menu
        self.menuEdit.addAction(self.actionAddFile)
        self.menuEdit.addAction(self.actionExport_Pages)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionDeletePage)
        self.menuEdit.addAction(self.actionDeleteSpecificPages)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionMovePageUp)
        self.menuEdit.addAction(self.actionMovePageDown)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionRotateCurrentPageClockwise)
        self.menuEdit.addAction(self.actionRotateCurrentPageCounterclockwise)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionRotateAllPagesClockwise)
        # self.menuEdit.addAction(self.actionRotateSpecificPages)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.actionDraw)

        # Help menu
        self.menuHelp.addAction(self.actionAbout)
        self.menuHelp.addSeparator()
        self.menuHelp.addAction(self.actionOpenHelp)

    def define_toolbar_elements(self, main_window):
        """Create toolbar and its elements"""
        self.mainToolBar = QToolBar(main_window)
        self.mainToolBar.setObjectName("mainToolBar")
        self.mainToolBar.setMovable(False)
        self.mainToolBar.setFloatable(False)
        main_window.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.mainToolBar)

        # Zoom selector
        self.m_zoomSelector = ZoomSelector(main_window)
        self.m_zoomSelector.setMaximumWidth(70)

        # Page input and label
        self.m_pageInput = QLineEdit(main_window)
        self.m_pageLabel = QLabel(main_window)
        page_layout = QHBoxLayout()
        page_layout.addWidget(self.m_pageInput)

        if sys.platform != "win32":
            self.artificialSpacerPage = QWidget()
            self.artificialSpacerPage.setFixedWidth(10)
            page_layout.addWidget(self.artificialSpacerPage)

        page_layout.addWidget(self.m_pageLabel)
        self.page_widget = QWidget(main_window)
        self.page_widget.setLayout(page_layout)
        self.page_widget.setFixedWidth(100)

        # Set input field size
        font_metrics = self.m_pageInput.fontMetrics()
        character_width = font_metrics.horizontalAdvance("0")
        self.m_pageInput.setFixedWidth(character_width * 7)
        self.m_pageLabel.setFixedWidth(character_width * 8)
        self.m_pageInput.setPlaceholderText("")

        # Spacers
        self.spacerLeft = QWidget()
        self.spacerLeft.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.spacerMidLeft = QWidget()
        # self.spacerMidLeft.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.spacerMiddle = QWidget()
        self.spacerMiddle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.spacerMidRight = QWidget()
        # self.spacerMidRight.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.spacerRight = QWidget()
        self.spacerRight.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.artificialSpacer1 = QWidget()
        self.artificialSpacer1.setFixedWidth(10)
        self.artificialSpacer2 = QWidget()
        self.artificialSpacer2.setFixedWidth(10)
        self.artificialSpacer3 = QWidget()
        self.artificialSpacer3.setFixedWidth(10)
        self.artificialSpacer4 = QWidget()
        self.artificialSpacer4.setFixedWidth(10)
        self.artificialSpacer5 = QWidget()
        self.artificialSpacer5.setFixedWidth(10)
        self.artificialSpacer6 = QWidget()
        self.artificialSpacer6.setFixedWidth(10)
        self.artificialSpacer7 = QWidget()
        self.artificialSpacer7.setFixedWidth(10)
        self.artificialSpacer8 = QWidget()
        self.artificialSpacer8.setFixedWidth(10)

    def connect_toolbar_ui(self):
        """Connect toolbar elements"""
        # LEFT SECTION - FILE OPERATIONS

        self.mainToolBar.addAction(self.actionOpen)
        self.mainToolBar.addAction(self.actionSave)
        self.mainToolBar.addAction(self.actionSaveAs)
        self.mainToolBar.addAction(self.actionPrint)
        self.mainToolBar.addAction(self.actionEmail)
        self.mainToolBar.addAction(self.actionCompress)
        self.mainToolBar.addAction(self.actionClosePdf)

        # MIDDLE SECTION - MISCELLANEOUS

        self.mainToolBar.addWidget(self.spacerLeft)

        self.mainToolBar.addAction(self.actionZoom_In)
        self.mainToolBar.addAction(self.actionZoom_Out)
        self.mainToolBar.addWidget(self.m_zoomSelector)
        self.mainToolBar.addAction(self.actionFitToWidth)
        self.mainToolBar.addAction(self.actionFitToHeight)

        self.mainToolBar.addWidget(self.artificialSpacer1)
        self.mainToolBar.addSeparator()

        self.mainToolBar.addWidget(self.page_widget)

        self.mainToolBar.addSeparator()
        self.mainToolBar.addWidget(self.artificialSpacer2)

        self.mainToolBar.addAction(self.actionPrevious_Page)
        self.mainToolBar.addAction(self.actionNext_Page)

        self.mainToolBar.addWidget(self.artificialSpacer3)
        self.mainToolBar.addSeparator()
        self.mainToolBar.addWidget(self.artificialSpacer4)

        self.mainToolBar.addAction(self.actionRotateCurrentPageCounterclockwise)
        self.mainToolBar.addAction(self.actionRotateCurrentPageClockwise)

        self.mainToolBar.addWidget(self.artificialSpacer5)
        self.mainToolBar.addSeparator()
        self.mainToolBar.addWidget(self.artificialSpacer6)

        self.mainToolBar.addAction(self.actionMovePageUp)
        self.mainToolBar.addAction(self.actionMovePageDown)

        self.mainToolBar.addWidget(self.artificialSpacer7)
        self.mainToolBar.addSeparator()
        self.mainToolBar.addWidget(self.artificialSpacer8)

        self.mainToolBar.addAction(self.actionDeletePage)
        self.mainToolBar.addAction(self.actionAddFile)

        # RIGHT SECTION - DRAWING

        self.mainToolBar.addWidget(self.spacerRight)

        self.mainToolBar.addAction(self.actionDraw)

        # self.mainToolBar.addAction(self.actionRotateViewCounterclockwise)
        # self.mainToolBar.addAction(self.actionRotateViewClockwise)

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
            self.actionExport_Pages: "image_download.png",
            self.actionPasswordDoc: "password_doc.png",
            self.actionEnumeratePages: "enumerate_pages.png",
            self.actionClearRecentFiles: "delete_pages.png",

            # View actions
            self.actionToggle_Panel: "pages.png",
            self.actionToggleFullscreen: "pages.png",
            self.actionZoom_In: "zoom_in.png",
            self.actionZoom_Out: "zoom_out.png",
            self.actionFitToWidth: "fit_to_width.png",
            self.actionFitToHeight: "fit_to_height.png",
            self.actionRotateViewClockwise: "rotate_pages_clockwise.png",
            self.actionRotateViewCounterclockwise: "rotate_pages_counterclockwise.png",
            self.actionRotateAllPagesClockwise: "rotate_pages_clockwise.png",

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
            self.actionRotateCurrentPageClockwise: "rotate_temp_clockwise.png",
            self.actionRotateCurrentPageCounterclockwise: "rotate_temp_counterclockwise.png",
            self.actionRotateSpecificPages: "rotate_pages_180_degrees.png",
            self.actionAddFile: "add_file.png",
            self.actionDraw: "drawing.png",

            # Help actions
            self.actionAbout: "help.png",
            self.actionOpenHelp: "help.png",
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
