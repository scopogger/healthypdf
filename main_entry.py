#!/usr/bin/env python3
"""
PDF Editor - Main Entry Point
A modern PDF editor with page manipulation capabilities.
"""

import sys
import os
from argparse import ArgumentParser, RawTextHelpFormatter

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from main_window import MainWindow


def setup_application():
    """Setup QApplication with proper settings"""
    # Enable high DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    # Create application
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("PDF Editor")
    app.setApplicationDisplayName("PDF Editor")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("PDF Tools")
    app.setOrganizationDomain("pdftools.local")
    
    return app


def parse_arguments():
    """Parse command line arguments"""
    parser = ArgumentParser(
        description="PDF Editor - A modern PDF editor with page manipulation capabilities",
        formatter_class=RawTextHelpFormatter
    )
    parser.add_argument(
        "file", 
        help="PDF file to open on startup", 
        nargs='?', 
        type=str
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )
    
    return parser.parse_args()


def main():
    """Main entry point"""
    try:
        # Parse arguments
        args = parse_arguments()
        
        # Setup application
        app = setup_application()
        
        # Create main window
        main_window = MainWindow()
        
        # Show window
        main_window.show()
        
        # Load file if specified
        if args.file:
            if os.path.exists(args.file) and args.file.lower().endswith('.pdf'):
                main_window.load_document(args.file)
            else:
                print(f"Warning: File '{args.file}' not found or not a PDF file")
        
        # Start event loop
        return app.exec()
        
    except Exception as e:
        print(f"Fatal error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())