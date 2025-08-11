import sys
from PySide6.QtWidgets import (QMainWindow, QApplication, QFileDialog, QMessageBox, 
                              QToolBar, QStatusBar, QDockWidget, QListWidget, QSpinBox,
                              QComboBox, QLabel)
from PySide6.QtGui import QIcon, QActionGroup, QAction
from PySide6.QtCore import Qt, QSize
# from PyPDF2 import PdfReader, PdfWriter
from pathlib import Path

class PDFEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.pdf_document = None
        self.current_page = 0
        self.zoom_level = 100
        
        self.setWindowTitle("PDF Editor")
        self.setGeometry(100, 100, 1024, 768)
        
        self.create_actions()
        self.create_menus()
        self.create_toolbars()
        self.create_statusbar()
        self.create_side_panel()
        
        # Central widget for PDF view (placeholder for now)
        self.pdf_view = QLabel("PDF content will be displayed here", self)
        self.pdf_view.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.pdf_view)
        
    def create_actions(self):
        # File actions
        self.open_action = QAction(QIcon.fromTheme("document-open"), "&Open...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setStatusTip("Open PDF file")
        self.open_action.triggered.connect(self.open_file)
        
        self.save_action = QAction(QIcon.fromTheme("document-save"), "&Save", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setStatusTip("Save PDF file")
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_file)
        
        self.save_as_action = QAction(QIcon.fromTheme("document-save-as"), "Save &As...", self)
        self.save_as_action.setStatusTip("Save PDF file as...")
        self.save_as_action.setEnabled(False)
        self.save_as_action.triggered.connect(self.save_file_as)
        
        self.print_action = QAction(QIcon.fromTheme("document-print"), "&Print...", self)
        self.print_action.setShortcut("Ctrl+P")
        self.print_action.setStatusTip("Print PDF file")
        self.print_action.setEnabled(False)
        
        self.close_action = QAction(QIcon.fromTheme("window-close"), "&Close", self)
        self.close_action.setShortcut("Ctrl+W")
        self.close_action.setStatusTip("Close current PDF")
        self.close_action.setEnabled(False)
        self.close_action.triggered.connect(self.close_file)
        
        self.exit_action = QAction(QIcon.fromTheme("application-exit"), "E&xit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.setStatusTip("Exit application")
        self.exit_action.triggered.connect(self.close)
        
        # View actions
        self.zoom_in_action = QAction(QIcon.fromTheme("zoom-in"), "Zoom &In", self)
        self.zoom_in_action.setShortcut("Ctrl++")
        self.zoom_in_action.setStatusTip("Zoom in")
        self.zoom_in_action.triggered.connect(self.zoom_in)
        
        self.zoom_out_action = QAction(QIcon.fromTheme("zoom-out"), "Zoom &Out", self)
        self.zoom_out_action.setShortcut("Ctrl+-")
        self.zoom_out_action.setStatusTip("Zoom out")
        self.zoom_out_action.triggered.connect(self.zoom_out)
        
        self.rotate_cw_action = QAction(QIcon.fromTheme("object-rotate-right"), "Rotate &Right", self)
        self.rotate_cw_action.setStatusTip("Rotate clockwise")
        
        self.rotate_ccw_action = QAction(QIcon.fromTheme("object-rotate-left"), "Rotate &Left", self)
        self.rotate_ccw_action.setStatusTip("Rotate counter-clockwise")
        
        self.prev_page_action = QAction(QIcon.fromTheme("go-previous"), "Previous Page", self)
        self.prev_page_action.setShortcut("PgUp")
        self.prev_page_action.setStatusTip("Go to previous page")
        self.prev_page_action.triggered.connect(self.prev_page)
        
        self.next_page_action = QAction(QIcon.fromTheme("go-next"), "Next Page", self)
        self.next_page_action.setShortcut("PgDown")
        self.next_page_action.setStatusTip("Go to next page")
        self.next_page_action.triggered.connect(self.next_page)
        
        # Edit actions
        self.delete_page_action = QAction(QIcon.fromTheme("edit-delete"), "Delete Page", self)
        self.delete_page_action.setStatusTip("Delete current page")
        self.delete_page_action.setEnabled(False)
        
        self.move_page_up_action = QAction(QIcon.fromTheme("go-up"), "Move Page Up", self)
        self.move_page_up_action.setStatusTip("Move current page up")
        self.move_page_up_action.setEnabled(False)
        
        self.move_page_down_action = QAction(QIcon.fromTheme("go-down"), "Move Page Down", self)
        self.move_page_down_action.setStatusTip("Move current page down")
        self.move_page_down_action.setEnabled(False)
        
        # Help actions
        self.about_action = QAction("&About", self)
        self.about_action.setStatusTip("Show about dialog")
        self.about_action.triggered.connect(self.about)
        
        self.settings_action = QAction("&Settings", self)
        self.settings_action.setStatusTip("Open settings dialog")
        
    def create_menus(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.print_action)
        file_menu.addAction(self.close_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addSeparator()
        view_menu.addAction(self.rotate_cw_action)
        view_menu.addAction(self.rotate_ccw_action)
        view_menu.addSeparator()
        view_menu.addAction(self.prev_page_action)
        view_menu.addAction(self.next_page_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.about_action)
        help_menu.addAction(self.settings_action)
    
    def create_toolbars(self):
        # Main toolbar
        self.main_toolbar = QToolBar("Main Toolbar", self)
        self.main_toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self.main_toolbar)
        
        # File section
        self.main_toolbar.addAction(self.open_action)
        self.main_toolbar.addAction(self.save_action)
        self.main_toolbar.addAction(self.print_action)
        self.main_toolbar.addAction(self.close_action)
        self.main_toolbar.addSeparator()
        
        # Navigation section
        self.main_toolbar.addAction(self.prev_page_action)
        
        self.page_spinbox = QSpinBox(self)
        self.page_spinbox.setMinimum(1)
        self.page_spinbox.setMaximum(1)
        self.page_spinbox.setValue(1)
        self.page_spinbox.valueChanged.connect(self.go_to_page)
        self.main_toolbar.addWidget(self.page_spinbox)
        
        self.main_toolbar.addAction(self.next_page_action)
        self.main_toolbar.addSeparator()
        
        # Zoom section
        self.main_toolbar.addAction(self.zoom_in_action)
        
        self.zoom_combobox = QComboBox(self)
        self.zoom_combobox.addItems(["25%", "50%", "75%", "100%", "150%", "200%", "400%", "800%"])
        self.zoom_combobox.setCurrentText("100%")
        self.zoom_combobox.currentTextChanged.connect(self.zoom_changed)
        self.main_toolbar.addWidget(self.zoom_combobox)
        
        self.main_toolbar.addAction(self.zoom_out_action)
        self.main_toolbar.addSeparator()
        
        # Edit section
        self.main_toolbar.addAction(self.delete_page_action)
        self.main_toolbar.addAction(self.move_page_up_action)
        self.main_toolbar.addAction(self.move_page_down_action)
    
    def create_statusbar(self):
        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)
        
        # Page format label
        self.page_format_label = QLabel("Page: -")
        self.statusbar.addPermanentWidget(self.page_format_label)
        
        # Dimensions label (pixels)
        self.dimensions_px_label = QLabel("Dimensions: - px × - px")
        self.statusbar.addPermanentWidget(self.dimensions_px_label)
        
        # Dimensions label (mm)
        self.dimensions_mm_label = QLabel("- mm × - mm")
        self.statusbar.addPermanentWidget(self.dimensions_mm_label)
    
    def create_side_panel(self):
        # Thumbnail panel
        self.thumbnail_dock = QDockWidget("Pages", self)
        self.thumbnail_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        
        self.thumbnail_list = QListWidget(self.thumbnail_dock)
        self.thumbnail_list.itemClicked.connect(self.thumbnail_clicked)
        self.thumbnail_dock.setWidget(self.thumbnail_list)
        
        self.addDockWidget(Qt.LeftDockWidgetArea, self.thumbnail_dock)
        
        # Bookmarks panel (placeholder)
        self.bookmark_dock = QDockWidget("Bookmarks", self)
        self.bookmark_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.bookmark_list = QListWidget(self.bookmark_dock)
        self.bookmark_dock.setWidget(self.bookmark_list)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.bookmark_dock)
    
    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF File", "", "PDF Files (*.pdf)"
        )
        
        if file_path:
            try:
                self.current_file = file_path
                # self.pdf_document = PdfReader(file_path)
                #
                # # Update UI
                # self.page_spinbox.setMaximum(len(self.pdf_document.pages))
                self.update_thumbnails()
                self.update_page_info()
                
                # Enable actions
                self.save_action.setEnabled(True)
                self.save_as_action.setEnabled(True)
                self.print_action.setEnabled(True)
                self.close_action.setEnabled(True)
                self.delete_page_action.setEnabled(True)
                self.move_page_up_action.setEnabled(True)
                self.move_page_down_action.setEnabled(True)
                
                self.statusbar.showMessage(f"Opened: {Path(file_path).name}", 3000)
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open file:\n{str(e)}")
    
    def save_file(self):
        if self.current_file and self.pdf_document:
            try:
                # writer = PdfWriter()
                # for page in self.pdf_document.pages:
                #     writer.add_page(page)
                #
                # with open(self.current_file, 'wb') as f:
                #     writer.write(f)
                
                self.statusbar.showMessage(f"Saved: {Path(self.current_file).name}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{str(e)}")
    
    def save_file_as(self):
        if self.pdf_document:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save PDF File As", "", "PDF Files (*.pdf)"
            )
            
            if file_path:
                try:
                    # writer = PdfWriter()
                    # for page in self.pdf_document.pages:
                    #     writer.add_page(page)
                    #
                    # with open(file_path, 'wb') as f:
                    #     writer.write(f)
                    
                    self.current_file = file_path
                    self.statusbar.showMessage(f"Saved as: {Path(file_path).name}", 3000)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not save file:\n{str(e)}")
    
    def close_file(self):
        self.current_file = None
        self.pdf_document = None
        self.current_page = 0
        
        # Clear UI
        self.thumbnail_list.clear()
        self.page_spinbox.setMaximum(1)
        self.page_spinbox.setValue(1)
        self.pdf_view.setText("PDF content will be displayed here")
        
        # Update status bar
        self.page_format_label.setText("Page: -")
        self.dimensions_px_label.setText("Dimensions: - px × - px")
        self.dimensions_mm_label.setText("- mm × - mm")
        
        # Disable actions
        self.save_action.setEnabled(False)
        self.save_as_action.setEnabled(False)
        self.print_action.setEnabled(False)
        self.close_action.setEnabled(False)
        self.delete_page_action.setEnabled(False)
        self.move_page_up_action.setEnabled(False)
        self.move_page_down_action.setEnabled(False)
        
        self.statusbar.showMessage("File closed", 3000)
    
    def zoom_in(self):
        self.zoom_level = min(self.zoom_level + 10, 800)
        self.update_zoom()
    
    def zoom_out(self):
        self.zoom_level = max(self.zoom_level - 10, 25)
        self.update_zoom()
    
    def zoom_changed(self, text):
        self.zoom_level = int(text[:-1])
        self.update_zoom()
    
    def update_zoom(self):
        self.zoom_combobox.setCurrentText(f"{self.zoom_level}%")
        # Here you would update the actual PDF view zoom
        self.statusbar.showMessage(f"Zoom: {self.zoom_level}%", 2000)
    
    def prev_page(self):
        if self.pdf_document and self.current_page > 0:
            self.current_page -= 1
            self.page_spinbox.setValue(self.current_page + 1)
            self.update_page_info()
    
    def next_page(self):
        if self.pdf_document and self.current_page < len(self.pdf_document.pages) - 1:
            self.current_page += 1
            self.page_spinbox.setValue(self.current_page + 1)
            self.update_page_info()
    
    def go_to_page(self, page_num):
        if self.pdf_document and 1 <= page_num <= len(self.pdf_document.pages):
            self.current_page = page_num - 1
            self.update_page_info()
    
    def thumbnail_clicked(self, item):
        page_num = self.thumbnail_list.row(item)
        self.go_to_page(page_num + 1)
    
    def update_thumbnails(self):
        self.thumbnail_list.clear()
        if self.pdf_document:
            for i in range(len(self.pdf_document.pages)):
                self.thumbnail_list.addItem(f"Page {i+1}")
    
    def update_page_info(self):
        if self.pdf_document and 0 <= self.current_page < len(self.pdf_document.pages):
            page = self.pdf_document.pages[self.current_page]
            
            # Update page format (simplified)
            self.page_format_label.setText(f"Page: {self.current_page + 1}/{len(self.pdf_document.pages)}")
            
            # Update dimensions (placeholder values)
            self.dimensions_px_label.setText("Dimensions: 595 px × 842 px")
            self.dimensions_mm_label.setText("210 mm × 297 mm")
            
            # Update PDF view (placeholder)
            self.pdf_view.setText(f"Displaying page {self.current_page + 1} of {Path(self.current_file).name}")
    
    def about(self):
        QMessageBox.about(self, "About PDF Editor", 
                         "PDF Editor\nVersion 1.0\n\nA simple PDF editor built with PySide6")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = PDFEditor()
    editor.show()
    sys.exit(app.exec())
