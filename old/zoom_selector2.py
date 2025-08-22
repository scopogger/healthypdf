"""
Zoom Selector Widget - Provides zoom control functionality
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QCompleter
from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtGui import QValidator


class ZoomValidator(QValidator):
    """Custom validator for zoom percentage input"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.min_zoom = 10
        self.max_zoom = 500
    
    def validate(self, input_str, pos):
        """Validate zoom input"""
        # Remove % if present
        clean_input = input_str.replace('%', '')
        
        if not clean_input:
            return (QValidator.Intermediate, input_str, pos)
        
        try:
            value = int(clean_input)
            if self.min_zoom <= value <= self.max_zoom:
                return (QValidator.Acceptable, input_str, pos)
            elif value < self.min_zoom or value > self.max_zoom:
                return (QValidator.Invalid, input_str, pos)
            else:
                return (QValidator.Intermediate, input_str, pos)
        except ValueError:
            return (QValidator.Invalid, input_str, pos)


class ZoomSelector(QWidget):
    """Zoom selector widget with dropdown and validation"""

    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.pdf_viewer = None
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the zoom selector UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Zoom input field
        self.zoom_input = QLineEdit()
        self.zoom_input.setFixedWidth(70)
        self.zoom_input.setText("100%")
        self.zoom_input.setAlignment(Qt.AlignCenter)
        
        # Set validator
        self.validator = ZoomValidator()
        self.zoom_input.setValidator(self.validator)
        
        # Setup completer with common zoom values
        zoom_values = [
            "25%", "50%", "75%", "100%", "125%", "150%", 
            "175%", "200%", "250%", "300%", "400%", "500%"
        ]
        completer = QCompleter(zoom_values)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.zoom_input.setCompleter(completer)
        
        # Connect signals
        self.zoom_input.editingFinished.connect(self._on_zoom_input_changed)
        self.zoom_input.returnPressed.connect(self._on_zoom_input_changed)
        
        layout.addWidget(self.zoom_input)
        
    def set_pdf_viewer(self, viewer):
        """Connect to PDF viewer"""
        self.pdf_viewer = viewer
        
    def _on_zoom_input_changed(self):
        """Handle zoom input change"""
        try:
            text = self.zoom_input.text().replace('%', '').strip()
            if not text:
                # Reset to current zoom if empty
                self._reset_to_current_zoom()
                return
                
            zoom_percent = int(text)
            
            # Clamp to valid range
            zoom_percent = max(10, min(500, zoom_percent))
            zoom_factor = zoom_percent / 100.0

            # Update display
            self.zoom_input.setText(f"{zoom_percent}%")
            
            # Apply zoom
            if self.pdf_viewer and hasattr(self.pdf_viewer, 'set_zoom'):
                self.pdf_viewer.set_zoom(zoom_factor)

            # Emit signal
            self.zoom_changed.emit(zoom_factor)
            
        except ValueError:
            # Reset to current zoom if invalid input
            self._reset_to_current_zoom()

    def _reset_to_current_zoom(self):
        """Reset input to current zoom level"""
        if self.pdf_viewer and hasattr(self.pdf_viewer, 'zoom_level'):
            current_zoom = int(self.pdf_viewer.zoom_level * 100)
            self.zoom_input.setText(f"{current_zoom}%")
        else:
            self.zoom_input.setText("100%")

    def set_zoom_value(self, zoom_factor: float):
        """Set zoom value programmatically"""
        zoom_percent = int(zoom_factor * 100)
        zoom_percent = max(10, min(500, zoom_percent))  # Clamp to valid range
        self.zoom_input.setText(f"{zoom_percent}%")

    def get_zoom_factor(self) -> float:
        """Get current zoom factor"""
        try:
            text = self.zoom_input.text().replace('%', '').strip()
            if text:
                return int(text) / 100.0
            return 1.0
        except ValueError:
            return 1.0

    def zoom_in(self):
        """Increase zoom by 25%"""
        current = self.get_zoom_factor()
        new_zoom = min(5.0, current * 1.25)
        self.set_zoom_value(new_zoom)
        self.zoom_changed.emit(new_zoom)

    def zoom_out(self):
        """Decrease zoom by 20%"""
        current = self.get_zoom_factor()
        new_zoom = max(0.1, current * 0.8)
        self.set_zoom_value(new_zoom)
        self.zoom_changed.emit(new_zoom)

    def reset_zoom(self):
        """Reset zoom to 100%"""
        self.set_zoom_value(1.0)
        self.zoom_changed.emit(1.0)