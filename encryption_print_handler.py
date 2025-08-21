"""
Encryption and Print Handler - Handles PDF encryption/decryption and printing
"""
import os
import tempfile
from PySide6.QtWidgets import (
    QMessageBox, QInputDialog, QFileDialog, QDialog, QVBoxLayout,
    QHBoxLayout, QPushButton, QLineEdit, QLabel, QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QImage, QPageLayout
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
import fitz  # PyMuPDF


class PasswordDialog(QDialog):
    """Custom dialog for setting PDF password"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set PDF Password")
        self.setModal(True)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # User password
        user_layout = QHBoxLayout()
        user_layout.addWidget(QLabel("User Password:"))
        self.user_password = QLineEdit()
        self.user_password.setEchoMode(QLineEdit.Password)
        user_layout.addWidget(self.user_password)
        layout.addLayout(user_layout)
        
        # Owner password
        owner_layout = QHBoxLayout()
        owner_layout.addWidget(QLabel("Owner Password:"))
        self.owner_password = QLineEdit()
        self.owner_password.setEchoMode(QLineEdit.Password)
        owner_layout.addWidget(self.owner_password)
        layout.addLayout(owner_layout)
        
        # Same password checkbox
        self.same_password = QCheckBox("Use same password for both")
        self.same_password.setChecked(True)
        self.same_password.toggled.connect(self.on_same_password_toggled)
        layout.addWidget(self.same_password)
        
        # Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Initially disable owner password field
        self.owner_password.setEnabled(False)
        
    def on_same_password_toggled(self, checked):
        """Handle same password checkbox toggle"""
        self.owner_password.setEnabled(not checked)
        if checked:
            self.owner_password.setText("")
            
    def get_passwords(self):
        """Get the entered passwords"""
        user_pw = self.user_password.text()
        owner_pw = self.owner_password.text() if not self.same_password.isChecked() else user_pw
        return user_pw, owner_pw


class EncryptionPrintHandler:
    """Handler for PDF encryption, decryption, and printing operations"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def authenticate_document(self, file_path: str) -> tuple:
        """Handle password authentication for encrypted PDFs. Returns (doc, password)"""
        doc = fitz.open(file_path)
        
        if doc.needs_pass:
            password, ok = QInputDialog.getText(
                self.main_window, 
                "Password Required", 
                f"File {os.path.basename(file_path)} is password protected.\nEnter password:",
                QInputDialog.Password
            )
            
            if ok and password:
                if doc.authenticate(password):
                    return doc, password
                else:
                    QMessageBox.warning(self.main_window, "Authentication Failed", "Invalid password!")
                    doc.close()
                    return None, None
            else:
                doc.close()
                return None, None
        else:
            return doc, ""
    
    def encrypt_pdf(self, input_file: str, output_file: str = None):
        """Encrypt a PDF file with password"""
        try:
            if not output_file:
                output_file, _ = QFileDialog.getSaveFileName(
                    self.main_window,
                    "Save Encrypted PDF As",
                    input_file.replace('.pdf', '_encrypted.pdf'),
                    "PDF Files (*.pdf)"
                )
                
                if not output_file:
                    return False
            
            # Get passwords from user
            password_dialog = PasswordDialog(self.main_window)
            if password_dialog.exec() != QDialog.Accepted:
                return False
                
            user_pw, owner_pw = password_dialog.get_passwords()
            
            if not user_pw:
                QMessageBox.warning(self.main_window, "Error", "Password cannot be empty!")
                return False
            
            # Open and authenticate source document
            doc, _ = self.authenticate_document(input_file)
            if doc is None:
                return False
            
            # Set encryption
            encryption_dict = {
                "encryption": fitz.PDF_ENCRYPT_AES_256,
                "user_pw": user_pw,
                "owner_pw": owner_pw,
                "permissions": fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY | fitz.PDF_PERM_EDIT
            }
            
            # Save with encryption
            doc.save(output_file, **encryption_dict)
            doc.close()
            
            QMessageBox.information(self.main_window, "Success", f"PDF encrypted and saved to:\n{output_file}")
            return True
            
        except Exception as e:
            QMessageBox.critical(self.main_window, "Encryption Error", f"Failed to encrypt PDF:\n{str(e)}")
            return False
    
    def decrypt_pdf(self, input_file: str, output_file: str = None):
        """Decrypt a PDF file (remove password protection)"""
        try:
            if not output_file:
                output_file, _ = QFileDialog.getSaveFileName(
                    self.main_window,
                    "Save Decrypted PDF As",
                    input_file.replace('.pdf', '_decrypted.pdf'),
                    "PDF Files (*.pdf)"
                )
                
                if not output_file:
                    return False
            
            # Open and authenticate source document
            doc, password = self.authenticate_document(input_file)
            if doc is None:
                return False
            
            # Save without encryption
            doc.save(output_file)
            doc.close()
            
            QMessageBox.information(self.main_window, "Success", f"PDF decrypted and saved to:\n{output_file}")
            return True
            
        except Exception as e:
            QMessageBox.critical(self.main_window, "Decryption Error", f"Failed to decrypt PDF:\n{str(e)}")
            return False
    
    def print_pdf(self, file_path: str = None):
        """Print PDF document"""
        try:
            # Use current document if no file path provided
            if not file_path:
                if not hasattr(self.main_window, 'current_document_path') or not self.main_window.current_document_path:
                    QMessageBox.warning(self.main_window, "Warning", "Please open a PDF file first.")
                    return False
                file_path = self.main_window.current_document_path
            
            if not os.path.exists(file_path):
                QMessageBox.warning(self.main_window, "Error", f"File not found: {file_path}")
                return False
            
            # Set up printer in high resolution
            printer = QPrinter(QPrinter.HighResolution)
            printer.setPageSize(QPrinter.A4)
            
            dialog = QPrintDialog(printer, self.main_window)
            dialog.setWindowTitle("Print PDF")
            
            # Show print dialog and exit if user cancels
            if dialog.exec() != QPrintDialog.Accepted:
                return False
            
            # Open and authenticate PDF document
            doc, password = self.authenticate_document(file_path)
            if doc is None:
                return False
            
            painter = QPainter()
            
            # Start the painter with the printer
            if not painter.begin(printer):
                QMessageBox.critical(self.main_window, "Print Error", "Cannot open printer device.")
                doc.close()
                return False
            
            try:
                # Get print range
                from_page = dialog.fromPage() - 1 if dialog.fromPage() > 0 else 0
                to_page = dialog.toPage() - 1 if dialog.toPage() > 0 else len(doc) - 1
                
                # Ensure valid range
                from_page = max(0, from_page)
                to_page = min(len(doc) - 1, to_page)
                
                page_count = to_page - from_page + 1
                current_page = 0
                
                # Iterate through pages of the document
                for page_num in range(from_page, to_page + 1):
                    if current_page > 0:
                        if not printer.newPage():
                            QMessageBox.critical(self.main_window, "Print Error", "Failed to create new page.")
                            break
                    
                    page = doc[page_num]
                    
                    # Get page dimensions
                    pdf_rect = page.rect
                    is_landscape = pdf_rect.width > pdf_rect.height
                    
                    # Set page layout based on orientation
                    page_layout = printer.pageLayout()
                    if is_landscape and page_layout.orientation() == QPageLayout.Portrait:
                        page_layout.setOrientation(QPageLayout.Landscape)
                        printer.setPageLayout(page_layout)
                    elif not is_landscape and page_layout.orientation() == QPageLayout.Landscape:
                        page_layout.setOrientation(QPageLayout.Portrait)
                        printer.setPageLayout(page_layout)
                    
                    # Render page at high resolution for printing
                    zoom_factor = 2.0  # Higher quality for printing
                    matrix = fitz.Matrix(zoom_factor, zoom_factor)
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    
                    # Convert to QImage
                    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
                    
                    # Get the printable area
                    paint_rect = printer.pageRect(QPrinter.DevicePixel)
                    
                    # Scale image to fit the page while maintaining aspect ratio
                    scaled_image = image.scaled(
                        paint_rect.size().toSize(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    
                    # Center the image on the page
                    x = (paint_rect.width() - scaled_image.width()) // 2
                    y = (paint_rect.height() - scaled_image.height()) // 2
                    
                    # Draw the image
                    painter.drawImage(x, y, scaled_image)
                    
                    current_page += 1
                
                # End the painter
                painter.end()
                doc.close()
                
                QMessageBox.information(self.main_window, "Print Complete", f"Successfully printed {current_page} page(s).")
                return True
                
            except Exception as e:
                painter.end()
                doc.close()
                QMessageBox.critical(self.main_window, "Print Error", f"Error during printing:\n{str(e)}")
                return False
            
        except Exception as e:
            QMessageBox.critical(self.main_window, "Print Error", f"Failed to print PDF:\n{str(e)}")
            return False
    
    def get_pdf_info(self, file_path: str):
        """Get PDF document information"""
        try:
            doc, password = self.authenticate_document(file_path)
            if doc is None:
                return None
            
            metadata = doc.metadata
            info = {
                'title': metadata.get('title', 'N/A'),
                'author': metadata.get('author', 'N/A'),
                'subject': metadata.get('subject', 'N/A'),
                'creator': metadata.get('creator', 'N/A'),
                'producer': metadata.get('producer', 'N/A'),
                'created': metadata.get('creationDate', 'N/A'),
                'modified': metadata.get('modDate', 'N/A'),
                'pages': len(doc),
                'encrypted': doc.needs_pass,
                'file_size': os.path.getsize(file_path)
            }
            
            doc.close()
            return info
            
        except Exception as e:
            QMessageBox.critical(self.main_window, "Error", f"Failed to get PDF info:\n{str(e)}")
            return None
    
    def compress_pdf(self, input_file: str, output_file: str = None):
        """Compress PDF file to reduce size"""
        try:
            if not output_file:
                output_file, _ = QFileDialog.getSaveFileName(
                    self.main_window,
                    "Save Compressed PDF As",
                    input_file.replace('.pdf', '_compressed.pdf'),
                    "PDF Files (*.pdf)"
                )
                
                if not output_file:
                    return False
            
            # Open and authenticate source document
            doc, password = self.authenticate_document(input_file)
            if doc is None:
                return False
            
            # Get original file size
            original_size = os.path.getsize(input_file)
            
            # Save with compression options
            doc.save(
                output_file,
                garbage=4,  # Remove unused objects
                deflate=True,  # Compress streams
                clean=True,  # Clean up document structure
                pretty=False,  # Don't pretty-print (saves space)
                linear=False,  # Don't linearize (web optimization)
                no_new_id=True,  # Don't generate new document ID
                encryption=fitz.PDF_ENCRYPT_NONE  # Remove encryption if present
            )
            
            doc.close()
            
            # Check compression results
            if os.path.exists(output_file):
                new_size = os.path.getsize(output_file)
                compression_ratio = (1 - new_size / original_size) * 100 if original_size > 0 else 0
                
                QMessageBox.information(
                    self.main_window, 
                    "Compression Complete", 
                    f"PDF compressed successfully!\n\n"
                    f"Original size: {original_size:,} bytes\n"
                    f"Compressed size: {new_size:,} bytes\n"
                    f"Space saved: {compression_ratio:.1f}%\n\n"
                    f"Saved to: {output_file}"
                )
                return True
            else:
                QMessageBox.critical(self.main_window, "Compression Error", "Failed to create compressed file.")
                return False
                
        except Exception as e:
            QMessageBox.critical(self.main_window, "Compression Error", f"Failed to compress PDF:\n{str(e)}")
            return False