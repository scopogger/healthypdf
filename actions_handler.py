"""
Enhanced Actions Handler - Handles all UI actions with proper page numbering
"""
import os
import fitz
from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QInputDialog, QProgressDialog, QApplication
)
from PySide6.QtCore import QPointF, Qt
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtGui import QPainter, QImage, QPageLayout, QAction
from settings_manager import settings_manager


def messagebox_info(parent, title, message):
    """Show info message box"""
    QMessageBox.information(parent, title, message)


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
        self.connect_recent_files()
        self.connect_print_actions()

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

    def connect_recent_files(self):
        """Connect recent files actions"""
        # Update recent files menu
        self.update_recent_files_menu()

    def connect_print_actions(self):
        """Connect printing actions"""
        if hasattr(self.ui, 'actionPrint'):
            self.ui.actionPrint.triggered.connect(self.print_document)

    def get_visible_pages_in_layout_order(self):
        """Get list of visible page indices in their current layout order"""
        visible_pages = []
        if hasattr(self.ui.pdfView, 'pages_layout') and hasattr(self.ui.pdfView, 'page_widgets'):
            for i in range(self.ui.pdfView.pages_layout.count()):
                item = self.ui.pdfView.pages_layout.itemAt(i)
                if item and item.widget() and not item.widget().isHidden():
                    # Find which page widget this is
                    widget = item.widget()
                    for j, page_widget in enumerate(self.ui.pdfView.page_widgets):
                        if page_widget == widget:
                            visible_pages.append(j)
                            break
        return visible_pages

    def get_visible_pages_list(self):
        """Get list of visible (non-deleted) page indices in original order"""
        visible_pages = []
        if hasattr(self.ui.pdfView, 'page_widgets'):
            for i, widget in enumerate(self.ui.pdfView.page_widgets):
                if not widget.isHidden():
                    visible_pages.append(i)
        return visible_pages

    def update_recent_files_menu(self):
        """Update recent files in menu"""
        if not hasattr(self.ui, 'menuFile'):
            return

        # --- remove previous recent-file actions, separator, and clear action
        to_remove = []
        for act in self.ui.menuFile.actions():
            name = act.objectName() or ""
            if name.startswith('recent_file_') or name in ('recent_files_separator', 'actionClearRecents'):
                to_remove.append(act)
        for act in to_remove:
            self.ui.menuFile.removeAction(act)
            act.deleteLater()

        # --- add fresh recent files
        recent_files = settings_manager.get_recent_files()
        if not recent_files:
            return

        # insert after "Open" (if it exists)
        open_action = getattr(self.ui, 'actionOpen', None)
        if not open_action:
            return

        # insert a separator after Open
        separator = self.ui.menuFile.insertSeparator(open_action)
        separator.setObjectName('recent_files_separator')

        # insert recent items BEFORE the separator so they appear just after Open
        # (Qt inserts the new action *before* the 'before' action)
        for i, file_path in enumerate(recent_files[:10]):
            text = f"&{i + 1} {os.path.basename(file_path)}"
            act = QAction(text, self.ui.menuFile)
            act.setObjectName(f'recent_file_{i}')
            act.setToolTip(file_path)
            # capture path at definition time
            act.triggered.connect(lambda checked=False, p=file_path: self.open_recent_file(p))
            self.ui.menuFile.insertAction(separator, act)

        # add "Clear Recent Files" right after the recent list (still before the same separator)
        clear_action = QAction("Clear Recent Files", self.ui.menuFile)
        clear_action.setObjectName('actionClearRecents')
        clear_action.triggered.connect(self.clear_recent_files)
        self.ui.menuFile.insertAction(separator, clear_action)

    def open_recent_file(self, file_path):
        """Open a recent file"""
        if os.path.exists(file_path):
            self.main_window.load_document(file_path)
        else:
            QMessageBox.warning(
                self.main_window,
                "File Not Found",
                f"The file '{file_path}' no longer exists."
            )
            settings_manager.remove_recent_file(file_path)
            self.update_recent_files_menu()

    def clear_recent_files(self):
        """Clear recent files list"""
        settings_manager.clear_recent_files()
        self.update_recent_files_menu()

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

        last_dir = settings_manager.get_last_directory()
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Open PDF",
            last_dir,
            "PDF Files (*.pdf)"
        )

        if file_path:
            settings_manager.save_last_directory(os.path.dirname(file_path))
            settings_manager.add_recent_file(file_path)
            self.update_recent_files_menu()
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

        return True

    def save_file_as(self) -> bool:
        """Save changes to a new file"""
        last_dir = settings_manager.get_last_directory()
        file_path, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Save PDF As",
            last_dir,
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return False

        settings_manager.save_last_directory(os.path.dirname(file_path))

        if hasattr(self.ui.pdfView, 'save_changes'):
            success = self.ui.pdfView.save_changes(file_path)
            if success:
                self.main_window.current_document_path = file_path
                filename = os.path.basename(file_path)
                self.main_window.setWindowTitle(f"PDF Editor - {filename}")
                self.main_window.is_document_modified = False
                self.main_window.update_ui_state()
                settings_manager.add_recent_file(file_path)
                self.update_recent_files_menu()
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

    def print_document(self):
        """Print the current PDF document using visible pages only"""
        # Check if there is an open PDF file
        if not hasattr(self.ui.pdfView, 'document') or not self.ui.pdfView.document:
            QMessageBox.information(
                self.main_window,
                "Warning",
                "Please open a PDF file first."
            )
            return

        try:
            # Set up printer in high resolution
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self.main_window)

            # Show print dialog and exit if user cancels
            if dialog.exec() != QPrintDialog.Accepted:
                return

            # Get visible pages in their layout order
            visible_pages = self.get_visible_pages_in_layout_order()
            if not visible_pages:
                QMessageBox.warning(
                    self.main_window,
                    "No Pages to Print",
                    "No visible pages to print."
                )
                return

            # Get document
            pdf_document = self.ui.pdfView.document
            painter = QPainter()

            # Start the painter with the printer
            if not painter.begin(printer):
                QMessageBox.critical(
                    self.main_window,
                    "Print Error",
                    "Cannot open print device."
                )
                return

            # Create progress dialog
            progress = QProgressDialog("Printing...", "Cancel", 0, len(visible_pages), self.main_window)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            # Print only visible pages in their current layout order
            for idx, page_num in enumerate(visible_pages):
                # Update progress
                progress.setValue(idx)
                QApplication.processEvents()

                if progress.wasCanceled():
                    break

                if idx > 0:
                    printer.newPage()

                page = pdf_document[page_num]

                # Apply any rotations
                rotation = 0
                if hasattr(self.ui.pdfView, 'page_rotations'):
                    rotation = self.ui.pdfView.page_rotations.get(page_num, 0)

                if rotation != 0:
                    page.set_rotation(rotation)

                # Determine page orientation
                pdf_rect = page.rect
                is_landscape = pdf_rect.width > pdf_rect.height

                # Set printer page layout if needed
                page_layout = printer.pageLayout()
                if is_landscape and (page_layout.orientation() == QPageLayout.Portrait):
                    new_layout = QPageLayout(
                        page_layout.pageSize(),
                        QPageLayout.Landscape,
                        page_layout.margins()
                    )
                    printer.setPageLayout(new_layout)

                # Render page at high resolution
                zoom_factor = 2  # Adjust for print quality
                matrix = fitz.Matrix(zoom_factor, zoom_factor)
                pix = page.get_pixmap(matrix=matrix)

                image = QImage(pix.samples, pix.width, pix.height,
                              pix.stride, QImage.Format_RGB888)

                # Get the page rect from printer in device pixels
                paint_rect = printer.pageRect(QPrinter.DevicePixel)

                # Scale image to fit the page while maintaining aspect ratio
                scaled_image = image.scaled(
                    paint_rect.size().toSize(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                # Center the image on the page
                target_size = scaled_image.size()
                x = paint_rect.x() + (paint_rect.width() - target_size.width()) // 2
                y = paint_rect.y() + (paint_rect.height() - target_size.height()) // 2

                target_rect = paint_rect.adjusted(
                    x - paint_rect.x(),
                    y - paint_rect.y(),
                    -(paint_rect.width() - (x - paint_rect.x()) - target_size.width()),
                    -(paint_rect.height() - (y - paint_rect.y()) - target_size.height())
                )

                painter.drawImage(target_rect, scaled_image)

            # End the painter
            painter.end()
            progress.close()

            QMessageBox.information(
                self.main_window,
                "Print Complete",
                f"Successfully printed {len(visible_pages)} pages."
            )

        except Exception as e:
            QMessageBox.critical(
                self.main_window,
                "Print Error",
                f"Error occurred while printing: {str(e)}"
            )

    # Navigation operations with proper page numbering
    def previous_page(self):
        """Go to previous visible page in layout order"""
        if not hasattr(self.ui.pdfView, 'get_current_page'):
            return

        current_original = self.ui.pdfView.get_current_page()
        # convert original -> layout index
        current_layout = self.ui.pdfView.layout_index_for_original(current_original)
        visible_pages = self.get_visible_pages_in_layout_order()

        if visible_pages is None or current_layout is None:
            return

        if current_layout in visible_pages:
            idx = visible_pages.index(current_layout)
            if idx > 0:
                prev_layout = visible_pages[idx - 1]
                self.ui.pdfView.go_to_page(prev_layout)

    def next_page(self):
        """Go to next visible page in layout order"""
        if not hasattr(self.ui.pdfView, 'get_current_page'):
            return

        current_original = self.ui.pdfView.get_current_page()
        current_layout = self.ui.pdfView.layout_index_for_original(current_original)
        visible_pages = self.get_visible_pages_in_layout_order()

        if visible_pages is None or current_layout is None:
            return

        if current_layout in visible_pages:
            idx = visible_pages.index(current_layout)
            if idx < len(visible_pages) - 1:
                next_layout = visible_pages[idx + 1]
                self.ui.pdfView.go_to_page(next_layout)

    def jump_to_first_page(self):
        """Jump to first visible page in layout order"""
        visible_pages = self.get_visible_pages_in_layout_order()
        if visible_pages and hasattr(self.ui.pdfView, 'go_to_page'):
            self.ui.pdfView.go_to_page(visible_pages[0])

    def jump_to_last_page(self):
        """Jump to last visible page in layout order"""
        visible_pages = self.get_visible_pages_in_layout_order()
        if visible_pages and hasattr(self.ui.pdfView, 'go_to_page'):
            self.ui.pdfView.go_to_page(visible_pages[-1])

    # Page manipulation operations
    def delete_current_page(self):
        """Delete the current page with proper numbering update"""
        if hasattr(self.ui.pdfView, 'delete_current_page'):
            success = self.ui.pdfView.delete_current_page()
            if success:
                self.main_window.on_document_modified(True)
                self.main_window.update_page_info()

                # Update thumbnail - hide the thumbnail for this page
                current_page = self.ui.pdfView.get_current_page()
                if hasattr(self.ui.thumbnailList, 'hide_page_thumbnail'):
                    self.ui.thumbnailList.hide_page_thumbnail(current_page)

                # Update all thumbnail labels to reflect new display numbering
                if hasattr(self.ui.thumbnailList, 'update_all_thumbnail_labels'):
                    self.ui.thumbnailList.update_all_thumbnail_labels()

    def move_page_up(self):
        """Move current page up with proper numbering update"""
        if hasattr(self.ui.pdfView, 'move_page_up'):
            success = self.ui.pdfView.move_page_up()
            if success:
                self.main_window.on_document_modified(True)
                self.main_window.update_page_info()

                # Update thumbnail order and labels
                if hasattr(self.ui.thumbnailList, 'update_thumbnails_order'):
                    self.ui.thumbnailList.update_thumbnails_order()
                if hasattr(self.ui.thumbnailList, 'update_all_thumbnail_labels'):
                    self.ui.thumbnailList.update_all_thumbnail_labels()

    def move_page_down(self):
        """Move current page down with proper numbering update"""
        if hasattr(self.ui.pdfView, 'move_page_down'):
            success = self.ui.pdfView.move_page_down()
            if success:
                self.main_window.on_document_modified(True)
                self.main_window.update_page_info()

                # Update thumbnail order and labels
                if hasattr(self.ui.thumbnailList, 'update_thumbnails_order'):
                    self.ui.thumbnailList.update_thumbnails_order()
                if hasattr(self.ui.thumbnailList, 'update_all_thumbnail_labels'):
                    self.ui.thumbnailList.update_all_thumbnail_labels()

    def rotate_page_clockwise(self):
        """Rotate current page clockwise with thumbnail update"""
        if hasattr(self.ui.pdfView, 'rotate_page_clockwise'):
            success = self.ui.pdfView.rotate_page_clockwise()
            if success:
                self.main_window.on_document_modified(True)

                # Update thumbnail
                current_page = self.ui.pdfView.get_current_page()
                if hasattr(self.ui.thumbnailList, 'rotate_page_thumbnail'):
                    self.ui.thumbnailList.rotate_page_thumbnail(current_page, 90)

    def rotate_page_counterclockwise(self):
        """Rotate current page counterclockwise with thumbnail update"""
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

            # Update splitter sizes when toggling panel
            if hasattr(self.ui, 'splitter'):
                if not is_visible:  # Panel is being shown
                    # Restore panel width from settings or use default
                    _, panel_width, _ = settings_manager.load_panel_state()
                    min_panel_width = 150
                    max_panel_width = 300
                    constrained_width = max(min_panel_width, min(panel_width, max_panel_width))

                    tab_buttons_width = 25
                    pdf_view_width = max(400, self.main_window.width() - tab_buttons_width - constrained_width - 25)

                    self.ui.splitter.setSizes([tab_buttons_width, constrained_width, pdf_view_width])
                else:  # Panel is being hidden
                    # Give all space to PDF view
                    self.ui.splitter.setSizes([25, 0, self.main_window.width() - 25])
