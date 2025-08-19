"""
Actions Handler - Handles all UI actions and connects them to functionality
"""

from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtCore import QPointF
from PySide6.QtGui import QKeySequence


class ActionsHandler:
    """Handles all UI actions for the PDF editor"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.ui = main_window.ui
        self.connect_all_actions()
    
    def connect_all_actions(self):
        """Connect all UI actions to their handlers"""
        self.connect_file_actions()
        self.connect_navigation_actions()
        self.connect_page_actions()
        self.connect_view_actions()
        self.connect_panel_actions()
    
    def connect_file_actions(self):
        """Connect file menu actions"""
        if hasattr(self.ui, 'actionOpen'):
            self.ui.actionOpen.triggered.connect(self.open_file)
        if hasattr(self.ui, 'actionSave'):
            self.ui.actionSave.triggered.connect(self.save_file)
        if hasattr(self.ui, 'actionSaveAs'):
            self.ui.actionSaveAs.triggered.connect(self.save_file_as)
        if hasattr(self.ui, 'actionClosePdf'):
            self.ui.actionClosePdf.triggered.connect(self.close_file)
        if hasattr(self.ui, 'actionQuit'):
            self.ui.actionQuit.triggered.connect(self.main_window.close)
    
    def connect_navigation_actions(self):
        """Connect navigation actions"""
        if hasattr(self.ui, 'actionPrevious_Page'):
            self.ui.actionPrevious_Page.triggered.connect(self.previous_page)
        if hasattr(self.ui, 'actionNext_Page'):
            self.ui.actionNext_Page.triggered.connect(self.next_page)
        if hasattr(self.ui, 'actionJumpToFirstPage'):
            self.ui.actionJumpToFirstPage.triggered.connect(self.jump_to_first_page)
        if hasattr(self.ui, 'actionJumpToLastPage'):
            self.ui.actionJumpToLastPage.triggered.connect(self.jump_to_last_page)
    
    def connect_page_actions(self):
        """Connect page manipulation actions"""
        if hasattr(self.ui, 'actionDeletePage'):
            self.ui.actionDeletePage.triggered.connect(self.delete_current_page)
        if hasattr(self.ui, 'actionMovePageUp'):
            self.ui.actionMovePageUp.triggered.connect(self.move_page_up)
        if hasattr(self.ui, 'actionMovePageDown'):
            self.ui.actionMovePageDown.triggered.connect(self.move_page_down)
        if hasattr(self.ui, 'actionRotateCurrentPageClockwise'):
            self.ui.actionRotateCurrentPageClockwise.triggered.connect(self.rotate_page_clockwise)
        if hasattr(self.ui, 'actionRotateCurrentPageCounterclockwise'):
            self.ui.actionRotateCurrentPageCounterclockwise.triggered.connect(self.rotate_page_counterclockwise)
    
    def connect_view_actions(self):
        """Connect view actions"""
        if hasattr(self.ui, 'actionZoom_In'):
            self.ui.actionZoom_In.triggered.connect(self.zoom_in)
        if hasattr(self.ui, 'actionZoom_Out'):
            self.ui.actionZoom_Out.triggered.connect(self.zoom_out)
        if hasattr(self.ui, 'actionFitToWidth'):
            self.ui.actionFitToWidth.triggered.connect(self.fit_to_width)
        if hasattr(self.ui, 'actionFitToHeight'):
            self.ui.actionFitToHeight.triggered.connect(self.fit_to_height)
        if hasattr(self.ui, 'actionRotateViewClockwise'):
            self.ui.actionRotateViewClockwise.triggered.connect(self.rotate_view_clockwise)
        if hasattr(self.ui, 'actionRotateViewCounterclockwise'):
            self.ui.actionRotateViewCounterclockwise.triggered.connect(self.rotate_view_counterclockwise)
    
    def connect_panel_actions(self):
        """Connect panel actions"""
        if hasattr(self.ui, 'actionToggle_Panel'):
            self.ui.actionToggle_Panel.triggered.connect(self.toggle_side_panel)
    
    # File operations
    def open_file(self):
        """Open PDF file dialog"""
        if self.main_window.is_document_modified:
            reply = self.main_window.ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Save:
                if not self.save_file():
                    return

        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Open PDF",
            "",
            "PDF Files (*.pdf)"
        )

        if file_path:
            self.main_window.load_document(file_path)

    def save_file(self) -> bool:
        """Save changes to current file"""
        if not self.main_window.current_document_path:
            return self.save_file_as()

        if hasattr(self.ui.pdfView, 'save_changes'):
            success = self.ui.pdfView.save_changes()
            if success:
                self.main_window.is_document_modified = False
                self.main_window.update_ui_state()
                self.main_window.update_window_title()
            return success

        return True  # Fallback for read-only viewer

    def save_file_as(self) -> bool:
        """Save changes to a new file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Save PDF As",
            "",
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return False

        if hasattr(self.ui.pdfView, 'save_changes'):
            success = self.ui.pdfView.save_changes(file_path)
            if success:
                self.main_window.current_document_path = file_path
                filename = os.path.basename(file_path)
                self.main_window.setWindowTitle(f"PDF Editor - {filename}")
                self.main_window.is_document_modified = False
                self.main_window.update_ui_state()
            return success

        return True

    def close_file(self):
        """Close current document"""
        if self.main_window.is_document_modified:
            reply = self.main_window.ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Save:
                if not self.save_file():
                    return

        if hasattr(self.ui.pdfView, 'close_document'):
            self.ui.pdfView.close_document()

        if hasattr(self.ui.thumbnailList, 'clear_thumbnails'):
            self.ui.thumbnailList.clear_thumbnails()

        self.main_window.current_document_path = ""
        self.main_window.is_document_modified = False
        self.main_window.setWindowTitle("PDF Editor")
        self.main_window.update_ui_state()
        self.main_window.update_page_info()

    # Navigation operations
    def previous_page(self):
        """Go to previous page"""
        if hasattr(self.ui.pdfView, 'get_current_page'):
            current = self.ui.pdfView.get_current_page()
            if current > 0:
                self.ui.pdfView.go_to_page(current - 1)

    def next_page(self):
        """Go to next page"""
        if hasattr(self.ui.pdfView, 'get_current_page'):
            current = self.ui.pdfView.get_current_page()
            max_page = self.ui.pdfView.get_visible_page_count() - 1
            if current < max_page:
                self.ui.pdfView.go_to_page(current + 1)

    def jump_to_first_page(self):
        """Jump to first page"""
        if hasattr(self.ui.pdfView, 'go_to_page'):
            self.ui.pdfView.go_to_page(0)

    def jump_to_last_page(self):
        """Jump to last page"""
        if hasattr(self.ui.pdfView, 'go_to_page'):
            last_page = self.ui.pdfView.get_visible_page_count() - 1
            self.ui.pdfView.go_to_page(last_page)

    # Page manipulation operations
    def delete_current_page(self):
        """Delete the current page"""
        if hasattr(self.ui.pdfView, 'delete_current_page'):
            success = self.ui.pdfView.delete_current_page()
            if success:
                self.main_window.on_document_modified(True)
                self.main_window.update_page_info()
                
                # Update thumbnail
                current_page = self.ui.pdfView.get_current_page()
                if hasattr(self.ui.thumbnailList, 'hide_page_thumbnail'):
                    self.ui.thumbnailList.hide_page_thumbnail(current_page)

    def move_page_up(self):
        """Move current page up"""
        if hasattr(self.ui.pdfView, 'move_page_up'):
            success = self.ui.pdfView.move_page_up()
            if success:
                self.main_window.on_document_modified(True)
                self.main_window.update_page_info()

    def move_page_down(self):
        """Move current page down"""
        if hasattr(self.ui.pdfView, 'move_page_down'):
            success = self.ui.pdfView.move_page_down()
            if success:
                self.main_window.on_document_modified(True)
                self.main_window.update_page_info()

    def rotate_page_clockwise(self):
        """Rotate current page clockwise"""
        if hasattr(self.ui.pdfView, 'rotate_page_clockwise'):
            success = self.ui.pdfView.rotate_page_clockwise()
            if success:
                self.main_window.on_document_modified(True)
                
                # Update thumbnail
                current_page = self.ui.pdfView.get_current_page()
                if hasattr(self.ui.thumbnailList, 'rotate_page_thumbnail'):
                    self.ui.thumbnailList.rotate_page_thumbnail(current_page, 90)

    def rotate_page_counterclockwise(self):
        """Rotate current page counterclockwise"""
        if hasattr(self.ui.pdfView, 'rotate_page_counterclockwise'):
            success = self.ui.pdfView.rotate_page_counterclockwise()
            if success:
                self.main_window.on_document_modified(True)
                
                # Update thumbnail
                current_page = self.ui.pdfView.get_current_page()
                if hasattr(self.ui.thumbnailList, 'rotate_page_thumbnail'):
                    self.ui.thumbnailList.rotate_page_thumbnail(current_page, -90)

    # View operations
    def zoom_in(self):
        """Zoom in"""
        if hasattr(self.ui.pdfView, 'set_zoom'):
            current_zoom = getattr(self.ui.pdfView, 'zoom_level', 1.0)
            new_zoom = min(5.0, current_zoom * 1.25)
            self.ui.pdfView.set_zoom(new_zoom)
            
            # Update zoom selector
            if hasattr(self.ui, 'm_zoomSelector') and hasattr(self.ui.m_zoomSelector, 'set_zoom_value'):
                self.ui.m_zoomSelector.set_zoom_value(new_zoom)

    def zoom_out(self):
        """Zoom out"""
        if hasattr(self.ui.pdfView, 'set_zoom'):
            current_zoom = getattr(self.ui.pdfView, 'zoom_level', 1.0)
            new_zoom = max(0.1, current_zoom * 0.8)
            self.ui.pdfView.set_zoom(new_zoom)
            
            # Update zoom selector
            if hasattr(self.ui, 'm_zoomSelector') and hasattr(self.ui.m_zoomSelector, 'set_zoom_value'):
                self.ui.m_zoomSelector.set_zoom_value(new_zoom)

    def fit_to_width(self):
        """Fit document to width"""
        if hasattr(self.ui.pdfView, 'fit_to_width'):
            self.ui.pdfView.fit_to_width()

    def fit_to_height(self):
        """Fit document to height"""
        if hasattr(self.ui.pdfView, 'fit_to_height'):
            self.ui.pdfView.fit_to_height()

    def rotate_view_clockwise(self):
        """Rotate view clockwise (temporary rotation)"""
        # Implementation for temporary view rotation
        pass

    def rotate_view_counterclockwise(self):
        """Rotate view counterclockwise (temporary rotation)"""
        # Implementation for temporary view rotation
        pass

    # Panel operations
    def toggle_side_panel(self):
        """Toggle side panel visibility"""
        if hasattr(self.ui, 'sidePanelContent'):
            is_visible = self.ui.sidePanelContent.isVisible()
            self.ui.sidePanelContent.setVisible(not is_visible)
