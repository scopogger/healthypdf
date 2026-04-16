import os

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtPdf import QPdfBookmarkModel
from PySide6.QtWidgets import (
    QMainWindow, QMessageBox, QInputDialog
)

# Single source of truth for the application name used in window titles
APP_NAME = "Редактор PDF Альт"

from actions_handler import ActionsHandler
from pdf_viewer import PDFViewer
from settings_manager import settings_manager
from thumbnail_widget import ThumbnailContainerWidget, ThumbnailInfo
from updated_ui_main_window import UiMainWindow


class MainWindow(QMainWindow):
    """
    Main window that combines the old UI design with efficient PDF handling.
    """

    def __init__(self):
        super().__init__()

        # UI setup
        self.ui = UiMainWindow()
        self.ui.setup_ui(self, "en")

        # Document state
        self.current_document_path = ""
        self.is_document_modified = False

        # Setup PDF components - the UI already creates PDFViewer instances
        self.setup_pdf_components()

        # Setup actions handler
        self.actions_handler = ActionsHandler(self)

        # Connect UI signals
        self.connect_signals()

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Load settings and update UI state
        self.load_window_settings()
        self.update_ui_state()

        # Window settings
        self.setWindowTitle(APP_NAME)

    def setup_pdf_components(self):
        """Setup PDF viewer and thumbnail components"""
        # PDF viewer should already be created by updated_ui_main_window.py
        if not hasattr(self.ui, 'pdfView') or not isinstance(self.ui.pdfView, PDFViewer):
            # Fallback: create new PDF viewer if not found
            print("Warning: PDFViewer not found in UI, creating new one")
            self.ui.pdfView = PDFViewer()

            # Try to add it to the splitter if it exists
            if hasattr(self.ui, 'splitter'):
                self.ui.splitter.addWidget(self.ui.pdfView)

        # Thumbnail widget should already be created by updated_ui_main_window.py
        if hasattr(self.ui, 'thumbnailList') and isinstance(self.ui.thumbnailList, ThumbnailContainerWidget):
            self.thumbnail_widget = self.ui.thumbnailList
        else:
            # Fallback: create new thumbnail widget if not found
            print("Warning: ThumbnailContainerWidget not found in UI, creating new one")
            self.thumbnail_widget = ThumbnailContainerWidget()
            self.ui.thumbnailList = self.thumbnail_widget

    def load_window_settings(self):
        """Load window settings from settings manager"""
        size, position, maximized = settings_manager.load_window_state()

        self.resize(size)
        self.move(position)

        if maximized:
            self.showMaximized()

        # Load panel state
        panel_visible, panel_width, active_tab = settings_manager.load_panel_state()

        # Set panel visibility and enforce size constraints
        if hasattr(self.ui, 'sidePanelContent') and hasattr(self.ui, 'splitter'):
            self.ui.sidePanelContent.setVisible(panel_visible)

            if panel_visible:
                # Enforce minimum/maximum panel width constraints
                min_panel_width = 150
                max_panel_width = 300  # Maximum allowed width
                constrained_width = max(min_panel_width, min(panel_width, max_panel_width))

                # Set the splitter sizes - tab buttons (25px) + content width + remaining for PDF view
                tab_buttons_width = 25
                total_sidebar_width = tab_buttons_width + constrained_width
                pdf_view_width = max(400, self.width() - total_sidebar_width - 25)  # Minimum 400px for PDF view

                splitter_sizes = [tab_buttons_width, constrained_width, pdf_view_width]
                self.ui.splitter.setSizes(splitter_sizes)

                # Set minimum and maximum sizes for the side panel content
                self.ui.sidePanelContent.setMinimumWidth(min_panel_width)
                self.ui.sidePanelContent.setMaximumWidth(max_panel_width)
            else:
                # When panel is hidden, give all space to PDF view
                self.ui.splitter.setSizes([25, 0, self.width() - 25])

        # Set active tab
        if hasattr(self.ui, 'pagesButton') and hasattr(self.ui, 'bookmarksButton'):
            if active_tab == "bookmarks":
                self.ui.bookmarksButton.setChecked(True)
                self.ui.toggle_bookmark_tab()
            else:
                self.ui.pagesButton.setChecked(True)
                self.ui.toggle_pages_tab()

    def save_window_settings(self):
        """Save window settings"""
        settings_manager.save_window_state(
            self.size(),
            self.pos(),
            self.isMaximized()
        )

        # Save panel state
        panel_visible = True
        panel_width = 150  # Default fallback
        active_tab = "pages"

        if hasattr(self.ui, 'sidePanelContent'):
            panel_visible = self.ui.sidePanelContent.isVisible()
            if hasattr(self.ui, 'splitter') and panel_visible:
                sizes = self.ui.splitter.sizes()
                if len(sizes) >= 3:
                    panel_width = sizes[1]  # Second element is sidebar content width

        if hasattr(self.ui, 'bookmarksButton'):
            if self.ui.bookmarksButton.isChecked():
                active_tab = "bookmarks"

        settings_manager.save_panel_state(panel_visible, panel_width, active_tab)

        # # Save thumbnail size
        # if hasattr(self.ui.thumbnailList, 'thumbnail_size'):
        #     settings_manager.save_thumbnail_size(self.ui.thumbnailList.thumbnail_size)

    def on_bookmark_clicked(self, index):
        """Handle bookmark selection with single click - adapted from old code"""
        if not index.isValid():
            return

        # Get page number from bookmark (0-based in Qt)
        page = index.data(int(QPdfBookmarkModel.Role.Page))
        zoom_level = index.data(int(QPdfBookmarkModel.Role.Level))

        print(f"Bookmark clicked - Page: {page}, Zoom: {zoom_level}")

        if page is not None:
            # Convert to layout index and navigate
            layout_index = self.ui.pdfView.layout_index_for_original(page)
            if layout_index is not None:
                print(f"Navigating to layout index: {layout_index}")
                self.ui.pdfView.scroll_to_page(layout_index)
            else:
                print(f"Could not find layout index for original page {page}")

    def load_bookmarks_document(self, file_path: str):
        """Load the same document into QPdfDocument for bookmarks"""
        if hasattr(self.ui, 'm_document'):
            self.ui.m_document.load(file_path)

    def connect_signals(self):
        """Connect UI signals to their respective handlers"""

        # Connect bookmark selection - use clicked for single-click response
        if hasattr(self.ui, 'bookmarkView'):
            self.ui.bookmarkView.clicked.connect(self.on_bookmark_clicked)

        # PDF viewer signals
        if hasattr(self.ui.pdfView, 'page_changed'):
            self.ui.pdfView.page_changed.connect(self.on_page_changed)
        if hasattr(self.ui.pdfView, 'document_modified'):
            self.ui.pdfView.document_modified.connect(self.on_document_modified)
        if hasattr(self.ui.pdfView, 'set_zoom'):
            self.ui.pdfView.set_zoom_signal.connect(self.ui.m_zoomSelector.set_zoom_value)

        # Thumbnail signals
        if hasattr(self.ui.thumbnailList, 'page_clicked'):
            self.ui.thumbnailList.page_clicked.connect(self.on_thumbnail_clicked)
            self.ui.thumbnailList.page_clicked.connect(self.ui.pdfView.scroll_to_page)

        self.ui.m_pageInput.installEventFilter(self)

        # Zoom selector
        if hasattr(self.ui, 'm_zoomSelector') and hasattr(self.ui.m_zoomSelector, 'zoom_changed'):
            self.ui.m_zoomSelector.zoom_changed.connect(self.on_zoom_changed)

        if hasattr(self.ui, 'actionDraw'):
            self.ui.actionDraw.toggled.connect(self.on_action_draw_toggled)

        # All action connections are now handled by ActionsHandler

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def eventFilter(self, obj, event):
        if obj == self.ui.m_pageInput:
            if event.type() == QEvent.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):

                    has_document = hasattr(self.ui.pdfView, 'document') and self.ui.pdfView.document is not None
                    if has_document:
                        self.go_to_page_input()
                    return True
        return super().eventFilter(obj, event)

    def load_document(self, file_path: str):
        """Load a PDF document with password handling"""
        if self.is_document_modified:
            reply = self.ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Save:
                if not self.actions_handler.save_file():
                    return

        print(f"Loading document: {file_path}")

        # Check if we have a stored password for this file
        stored_password = settings_manager.get_encryption_password(file_path)

        success = False
        if hasattr(self.ui.pdfView, 'open_document'):
            print("Attempting to open document with PDF viewer")
            success = self.ui.pdfView.open_document(file_path)
            print(f"PDF viewer open result: {success}")

            # If failed but password is stored, retry with password
            if not success and stored_password:
                print("Retrying with stored password")
                try:
                    import fitz
                    test_doc = fitz.open(file_path)
                    if test_doc.is_encrypted and test_doc.authenticate(stored_password):
                        test_doc.close()
                        self.ui.pdfView.document_password = stored_password
                        success = self.ui.pdfView.open_document(file_path)
                    else:
                        test_doc.close()
                        settings_manager.remove_encryption_password(file_path)
                except Exception as e:
                    print(f"Password retry failed: {e}")

            if not success:
                print("Document loading failed, checking if encrypted")
                success = self.handle_encrypted_document(file_path)
        else:
            print("Error: PDF viewer does not have open_document method")
            success = False

        if success:
            print("Document loaded successfully")
            self.current_document_path = file_path
            filename = os.path.basename(file_path)
            self.setWindowTitle(f"{APP_NAME} — {filename}")

            # Load document for bookmarks
            self.load_bookmarks_document(file_path)

            if hasattr(self.ui.thumbnailList, 'set_document'):

                self.ui.thumbnailList.set_document(
                    getattr(self.ui.pdfView, 'document', None)
                )

            self.is_document_modified = False
            self.update_ui_state()
            self.update_page_info()

            settings_manager.add_recent_file(file_path)
            if hasattr(self.actions_handler, 'update_recent_files_menu'):
                self.actions_handler.update_recent_files_menu()
        else:
            print(f"Failed to load document: {file_path}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open PDF file: {file_path}"
            )

    def handle_encrypted_document(self, file_path: str) -> bool:
        """Handle encrypted PDF documents"""
        try:
            import fitz
            test_doc = fitz.open(file_path)

            if not test_doc.is_encrypted:
                test_doc.close()
                return False

            # Ask for password
            password, ok = QInputDialog.getText(
                self,
                "PDF Password Required",
                f"Enter password for:\n{os.path.basename(file_path)}",
                QInputDialog.Password
            )

            if not ok or not password:
                test_doc.close()
                return False

            # Test password
            if test_doc.authenticate(password):
                test_doc.close()

                # Ask if user wants to remember password
                remember = QMessageBox.question(
                    self,
                    "Remember Password",
                    "Would you like to remember this password for future sessions?\n"
                    "(Password will be stored in application settings)",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if remember == QMessageBox.Yes:
                    settings_manager.save_encryption_password(file_path, password)

                # Try opening again
                return self.ui.pdfView.open_document(file_path)
            else:
                test_doc.close()
                QMessageBox.warning(
                    self,
                    "Invalid Password",
                    "The password you entered is incorrect."
                )
                return False

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error handling encrypted document: {str(e)}"
            )
            return False

    def update_ui_state(self):
        """Update UI state based on document availability"""
        has_document = hasattr(self.ui.pdfView, 'document') and self.ui.pdfView.document is not None

        print(f"Updating UI state, has_document: {has_document}")

        # Update file actions
        if hasattr(self.ui, 'actionSave'):
            self.ui.actionSave.setEnabled(has_document and self.is_document_modified)
        if hasattr(self.ui, 'actionSaveAs'):
            self.ui.actionSaveAs.setEnabled(has_document)
        if hasattr(self.ui, 'actionClosePdf'):
            self.ui.actionClosePdf.setEnabled(has_document)
        if hasattr(self.ui, 'actionPrint'):
            self.ui.actionPrint.setEnabled(has_document)
        if hasattr(self.ui, 'actionCompress'):
            self.ui.actionCompress.setEnabled(has_document)
        if hasattr(self.ui, 'actionEmail'):
            self.ui.actionEmail.setEnabled(has_document)
        if hasattr(self.ui, 'actionAboutPdf'):
            self.ui.actionAboutPdf.setEnabled(has_document)
        if hasattr(self.ui, 'actionDraw'):
            self.ui.actionDraw.setEnabled(has_document)
        if hasattr(self.ui, 'actionAddFile'):
            self.ui.actionAddFile.setEnabled(has_document)
        if hasattr(self.ui, 'actionExport_Pages'):
            self.ui.actionExport_Pages.setEnabled(has_document)

        # Update navigation actions
        nav_actions = [
            'actionPrevious_Page', 'actionNext_Page',
            'actionJumpToFirstPage', 'actionJumpToLastPage'
        ]
        for action_name in nav_actions:
            if hasattr(self.ui, action_name):
                getattr(self.ui, action_name).setEnabled(has_document)

        # Update page manipulation actions
        page_actions = [
            'actionDeletePage', 'actionDeleteSpecificPages',
            'actionMovePageUp', 'actionMovePageDown',
            'actionRotateCurrentPageClockwise', 'actionRotateCurrentPageCounterclockwise'
        ]
        for action_name in page_actions:
            if hasattr(self.ui, action_name):
                getattr(self.ui, action_name).setEnabled(has_document)

        # Update view actions
        view_actions = [
            'actionZoom_In', 'actionZoom_Out',
            'actionFitToWidth', 'actionFitToHeight'
        ]
        for action_name in view_actions:
            if hasattr(self.ui, action_name):
                getattr(self.ui, action_name).setEnabled(has_document)

    def get_current_display_page_number(self) -> int:
        """Get the current page's display number (1-based) using pdfView.pages_info and deleted_pages"""
        # if not hasattr(self.ui.pdfView, 'pages_info') or not self.ui.pdfView.pages_info:
        #     return 1

        # pdfView.get_current_page() now returns ORIGINAL page number
        current_original = self.ui.pdfView.get_current_page()
        display_number = 1
        for i, info in enumerate(self.ui.pdfView.page_widget_controller.pages_info):
            if info.page_num in self.ui.pdfView.deleted_pages:
                continue
            if info.page_num == current_original:
                return display_number
            display_number += 1
        return 1

    def get_total_display_pages(self) -> int:
        """Total visible pages (non-deleted)"""
        return self.ui.pdfView.page_widget_controller.countTotalPagesInfo

    def get_chunk_info_count(self):
        return self.ui.pdfView.page_widget_controller.current_chunk_index + 1, \
               len(self.ui.pdfView.page_widget_controller.chunks)

    def get_actual_page_from_display_number(self, display_number: int) -> int:
        """Convert a 1-based display number into a layout index (index into page_widgets/pages_info)"""
        # if not hasattr(self.ui.pdfView, 'pages_info') or not self.ui.pdfView.pages_info:
        #     return 0
        current_display = 1
        for i, info in enumerate(self.ui.pdfView.page_widget_controller.pages_info):
            if info.page_num in self.ui.pdfView.deleted_pages:
                continue
            if current_display == display_number:
                return i  # return layout index
            current_display += 1
        return 0

    def update_page_info(self):
        """Update toolbar/status with display numbers"""
        if hasattr(self.ui.pdfView, 'document') and self.ui.pdfView.document:
            current_display_page = self.get_current_display_page_number()
            total_display_pages = self.get_total_display_pages()
            current_chunk, total_chunk = self.get_chunk_info_count()

            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText(str(current_display_page))
            if hasattr(self.ui, 'm_pageLabel'):
                self.ui.m_pageLabel.setText(f"of {total_display_pages}")

            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(f"Страница {current_display_page} из {total_display_pages}. Часть {current_chunk} из {total_chunk}")
        else:
            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText("")
            if hasattr(self.ui, 'm_pageLabel'):
                self.ui.m_pageLabel.setText("of 0")
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage("No document")

    # def update_zoom_state(self):
    #     self.ui.actionFitToWidth.setChecked(1 * self.ui.pdfView.zoom_type)
    #     pass

    def go_to_page_input(self):
        """User typed a page number: convert display number -> layout index -> scroll and highlight."""
        try:
            if hasattr(self.ui, 'm_pageInput'):
                page_text = self.ui.m_pageInput.text()
                display_page_num = int(page_text)  # 1-based display number
                total_pages = self.get_total_display_pages()
                if 1 <= display_page_num <= total_pages:
                    layout_index = self.get_actual_page_from_display_number(display_page_num)
                    self.ui.pdfView.scroll_to_page(layout_index)

                    # Directly sync the thumbnail highlight. scroll_to_page fires
                    # page_changed only via a 200 ms scroll timer, so the first call
                    # may arrive before the thumbnail widget is ready. Calling
                    # set_current_page here ensures the highlight is always applied.
                    orig_page_num = self.ui.pdfView.page_widget_controller.getPageInfoByIndex(layout_index).page_num
                    if hasattr(self.ui.thumbnailList, 'set_current_page'):
                        self.ui.thumbnailList.set_current_page(orig_page_num)
                    self.update_page_info()
                else:
                    current_display_page = self.get_current_display_page_number()
                    self.ui.m_pageInput.setText(str(current_display_page))
        except (ValueError, Exception) as e:
            print(f"[go_to_page_input] {e}")
            current_display_page = self.get_current_display_page_number()
            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText(str(current_display_page))

    def ask_save_changes(self) -> int:
        """Спросить пользователя, хочет ли он сохранить изменения"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Несохранённые изменения")
        msg_box.setText("В документе есть несохранённые изменения. Хотите ли сохранить их?")
        msg_box.setIcon(QMessageBox.Question)

        # Создаем кнопки с русским текстом
        save_btn = msg_box.addButton("Сохранить", QMessageBox.AcceptRole)
        discard_btn = msg_box.addButton("Не сохранять", QMessageBox.DestructiveRole)
        cancel_btn = msg_box.addButton("Отмена", QMessageBox.RejectRole)

        # Устанавливаем кнопку по умолчанию
        msg_box.setDefaultButton(save_btn)

        msg_box.exec()

        # Возвращаем соответствующий стандартный код кнопки
        clicked_button = msg_box.clickedButton()
        if clicked_button == save_btn:
            return QMessageBox.Save
        elif clicked_button == discard_btn:
            return QMessageBox.Discard
        else:  # cancel_btn
            return QMessageBox.Cancel

    def update_window_title(self):
        """Update window title to reflect modification status"""
        if self.current_document_path:
            filename = os.path.basename(self.current_document_path)
            if self.is_document_modified:
                self.setWindowTitle(f"{APP_NAME} — {filename}*")
            else:
                self.setWindowTitle(f"{APP_NAME} — {filename}")
        else:
            self.setWindowTitle(APP_NAME)

    # Event handlers
    def on_page_changed(self, orig_page_num: int):
        """pdfView now emits ORIGINAL page numbers; thumbnail widget likely expects original page ids"""
        print(f"Calling 'on_page_changed' from main_window to page {orig_page_num}")
        if hasattr(self.ui.thumbnailList, 'set_current_page'):
            # thumbnailList probably expects original page number; if it expects layout index adjust accordingly
            try:
                self.ui.thumbnailList.set_current_page(orig_page_num)
            except Exception:
                # fallback: convert orig -> layout and call with layout index
                layout_idx = self.ui.pdfView.layout_index_for_original(orig_page_num)
                if layout_idx is not None and hasattr(self.ui.thumbnailList, 'set_current_page'):
                    self.ui.thumbnailList.set_current_page(layout_idx)
        self.update_page_info()
        # print(f"o:{orig_page_num}, g:{self.ui.pdfView.get_current_page()}")

    def on_action_draw_toggled(self, checked: bool):
        """Toggle drawing mode. If turning off and there are unsaved drawings prompt Save/Discard/Cancel."""
        if checked:
            # enable drawing mode
            if hasattr(self.ui.pdfView, 'set_drawing_mode'):
                self.ui.pdfView.set_drawing_mode(True)
        else:
            if hasattr(self.ui.pdfView, 'set_drawing_mode'):
                self.ui.pdfView.set_drawing_mode(False)

    def on_document_modified(self, is_modified: bool):
        """Handle document modification status change"""
        self.is_document_modified = is_modified
        self.update_ui_state()
        self.update_window_title()

    def on_thumbnail_clicked(self, page_num: int):
        """thumbnail clicked might send ORIGINAL page number or layout index; adapt"""
        if not hasattr(self.ui.pdfView, 'go_to_page'):
            return

        # If thumbnail widget sends original id -> convert to layout index
        layout_idx = None
        if hasattr(self.ui.pdfView, 'pages_info'):
            # try to interpret as original
            for i, info in enumerate(self.ui.pdfView.pages_info):
                if info.page_num == page_num:
                    layout_idx = i
                    break

        # If not found as original, maybe page_num already is a layout index
        if layout_idx is None:
            # sanity-check bounds
            try:
                if 0 <= int(page_num) < self.ui.pdfView.page_widget_controller.getLastPageWidget().orig_page_num:
                    layout_idx = int(page_num)
            except Exception:
                return

        if layout_idx is not None:
            self.ui.pdfView.go_to_page(layout_idx)

    def on_zoom_changed(self, zoom_factor: float):
        """Handle zoom change from zoom selector"""
        if hasattr(self.ui.pdfView, 'set_zoom'):
            zoom_factor = max(0.25, min(5.0, zoom_factor))
            self.ui.pdfView.set_zoom(zoom_factor, margin_y=0)

        # Save zoom level
        settings_manager.save_zoom_level(zoom_factor)

    # Drag and drop support
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith('.pdf'):
                event.accept()
            else:
                event.ignore()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle drop events"""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.pdf'):
                self.load_document(file_path)

    def cleanup_before_close(self):
        """Aggressive cleanup before application closes"""
        print("Performing aggressive cleanup before close...")

        # # Clear thumbnails
        if hasattr(self.ui, 'thumbnailList') and hasattr(self.ui.thumbnailList, 'clear_thumbnails'):
            self.ui.thumbnailList.clear_thumbnails()

        # Close PDF viewer document
        if hasattr(self.ui, 'pdfView') and hasattr(self.ui.pdfView, 'close_document'):
            self.ui.pdfView.close_document()

        # Clear any remaining references
        self.current_document_path = ""
        self.is_document_modified = False

        # Clear actions handler if it holds references
        if hasattr(self, 'actions_handler'):
            self.actions_handler = None

        # Force final garbage collection
        import gc
        for _ in range(3):
            gc.collect()

    # def pageInputEditing(self):
    #     self.ui.pdfView.zoom_action[self.ui.pdfView.zoom_type]()

    def closeEvent(self, event):
        """Handle application close event"""
        if self.is_document_modified:
            reply = self.ask_save_changes()
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.Save:
                if not self.actions_handler.save_file():
                    event.ignore()
                    return

        # Save window settings before closing
        self.save_window_settings()

        # Perform aggressive cleanup
        self.cleanup_before_close()

        event.accept()
