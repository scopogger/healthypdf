import os
import sys
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QApplication, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QKeySequence, QDragEnterEvent, QDropEvent

# Import the updated UI
from updated_ui_main_window import UiMainWindow

# Import integrated components
from integrated_pdf_viewer import IntegratedPDFViewer, IntegratedThumbnailWidget, ZoomSelector


class IntegratedMainWindow(QMainWindow):
    """
    Main window that combines the old UI design with the new efficient PDF handling.
    This class bridges the UI components with the integrated PDF viewer functionality.
    """

    def __init__(self):
        super().__init__()

        # UI setup
        self.ui = UiMainWindow()
        self.ui.setup_ui(self)

        # Document state
        self.current_document_path = ""
        self.is_document_modified = False

        # Connect UI signals to handlers
        self.connect_signals()

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Update initial UI state
        self.update_ui_state()

        # Window settings
        self.setWindowTitle("PDF Editor")

    def connect_signals(self):
        """Connect UI signals to their respective handlers"""

        # File operations
        self.ui.actionOpen.triggered.connect(self.open_file)
        self.ui.actionSave.triggered.connect(self.save_file)
        self.ui.actionSaveAs.triggered.connect(self.save_file_as)
        self.ui.actionClosePdf.triggered.connect(self.close_file)
        self.ui.actionQuit.triggered.connect(self.close)

        # Navigation
        self.ui.actionPrevious_Page.triggered.connect(self.previous_page)
        self.ui.actionNext_Page.triggered.connect(self.next_page)
        self.ui.actionJumpToFirstPage.triggered.connect(self.jump_to_first_page)
        self.ui.actionJumpToLastPage.triggered.connect(self.jump_to_last_page)

        # Page manipulation
        self.ui.actionDeletePage.triggered.connect(self.delete_current_page)
        self.ui.actionMovePageUp.triggered.connect(self.move_page_up)
        self.ui.actionMovePageDown.triggered.connect(self.move_page_down)
        self.ui.actionRotateCurrentPageClockwise.triggered.connect(self.rotate_page_clockwise)
        self.ui.actionRotateCurrentPageCounterclockwise.triggered.connect(self.rotate_page_counterclockwise)

        # View operations
        self.ui.actionZoom_In.triggered.connect(self.zoom_in)
        self.ui.actionZoom_Out.triggered.connect(self.zoom_out)
        self.ui.actionFitToWidth.triggered.connect(self.fit_to_width)
        self.ui.actionFitToHeight.triggered.connect(self.fit_to_height)
        self.ui.actionRotateViewClockwise.triggered.connect(self.rotate_view_clockwise)
        self.ui.actionRotateViewCounterclockwise.triggered.connect(self.rotate_view_counterclockwise)

        # Panel operations
        self.ui.actionToggle_Panel.triggered.connect(self.toggle_side_panel)

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

    def update_ui_state(self):
        """Update UI state based on document availability"""
        has_document = hasattr(self.ui.pdfView, 'document') and self.ui.pdfView.document is not None

        # Update actions
        self.ui.actionSave.setEnabled(has_document and self.is_document_modified)
        self.ui.actionSaveAs.setEnabled(has_document)
        self.ui.actionClosePdf.setEnabled(has_document)

        # Navigation actions
        self.ui.actionPrevious_Page.setEnabled(has_document)
        self.ui.actionNext_Page.setEnabled(has_document)
        self.ui.actionJumpToFirstPage.setEnabled(has_document)
        self.ui.actionJumpToLastPage.setEnabled(has_document)

        # Page manipulation actions
        self.ui.actionDeletePage.setEnabled(has_document)
        self.ui.actionMovePageUp.setEnabled(has_document)
        self.ui.actionMovePageDown.setEnabled(has_document)
        self.ui.actionRotateCurrentPageClockwise.setEnabled(has_document)
        self.ui.actionRotateCurrentPageCounterclockwise.setEnabled(has_document)

        # View actions
        self.ui.actionZoom_In.setEnabled(has_document)
        self.ui.actionZoom_Out.setEnabled(has_document)
        self.ui.actionFitToWidth.setEnabled(has_document)
        self.ui.actionFitToHeight.setEnabled(has_document)
        self.ui.actionRotateViewClockwise.setEnabled(has_document)
        self.ui.actionRotateViewCounterclockwise.setEnabled(has_document)

    def update_page_info(self):
        """Update page information in UI"""
        if hasattr(self.ui.pdfView, 'document') and self.ui.pdfView.document:
            current_page = self.ui.pdfView.get_current_page() + 1

            # Count visible pages (non-deleted)
            total_pages = 0
            if hasattr(self.ui.pdfView, 'page_widgets'):
                for widget in self.ui.pdfView.page_widgets:
                    if not widget.isHidden():
                        total_pages += 1
            else:
                total_pages = len(self.ui.pdfView.document)

            # Update page input and label
            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText(str(current_page))
            if hasattr(self.ui, 'm_pageLabel'):
                self.ui.m_pageLabel.setText(f"of {total_pages}")

            # Update status bar
            if hasattr(self.ui, 'statusBar'):
                self.ui.statusBar.showMessage(f"Page {current_page} of {total_pages}")
        else:
            # Clear page info when no document
            if hasattr(self.ui, 'm_pageInput'):
                self.ui.m_pageInput.setText("")
            if hasattr(self.ui, 'm_pageLabel'):
                self.ui.m_pageLabel.setText("of 0")
            if hasattr(self.ui, 'statusBar'):
                self.ui.statusBar.showMessage("No document")

    # File operations
    def open_file(self):
        """Open PDF file dialog"""
        if self.is_document_modified:
            reply = self.ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Save:
                if not self.save_file():
                    return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            "",
            "PDF Files (*.pdf)"
        )

        if file_path:
            self.load_document(file_path)

    def load_document(self, file_path: str):
        """Load a PDF document"""
        if hasattr(self.ui.pdfView, 'open_document'):
            success = self.ui.pdfView.open_document(file_path)
        else:
            # Fallback for standard QPdfView
            from PySide6.QtPdf import QPdfDocument
            document = QPdfDocument()
            if document.load(file_path) == QPdfDocument.Status.Ready:
                self.ui.pdfView.setDocument(document)
                success = True
            else:
                success = False

        if success:
            self.current_document_path = file_path
            filename = os.path.basename(file_path)
            self.setWindowTitle(f"PDF Editor - {filename}")

            # Update thumbnail widget if it's the integrated version
            if hasattr(self.ui.thumbnailList, 'set_document'):
                self.ui.thumbnailList.set_document(
                    getattr(self.ui.pdfView, 'document', None),
                    file_path
                )

            self.is_document_modified = False
            self.update_ui_state()
            self.update_page_info()
        else:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open PDF file: {file_path}"
            )

    def save_file(self) -> bool:
        """Save changes to current file"""
        if not self.current_document_path:
            return self.save_file_as()

        if hasattr(self.ui.pdfView, 'save_changes'):
            success = self.ui.pdfView.save_changes()
            if success:
                self.is_document_modified = False
                self.update_ui_state()
                self.update_window_title()
            return success

        return True  # Fallback for read-only viewer

    def save_file_as(self) -> bool:
        """Save changes to a new file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF As",
            "",
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return False

        if hasattr(self.ui.pdfView, 'save_changes'):
            success = self.ui.pdfView.save_changes(file_path)
            if success:
                self.current_document_path = file_path
                filename = os.path.basename(file_path)
                self.setWindowTitle(f"PDF Editor - {filename}")
                self.is_document_modified = False
                self.update_ui_state()
            return success

        return True

    def close_file(self):
        """Close current document"""
        if self.is_document_modified:
            reply = self.ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Save:
                if not self.save_file():
                    return

        if hasattr(self.ui.pdfView, 'close_document'):
            self.ui.pdfView.close_document()
        else:
            # Fallback for standard QPdfView
            self.ui.pdfView.setDocument(None)

        if hasattr(self.ui.thumbnailList, 'clear_thumbnails'):
            self.ui.thumbnailList.clear_thumbnails()

        self.current_document_path = ""
        self.is_document_modified = False
        self.setWindowTitle("PDF Editor")
        self.update_ui_state()
        self.update_page_info()

    def ask_save_changes(self) -> int:
        """Ask user if they want to save changes"""
        return QMessageBox.question(
            self,
            "Unsaved Changes",
            "The document has unsaved changes. Do you want to save them?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save
        )

    # Navigation operations
    def previous_page(self):
        """Go to previous page"""
        if hasattr(self.ui.pdfView, 'get_current_page'):
            current = self.ui.pdfView.get_current_page()
            if current > 0:
                self.ui.pdfView.go_to_page(current - 1)
        else:
            # Fallback for standard QPdfView
            nav = self.ui.pdfView.pageNavigator()
            if nav.currentPage() > 0:
                nav.jump(nav.currentPage() - 1, QPointF(), nav.currentZoom())

    def next_page(self):
        """Go to next page"""
        if hasattr(self.ui.pdfView, 'get_current_page'):
            current = self.ui.pdfView.get_current_page()
            if hasattr(self.ui.pdfView, 'page_widgets'):
                max_page = len(self.ui.pdfView.page_widgets) - 1
            else:
                max_page = len(self.ui.pdfView.document) - 1 if self.ui.pdfView.document else 0

            if current < max_page:
                self.ui.pdfView.go_to_page(current + 1)
        else:
            # Fallback for standard QPdfView
            nav = self.ui.pdfView.pageNavigator()
            doc = self.ui.pdfView.document()
            if doc and nav.currentPage() < doc.pageCount() - 1:
                nav.jump(nav.currentPage() + 1, QPointF(), nav.currentZoom())

    def jump_to_first_page(self):
        """Jump to first page"""
        if hasattr(self.ui.pdfView, 'go_to_page'):
            self.ui.pdfView.go_to_page(0)
        else:
            nav = self.ui.pdfView.pageNavigator()
            nav.jump(0, QPointF(), nav.currentZoom())

    def jump_to_last_page(self):
        """Jump to last page"""
        if hasattr(self.ui.pdfView, 'go_to_page'):
            if hasattr(self.ui.pdfView, 'page_widgets'):
                last_page = len(self.ui.pdfView.page_widgets) - 1
            else:
                last_page = len(self.ui.pdfView.document) - 1 if self.ui.pdfView.document else 0
            self.ui.pdfView.go_to_page(last_page)
        else:
            nav = self.ui.pdfView.pageNavigator()
            doc = self.ui.pdfView.document()
            if doc:
                nav.jump(doc.pageCount() - 1, QPointF(), nav.currentZoom())

    def go_to_page_input(self):
        """Handle page input from toolbar"""
        try:
            if hasattr(self.ui, 'm_pageInput'):
                page_text = self.ui.m_pageInput.text()
                page_num = int(page_text) - 1  # Convert to 0-based index

                if hasattr(self.ui.pdfView, 'go_to_page'):
                    max_pages = len(self.ui.pdfView.page_widgets) if hasattr(self.ui.pdfView, 'page_widgets') else 0
                    if 0 <= page_num < max_pages:
                        self.ui.pdfView.go_to_page(page_num)
                    else:
                        # Reset to current page if out of range
                        current = self.ui.pdfView.get_current_page()
                        self.ui.m_pageInput.setText(str(current + 1))
                else:
                    # Fallback for standard QPdfView
                    nav = self.ui.pdfView.pageNavigator()
                    doc = self.ui.pdfView.document()
                    if doc and 0 <= page_num < doc.pageCount():
                        nav.jump(page_num, QPointF(), nav.currentZoom())
        except ValueError:
            # Reset to current page if invalid input
            if hasattr(self.ui.pdfView, 'get_current_page'):
                current = self.ui.pdfView.get_current_page()
                self.ui.m_pageInput.setText(str(current + 1))

    # Page manipulation operations
    def delete_current_page(self):
        """Delete the current page"""
        if hasattr(self.ui.pdfView, 'delete_current_page'):
            success = self.ui.pdfView.delete_current_page()
            if success:
                self.on_document_modified(True)
                self.update_page_info()
        else:
            QMessageBox.information(
                self,
                "Feature Not Available",
                "Page deletion is not available in this view mode."
            )

    def move_page_up(self):
        """Move current page up"""
        if hasattr(self.ui.pdfView, 'move_page_up'):
            success = self.ui.pdfView.move_page_up()
            if success:
                self.on_document_modified(True)
                self.update_page_info()

    def move_page_down(self):
        """Move current page down"""
        if hasattr(self.ui.pdfView, 'move_page_down'):
            success = self.ui.pdfView.move_page_down()
            if success:
                self.on_document_modified(True)
                self.update_page_info()

    def rotate_page_clockwise(self):
        """Rotate current page clockwise"""
        if hasattr(self.ui.pdfView, 'rotate_page_clockwise'):
            success = self.ui.pdfView.rotate_page_clockwise()
            if success:
                self.on_document_modified(True)
                # Update thumbnail if available
                if hasattr(self.ui.thumbnailList, 'rotate_page_thumbnail'):
                    current_page = self.ui.pdfView.get_current_page()
                    self.ui.thumbnailList.rotate_page_thumbnail(current_page, 90)

    def rotate_page_counterclockwise(self):
        """Rotate current page counterclockwise"""
        if hasattr(self.ui.pdfView, 'rotate_page_counterclockwise'):
            success = self.ui.pdfView.rotate_page_counterclockwise()
            if success:
                self.on_document_modified(True)
                # Update thumbnail if available
                if hasattr(self.ui.thumbnailList, 'rotate_page_thumbnail'):
                    current_page = self.ui.pdfView.get_current_page()
                    self.ui.thumbnailList.rotate_page_thumbnail(current_page, -90)

    # View operations
    def zoom_in(self):
        """Zoom in"""
        if hasattr(self.ui.pdfView, 'set_zoom'):
            current_zoom = getattr(self.ui.pdfView, 'zoom_level', 1.0)
            new_zoom = min(5.0, current_zoom * 1.25)
            self.ui.pdfView.set_zoom(new_zoom)
            if hasattr(self.ui.m_zoomSelector, 'set_zoom_value'):
                self.ui.m_zoomSelector.set_zoom_value(new_zoom)
        else:
            # Fallback for standard QPdfView
            nav = self.ui.pdfView.pageNavigator()
            nav.jump(nav.currentPage(), nav.currentLocation(), nav.currentZoom() * 1.25)

    def zoom_out(self):
        """Zoom out"""
        if hasattr(self.ui.pdfView, 'set_zoom'):
            current_zoom = getattr(self.ui.pdfView, 'zoom_level', 1.0)
            new_zoom = max(0.1, current_zoom * 0.8)
            self.ui.pdfView.set_zoom(new_zoom)
            if hasattr(self.ui.m_zoomSelector, 'set_zoom_value'):
                self.ui.m_zoomSelector.set_zoom_value(new_zoom)
        else:
            # Fallback for standard QPdfView
            nav = self.ui.pdfView.pageNavigator()
            nav.jump(nav.currentPage(), nav.currentLocation(), nav.currentZoom() * 0.8)

    def fit_to_width(self):
        """Fit document to width"""
        if hasattr(self.ui.pdfView, 'setZoomMode'):
            from PySide6.QtPdfWidgets import QPdfView
            self.ui.pdfView.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def fit_to_height(self):
        """Fit document to height"""
        if hasattr(self.ui.pdfView, 'setZoomMode'):
            from PySide6.QtPdfWidgets import QPdfView
            self.ui.pdfView.setZoomMode(QPdfView.ZoomMode.FitInView)

    def rotate_view_clockwise(self):
        """Rotate view clockwise (temporary rotation)"""
        # This would be a temporary view rotation, different from page rotation
        pass

    def rotate_view_counterclockwise(self):
        """Rotate view counterclockwise (temporary rotation)"""
        # This would be a temporary view rotation, different from page rotation
        pass

    # Panel operations
    def toggle_side_panel(self):
        """Toggle side panel visibility"""
        if hasattr(self.ui, 'sidePanelContent'):
            is_visible = self.ui.sidePanelContent.isVisible()
            self.ui.sidePanelContent.setVisible(not is_visible)

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
                if not self.save_file():
                    event.ignore()
                    return

        event.accept()


def main():
    """Main entry point"""
    app = QApplication(sys.argv)

    app.setApplicationName("PDF Editor")
    app.setApplicationVersion("2.0")

    window = IntegratedMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
