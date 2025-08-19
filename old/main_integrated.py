"""
Main entry point for the Integrated PDF Editor

This application combines:
- The UI design and layout from the original PDF editor
- The efficient PDF handling and manipulation from the integrated PDF viewer
- Enhanced performance with better memory management and caching

Usage:
    python main_integrated.py [pdf_file]
"""

import sys
import os
from argparse import ArgumentParser, RawTextHelpFormatter
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from integrated_main_window import IntegratedMainWindow
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Please ensure PySide6 and PyMuPDF (fitz) are installed:")
    print("pip install PySide6 PyMuPDF")
    sys.exit(1)


def main():
    argument_parser = ArgumentParser(description="AltPDF",
                                     formatter_class=RawTextHelpFormatter)
    argument_parser.add_argument("file", help="The file to open",
                                 nargs='?', type=str)
    options = argument_parser.parse_args()

    # Default theme should be Light (this is an exception for Windows 10 and 11 PySide6 GUIs)
    sys.argv += ['-platform', 'windows:darkmode=1']

    """Main entry point for the application"""
    # Create QApplication
    app = QApplication(sys.argv)

    # Set application properties
    app.setApplicationName("Integrated PDF Editor")
    app.setApplicationDisplayName("PDF Editor")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("PDF Tools")

    # Enable high DPI scaling
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Create and show main window
    try:
        window = IntegratedMainWindow()
        window.show()

        # If a file was passed as command line argument, open it
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
            if os.path.exists(file_path) and file_path.lower().endswith('.pdf'):
                window.load_document(file_path)
            else:
                print(f"Warning: File '{file_path}' not found or not a PDF file")

        # Start the event loop
        return app.exec()

    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
