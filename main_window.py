import os
import sys
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QApplication, QFileDialog, QMessageBox, QSplitter,
    QWidget, QVBoxLayout, QLabel, QFrame, QInputDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QDragEnterEvent, QDropEvent

from updated_ui_main_window import UiMainWindow
from pdf_viewer import PDFViewer
from thumbnail_widget import ThumbnailWidget
from actions_handler import ActionsHandler
from settings_manager import settings_manager


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

        # Create PDF viewer and thumbnail widget
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
        self.setWindowTitle("PDF Editor")

    def setup_pdf_components(self):
        """Setup PDF viewer and thumbnail components"""
        # Replace the placeholder PDF view with our custom viewer
        if hasattr(self.ui, 'pdfView'):
            # Remove the placeholder
            old_pdf_view = self.ui.pdfView
            parent = old_pdf_view.parent()

            # Create new PDF viewer
            self.pdf_viewer = PDFViewer()

            # Replace in the UI
            if parent and hasattr(parent, 'layout') and parent.layout():
                layout = parent.layout()
                layout.replaceWidget(old_pdf_view, self.pdf_viewer)
                old_pdf_view.deleteLater()

            # Update reference
            self.ui.pdfView = self.pdf_viewer

        # Replace thumbnail widget if it exists
        if hasattr(self.ui, 'thumbnailList'):
            old_thumbnail = self.ui.thumbnailList
            parent = old_thumbnail.parent()

            # Create new thumbnail widget
            self.thumbnail_widget = ThumbnailWidget()

            # Replace in the UI
            if parent and hasattr(parent, 'layout') and parent.layout():
                layout = parent.layout()
                layout.replaceWidget(old_thumbnail, self.thumbnail_widget)
                old_thumbnail.deleteLater()

            # Update reference
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

        # Set panel visibility and size
        if hasattr(self.ui, 'sidePanelContent'):
            self.ui.sidePanelContent.setVisible(panel_visible)
            if panel_visible:
                # Set panel width
                splitter_sizes = [25, panel_width, self.width() - panel_width - 25]
                if hasattr(self.ui, 'splitter'):
                    self.ui.splitter.setSizes(splitter_sizes)

        # Set active tab
        if hasattr(self.ui.thumbnailList, 'pages_button') and hasattr(self.ui.thumbnailList, 'bookmarks_button'):
            if active_tab == "bookmarks":
                self.ui.thumbnailList.bookmarks_button.setChecked(True)
                self.ui.thumbnailList.show_bookmarks()
            else:
                self.ui.thumbnailList.pages_button.setChecked(True)
                self.ui.thumbnailList.show_pages()

        # Load thumbnail size
        thumbnail_size = settings_manager.get_thumbnail_size()
        if hasattr(self.ui.thumbnailList, 'size_slider'):
            settings_manager.save_thumbnail_size(self.ui.thumbnailList.thumbnail_size)  # self.ui.thumbnailList.size_slider.setValue(thumbnail_size)
            self.ui.thumbnailList.thumbnail_size = thumbnail_size

    def save_window_settings(self):
        """Save window settings"""
        settings_manager.save_window_state(
            self.size(),
            self.pos(),
            self.isMaximized()
        )

        # Save panel state
        panel_visible = True
        panel_width = 250
        active_tab = "pages"

        if hasattr(self.ui, 'sidePanelContent'):
            panel_visible = self.ui.sidePanelContent.isVisible()
            if hasattr(self.ui, 'splitter'):
                sizes = self.ui.splitter.sizes()
                if len(sizes) >= 2:
                    panel_width = sizes[1]

        if hasattr(self.ui.thumbnailList, 'bookmarks_button'):
            if self.ui.thumbnailList.bookmarks_button.isChecked():
                active_tab = "bookmarks"

        settings_manager.save_panel_state(panel_visible, panel_width, active_tab)

        # Save thumbnail size
        if hasattr(self.ui.thumbnailList, 'thumbnail_size'):
            settings_manager.save_thumbnail_size(self.ui.thumbnailList.thumbnail_size)

    def connect_signals(self):
        """Connect UI signals to their respective handlers"""

        # PDF viewer signals
        if hasattr(self.ui.pdfView, 'page_changed'):
            self.ui.pdfView.page_changed.connect(self.on_page_changed)
        if hasattr(self.ui.pdfView, 'document_modified'):
            self.ui.pdfView.document_modified.connect(self.on_document_modified)

        # Thumbnail signals
        if hasattr(self.ui.thumbnailList, 'page_clicked'):
            self.ui.thumbnailList.page_clicked.connect(self.on_thumbnail_clicked)

        # Page input
        if hasattr(self.ui, 'm_pageInput'):
            self.ui.m_pageInput.editingFinished.connect(self.go_to_page_input)

        # Zoom selector
        if hasattr(self.ui.m_zoomSelector, 'zoom_changed'):
            self.ui.m_zoomSelector.zoom_changed.connect(self.on_zoom_changed)

        # All action connections are now handled by ActionsHandler

    def load_document(self, file_path: str):
        """Load a PDF document with password handling"""
        if self.is_document_modified:
            reply = self.ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Save:
                if not self.actions_handler.save_file():
                    return

        # Check if we have a stored password for this file
        stored_password = settings_manager.get_encryption_password(file_path)

        # Use the PDF viewer's optimized loading
        if hasattr(self.ui.pdfView, 'open_document'):
            success = self.ui.pdfView.open_document(file_path)

            # If loading failed due to encryption, try with stored password
            if not success and stored_password:
                # Try to authenticate with stored password
                try:
                    import fitz
                    test_doc = fitz.open(file_path)
                    if test_doc.is_encrypted and test_doc.authenticate(stored_password):
                        test_doc.close()
                        success = self.ui.pdfView.open_document(file_path)
                    else:
                        test_doc.close()
                        # Remove invalid stored password
                        settings_manager.remove_encryption_password(file_path)
                except:
                    pass

            # If still failed and document is encrypted, ask for password
            if not success:
                success = self.handle_encrypted_document(file_path)
        else:
            success = False

        if success:
            self.current_document_path = file_path
            filename = os.path.basename(file_path)
            self.setWindowTitle(f"PDF Editor - {filename}")

            # Update thumbnail widget
            if hasattr(self.ui.thumbnailList, 'set_document'):
                self.ui.thumbnailList.set_document(
                    getattr(self.ui.pdfView, 'document', None),
                    file_path
                )

            self.is_document_modified = False
            self.update_ui_state()
            self.update_page_info()

            # Add to recent files
            settings_manager.add_recent_file(file_path)
            if hasattr(self.actions_handler, 'update_recent_files_menu'):
                self.actions_handler.update_recent_files_menu()
        else:
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
                    settings_manager.save_encryption_passwords(file_path, password)

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

        # Update file actions
        if hasattr(self.ui, 'actionSave'):
            self.ui.actionSave.setEnabled(has_document and self.is_document_modified)
        if hasattr(self.ui, 'actionSaveAs'):
            self.ui.actionSaveAs.setEnabled(has_document)
        if hasattr(self.ui, 'actionClosePdf'):
            self.ui.actionClosePdf.setEnabled(has_document)
        if hasattr(self.ui, 'actionPrint'):
            self.ui.actionPrint.setEnabled(has_document)

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
            'actionDeletePage', 'actionMovePageUp', 'actionMovePageDown',
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

    def update_page_info(self):
        """Update page information in UI"""
        if hasattr(self.ui.pdfView, 'document') and self.ui.pdfView.document:
            current_page = self.ui.pdfView.get_current_page() + 1

            # Count visible pages (non-deleted)
            total_pages = 0
            if hasattr(self.ui.pdfView, 'get_visible_page_count'):
                total_pages = self.ui.pdfView.get_visible_page_count()
            else:
                total_pages = len(self.ui.pdfView.document)

            # Update page input and label
            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText(str(current_page))
            if hasattr(self.ui, 'm_pageLabel'):
                self.ui.m_pageLabel.setText(f"of {total_pages}")

            # Update status bar
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(f"Page {current_page} of {total_pages}")
        else:
            # Clear page info when no document
            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText("")
            if hasattr(self.ui, 'm_pageLabel'):
                self.ui.m_pageLabel.setText("of 0")
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage("No document")

    def go_to_page_input(self):
        """Handle page input from toolbar"""
        try:
            if hasattr(self.ui, 'm_pageInput'):
                page_text = self.ui.m_pageInput.text()
                page_num = int(page_text) - 1  # Convert to 0-based index

                if hasattr(self.ui.pdfView, 'go_to_page'):
                    max_pages = self.ui.pdfView.get_visible_page_count()
                    if 0 <= page_num < max_pages:
                        self.ui.pdfView.go_to_page(page_num)
                    else:
                        # Reset to current page if out of range
                        current = self.ui.pdfView.get_current_page()
                        self.ui.m_pageInput.setText(str(current + 1))
        except ValueError:
            # Reset to current page if invalid input
            if hasattr(self.ui.pdfView, 'get_current_page'):
                current = self.ui.pdfView.get_current_page()
                if hasattr(self.ui, 'm_pageInput'):
                    self.ui.m_pageInput.setText(str(current + 1))

    def ask_save_changes(self) -> int:
        """Ask user if they want to save changes"""
        return QMessageBox.question(
            self,
            "Unsaved Changes",
            "The document has unsaved changes. Do you want to save them?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save
        )

    def update_window_title(self):
        """Update window title to reflect modification status"""
        if self.current_document_path:
            filename = os.path.basename(self.current_document_path)
            if self.is_document_modified:
                self.setWindowTitle(f"PDF Editor - {filename}*")
            else:
                self.setWindowTitle(f"PDF Editor - {filename}")
        else:
            self.setWindowTitle("PDF Editor")

    # Event handlers
    def on_page_changed(self, page_num: int):
        """Handle page change in viewer"""
        if hasattr(self.ui.thumbnailList, 'set_current_page'):
            self.ui.thumbnailList.set_current_page(page_num)
        self.update_page_info()

    def on_document_modified(self, is_modified: bool):
        """Handle document modification status change"""
        self.is_document_modified = is_modified
        self.update_ui_state()
        self.update_window_title()

    def on_thumbnail_clicked(self, page_num: int):
        """Handle thumbnail click"""
        if hasattr(self.ui.pdfView, 'go_to_page'):
            self.ui.pdfView.go_to_page(page_num)

    def on_zoom_changed(self, zoom_factor: float):
        """Handle zoom change from zoom selector"""
        if hasattr(self.ui.pdfView, 'set_zoom'):
            self.ui.pdfView.set_zoom(zoom_factor)

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

        # Clean up PDF viewer
        if hasattr(self.ui.pdfView, 'close_document'):
            self.ui.pdfView.close_document()

        event.accept()
