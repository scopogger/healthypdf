# PDF Editor - Optimized Memory Management

A modern PDF editor built with PySide6 that efficiently handles large PDF files by loading only visible pages to prevent memory issues and UI freezing.

## Key Features

- **Memory-Optimized PDF Viewing**: Only loads 2-3 visible pages at a time
- **Page Manipulation**: Delete, move, and rotate pages
- **Zoom Controls**: Full zoom functionality with fit-to-width/height options
- **Thumbnail Navigation**: Side panel with page thumbnails
- **Drag & Drop Support**: Open PDFs by dragging them into the application
- **Modern UI**: Complete menu system and toolbar

## Architecture Overview

The project is organized into logical components to eliminate code duplication and ensure maintainability:

### Core Files

1. **`main.py`** - Entry point script
   - Handles command-line arguments
   - Sets up the Qt application
   - Manages application lifecycle

2. **`main_window.py`** - Main window controller
   - Coordinates all UI components
   - Manages document state
   - Handles window-level events

3. **`actions_handler.py`** - Action management
   - Connects all UI actions to their handlers
   - Implements file operations, navigation, page manipulation
   - Centralizes all user interactions

4. **`pdf_viewer.py`** - Optimized PDF viewer ⚡
   - **CRITICAL**: Ultra-conservative memory management
   - Only loads 2-3 visible pages maximum
   - Aggressive page caching with immediate cleanup
   - Prevents UI freezing during PDF loading
   - Single-threaded rendering to avoid memory spikes

5. **`thumbnail_widget.py`** - Thumbnail sidebar
   - Lazy-loaded thumbnails
   - Click-to-navigate functionality
   - Memory-efficient caching

6. **`updated_ui_main_window.py`** - Complete UI setup
   - Full menu structure (File/Edit/View/Help)
   - Toolbar with all controls
   - Proper widget organization

7. **`zoom_selector.py`** - Zoom control widget
   - Dropdown with common zoom values
   - Input validation
   - Programmatic zoom control

## Memory Optimization Details

### The Problem
Loading large PDFs would cause:
- UI freezing for several minutes
- Excessive RAM usage (loading all pages)
- Poor user experience

### The Solution
The `PDFViewer` class implements aggressive memory management:

```python
# Ultra-conservative page cache (only 3 pages max)
self.page_cache = PageCache(max_size=3)

# Single thread to prevent memory spikes  
self.thread_pool.setMaxThreadCount(1)

# Only load 1-2 pages at most
if len(visible_pages) > 2:
    visible_pages = {current_center_page}
    # Add only one adjacent page
```

### Key Optimizations

1. **Placeholder Widgets**: Creates lightweight placeholders without rendering
2. **Viewport-Based Loading**: Only renders truly visible pages
3. **Immediate Cleanup**: Aggressively removes non-visible pages from memory
4. **Conservative Threading**: Single render thread prevents memory spikes
5. **Smart Caching**: LRU cache with maximum 3 pages
6. **Scroll Debouncing**: Delays rendering during scroll to prevent excessive updates

## Installation & Usage

### Requirements
```bash
pip install PySide6 PyMuPDF
```

### Running the Application
```bash
# Basic usage
python main.py

# Open specific PDF
python main.py document.pdf

# Debug mode
python main.py --debug document.pdf
```

### Drag & Drop
Simply drag PDF files into the application window to open them.

## UI Components

### Menu Structure
- **File**: Open, Save, Save As, Close, Exit
- **Edit**: Delete Page, Move Page Up/Down, Rotate Page
- **View**: Zoom In/Out, Fit to Width/Height, Rotate View, Toggle Panel
- **Help**: About

### Toolbar Features
- File operations (Open, Save)
- Page navigation (Previous/Next, First/Last)
- Direct page input
- Zoom controls with dropdown selector
- Page manipulation buttons

### Side Panel
- Page thumbnails with click navigation
- Thumbnail size controls
- Collapsible design

## Document Modification

The editor supports:
- **Page Deletion**: Mark pages as deleted (recoverable until save)
- **Page Reordering**: Move pages up/down in document
- **Page Rotation**: Rotate individual pages (90° increments)
- **Undo Support**: Changes only applied on save

### Save Behavior
- **Save**: Overwrites original file with changes
- **Save As**: Creates new file with modifications
- **Auto-prompt**: Warns before closing unsaved documents

## Performance Characteristics

### Memory Usage
- **Before**: Entire PDF loaded into RAM (could be GBs)
- **After**: Only 2-3 pages in memory (~10-50MB typical)

### Loading Time
- **Before**: 30+ seconds for large PDFs with UI freeze
- **After**: Instant loading with progressive page rendering

### Responsiveness
- Smooth scrolling with delayed rendering
- No UI blocking during page loads
- Immediate response to user interactions

## Code Organization Benefits

1. **No Duplication**: Single source of truth for each component
2. **Clear Separation**: UI, logic, and data handling separated
3. **Easy Testing**: Each component can be tested independently
4. **Maintainable**: Logical file structure with clear responsibilities
5. **Extensible**: Easy to add new features without affecting existing code

## Troubleshooting

### Common Issues

**PDF won't open:**
- Check file permissions
- Verify PDF is not corrupted
- Ensure file has .pdf extension

**UI freezing:**
- This should be eliminated with the new architecture
- If it occurs, check available RAM
- Try closing other applications

**Missing features:**
- Ensure all files are in the same directory
- Check PyMuPDF installation: `pip install --upgrade PyMuPDF`

### Debug Mode
Run with `--debug` flag for detailed console output:
```bash
python main.py --debug problematic_file.pdf
```

## Future Enhancements

Possible extensions:
- PDF merging/splitting
- Annotation support  
- Text extraction/search
- Batch processing
- Plugin architecture
- Multi-tab interface

## Technical Notes

- **Qt Framework**: PySide6 for cross-platform GUI
- **PDF Engine**: PyMuPDF (fitz) for PDF manipulation
- **Threading**: QThreadPool for non-blocking operations
- **Memory Management**: Aggressive garbage collection and cache limits
- **Architecture**: MVC-inspired separation of concerns