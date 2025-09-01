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
        self.setWindowTitle("PDF Editor")

    def setup_pdf_components(self):
        """Setup PDF viewer and thumbnail components"""
        # The UI already creates PDFViewer and ThumbnailWidget instances
        # We just need to get references to them

        # PDF viewer should already be created by updated_ui_main_window.py
        if hasattr(self.ui, 'pdfView') and isinstance(self.ui.pdfView, PDFViewer):
            self.pdf_viewer = self.ui.pdfView
        else:
            # Fallback: create new PDF viewer if not found
            print("Warning: PDFViewer not found in UI, creating new one")
            self.pdf_viewer = PDFViewer()
            self.ui.pdfView = self.pdf_viewer

            # Try to add it to the splitter if it exists
            if hasattr(self.ui, 'splitter'):
                self.ui.splitter.addWidget(self.pdf_viewer)

        # Thumbnail widget should already be created by updated_ui_main_window.py
        if hasattr(self.ui, 'thumbnailList') and isinstance(self.ui.thumbnailList, ThumbnailWidget):
            self.thumbnail_widget = self.ui.thumbnailList
        else:
            # Fallback: create new thumbnail widget if not found
            print("Warning: ThumbnailWidget not found in UI, creating new one")
            self.thumbnail_widget = ThumbnailWidget()
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

        # Load thumbnail size
        thumbnail_size = settings_manager.get_thumbnail_size()
        if hasattr(self.ui.thumbnailList, 'set_thumbnail_size'):
            self.ui.thumbnailList.set_thumbnail_size(thumbnail_size)
        elif hasattr(self.ui.thumbnailList, 'thumbnail_size'):
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
        if hasattr(self.ui, 'm_zoomSelector') and hasattr(self.ui.m_zoomSelector, 'zoom_changed'):
            self.ui.m_zoomSelector.zoom_changed.connect(self.on_zoom_changed)

        if hasattr(self.ui, 'actionDraw'):
            self.ui.actionDraw.toggled.connect(self.on_action_draw_toggled)

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

        print(f"Loading document: {file_path}")

        # Check if we have a stored password for this file
        stored_password = settings_manager.get_encryption_password(file_path)

        # Use the PDF viewer's optimized loading
        success = False
        if hasattr(self.ui.pdfView, 'open_document'):
            print("Attempting to open document with PDF viewer")
            success = self.ui.pdfView.open_document(file_path)
            print(f"PDF viewer open result: {success}")

            # If loading failed due to encryption, try with stored password
            if not success and stored_password:
                print("Retrying with stored password")
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
                except Exception as e:
                    print(f"Password retry failed: {e}")

            # If still failed and document is encrypted, ask for password
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
            self.setWindowTitle(f"PDF Editor - {filename}")

            # Update thumbnail widget
            if hasattr(self.ui.thumbnailList, 'set_document'):
                self.ui.thumbnailList.set_document(
                    getattr(self.ui.pdfView, 'document', None),
                    file_path
                )

            # Ensure viewer starts at top of layout (layout index 0) and refresh thumbnails' order
            try:
                # go to first layout position (if method exists)
                if hasattr(self.ui.pdfView, 'go_to_page'):
                    self.ui.pdfView.go_to_page(0)
                # compute visible_order (list of ORIGINAL page ids) and send to thumbnails
                if hasattr(self.ui.pdfView, 'pages_info') and hasattr(self.ui.thumbnailList, 'set_display_order'):
                    visible_order = [info.page_num for info in self.ui.pdfView.pages_info
                                     if info.page_num not in getattr(self.ui.pdfView, 'deleted_pages', set())]
                    self.ui.thumbnailList.set_display_order(visible_order)
                    # highlight current page
                    cur_orig = self.ui.pdfView.get_current_page()
                    self.ui.thumbnailList.set_current_page(cur_orig)
            except Exception:
                pass

            self.is_document_modified = False
            self.update_ui_state()
            self.update_page_info()

            # Add to recent files
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

    def get_current_display_page_number(self) -> int:
        """Get the current page's display number (1-based) using pdfView.pages_info and deleted_pages"""
        if not hasattr(self.ui.pdfView, 'pages_info') or not self.ui.pdfView.pages_info:
            return 1

        # pdfView.get_current_page() now returns ORIGINAL page number
        current_original = self.ui.pdfView.get_current_page()
        display_number = 1
        for i, info in enumerate(self.ui.pdfView.pages_info):
            if info.page_num in self.ui.pdfView.deleted_pages:
                continue
            if info.page_num == current_original:
                return display_number
            display_number += 1
        return 1

    def get_total_display_pages(self) -> int:
        """Total visible pages (non-deleted)"""
        if not hasattr(self.ui.pdfView, 'pages_info') or not self.ui.pdfView.pages_info:
            return 0
        count = 0
        for info in self.ui.pdfView.pages_info:
            if info.page_num not in self.ui.pdfView.deleted_pages:
                count += 1
        return count

    def get_actual_page_from_display_number(self, display_number: int) -> int:
        """Convert a 1-based display number into a layout index (index into page_widgets/pages_info)"""
        if not hasattr(self.ui.pdfView, 'pages_info') or not self.ui.pdfView.pages_info:
            return 0

        current_display = 1
        for i, info in enumerate(self.ui.pdfView.pages_info):
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

            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText(str(current_display_page))
            if hasattr(self.ui, 'm_pageLabel'):
                self.ui.m_pageLabel.setText(f"of {total_display_pages}")

            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(f"Page {current_display_page} of {total_display_pages}")
        else:
            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText("")
            if hasattr(self.ui, 'm_pageLabel'):
                self.ui.m_pageLabel.setText("of 0")
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage("No document")

    def go_to_page_input(self):
        """User typed a page number: convert display number -> layout index -> go_to_page"""
        try:
            if hasattr(self.ui, 'm_pageInput'):
                page_text = self.ui.m_pageInput.text()
                display_page_num = int(page_text)  # 1-based display number
                total_pages = self.get_total_display_pages()
                if 1 <= display_page_num <= total_pages:
                    layout_index = self.get_actual_page_from_display_number(display_page_num)
                    if hasattr(self.ui.pdfView, 'go_to_page'):
                        self.ui.pdfView.go_to_page(layout_index)
                else:
                    current_display_page = self.get_current_display_page_number()
                    self.ui.m_pageInput.setText(str(current_display_page))
        except ValueError:
            current_display_page = self.get_current_display_page_number()
            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText(str(current_display_page))

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
    def on_page_changed(self, orig_page_num: int):
        """pdfView now emits ORIGINAL page numbers; thumbnail widget likely expects original page ids"""
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

    def on_action_draw_toggled(self, checked: bool):
        """Toggle drawing mode. If turning off and there are unsaved drawings prompt Save/Discard/Cancel."""
        if checked:
            # enable drawing mode
            if hasattr(self.ui.pdfView, 'set_drawing_mode'):
                self.ui.pdfView.set_drawing_mode(True)
        else:
            # user requested to exit drawing mode — check unsaved annotations
            if hasattr(self.ui.pdfView, 'any_annotations_dirty') and self.ui.pdfView.any_annotations_dirty():
                from PySide6.QtWidgets import QMessageBox
                choice = QMessageBox.question(
                    self,
                    "Save drawings?",
                    "Save drawings to the document? (Save = persist, Discard = remove)",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save
                )
                if choice == QMessageBox.Save:
                    # mark modified so normal Save will persist drawings
                    # we set is_modified so Save action is enabled
                    if hasattr(self.ui.pdfView, 'is_modified'):
                        self.ui.pdfView.is_modified = True
                        try:
                            self.ui.pdfView.document_modified.emit(True)
                        except Exception:
                            pass
                    # disable drawing UI but keep drawings in memory (they will be merged on actual Save)
                    if hasattr(self.ui.pdfView, 'set_drawing_mode'):
                        self.ui.pdfView.set_drawing_mode(False)
                elif choice == QMessageBox.Discard:
                    # clear overlays on all pages
                    for w in getattr(self.ui.pdfView, "page_widgets", []):
                        try:
                            w.overlay.clear_annotations()
                        except Exception:
                            pass
                    if hasattr(self.ui.pdfView, 'set_drawing_mode'):
                        self.ui.pdfView.set_drawing_mode(False)
                    # mark not modified if nothing else changed
                    self.is_document_modified = False
                    try:
                        self.ui.pdfView.document_modified.emit(False)
                    except Exception:
                        pass
                else:
                    # cancel: re-enable drawing toggle
                    try:
                        self.ui.actionDraw.setChecked(True)
                    except Exception:
                        pass
                    return
            else:
                # no dirty annotations: just disable
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
                if 0 <= int(page_num) < len(self.ui.pdfView.page_widgets):
                    layout_idx = int(page_num)
            except Exception:
                return

        if layout_idx is not None:
            self.ui.pdfView.go_to_page(layout_idx)

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
