def deleted_create_placeholder_widgets(self, limit: Optional[int] = None):
    """Create lightweight placeholder PageWidget instances with dynamic loading support."""
    print(f"Creating placeholder widgets, limit: {limit}")

    # Clear existing widgets first
    while self.pages_layout.count():
        item = self.pages_layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()

    # self.page_widgets = []

    # Determine how many placeholders to create
    total_pages = len(self.pages_info)
    if limit is not None:
        pages_to_create = min(limit, total_pages)
    else:
        pages_to_create = total_pages

    print(f"Creating {pages_to_create} placeholder widgets out of {total_pages} total pages")

    for i in range(pages_to_create):
        page_info = self.pages_info[i]

        page_widget = PageWidget(
            page_info,
            i,
            self.page_widgets[-1:][0] if i > 0 else None,
            None,
            zoom=self.zoom_level)
        # Connect overlay change signal
        try:
            page_widget.overlay.annotation_changed.connect(
                lambda pw=page_widget, orig=page_info.page_num: self._save_vector_immediate(pw, orig)
            )
        except Exception as e:
            print(f"[PDFViewer] create_placeholder_widgets: connect failed for orig {page_info.page_num}: {e}")

        self.page_widgets.append(page_widget)
        self.pages_layout.addWidget(page_widget, 0, Qt.AlignmentFlag.AlignCenter)

    print(f"Created {len(self.page_widgets)} placeholder widgets")
    # Update container size based on ALL pages (not just created ones)
    # self.update_container_full_size()

    # Force layout update
    self.pages_container.adjustSize()
    self.pages_container.updateGeometry()
    self.update()

def deleted_create_page_placeholder(self, page_info: PageInfo):
    """
    Create a lightweight placeholder widget for a page.
    Prefer PageWidget from drawing_overlay if available; otherwise fallback to QLabel shim.
    The returned widget provides:
      - base_pixmap attribute (None or QPixmap)
      - set_base_pixmap(pixmap) method
      - clear_base(emit=False) method
      - base_label QLabel attribute for showing "Страница N\nЗагрузка..."
    """
    try:
        # Try to create the real PageWidget (preferred)
        widget = PageWidget(self.pages_container)
        # Ensure expected attributes exist (defensive)
        if not hasattr(widget, "base_pixmap"):
            widget.base_pixmap = None

        # Provide set_base_pixmap if missing (some PageWidget implementations differ)
        if not hasattr(widget, "set_base_pixmap"):
            def _set_base(pixmap):
                try:
                    widget.setPixmap(pixmap)
                except Exception:
                    pass
                widget.base_pixmap = pixmap

            widget.set_base_pixmap = _set_base

        # Provide clear_base if missing
        if not hasattr(widget, "clear_base"):
            def _clear_base(emit: bool = True):
                try:
                    widget.setPixmap(QPixmap())
                except Exception:
                    pass
                widget.base_pixmap = None

            widget.clear_base = _clear_base

        # Ensure there's a base_label we can update
        if not hasattr(widget, "base_label"):
            lbl = QLabel(widget)
            lbl.setAlignment(Qt.AlignCenter)
            widget.base_label = lbl
        # Set placeholder text
        try:
            display_num = (page_info.page_num + 1)
            widget.base_label.setText(f"Страница {display_num}\nЗагрузка...")
        except Exception:
            pass

        # Size the widget to expected display size
        display_size = self._calculate_display_size(page_info)
        try:
            widget.setMinimumSize(display_size)
            widget.setMaximumSize(display_size)
        except Exception:
            pass

        return widget

    except Exception as e:
        # Fallback lightweight QLabel shim if PageWidget creation fails
        lbl = QLabel(self.pages_container)
        lbl.setAlignment(Qt.AlignCenter)
        display_num = (page_info.page_num + 1)
        lbl.setText(f"Страница {display_num}\nЗагрузка...")
        # attach shim attributes used elsewhere
        lbl.base_pixmap = None

        def _set_base(pixmap):
            try:
                lbl.setPixmap(pixmap)
            except Exception:
                pass
            lbl.base_pixmap = pixmap

        def _clear_base(emit: bool = False):
            try:
                lbl.setPixmap(QPixmap())
            except Exception:
                pass
            lbl.base_pixmap = None

        lbl.set_base_pixmap = _set_base
        lbl.clear_base = _clear_base
        lbl.base_label = lbl  # point to itself so code accessing base_label works

        display_size = self._calculate_display_size(page_info)
        lbl.setMinimumSize(display_size)
        lbl.setMaximumSize(display_size)

        print(
            f"[PDFViewer] Warning: using QLabel fallback for page {page_info.page_num} because PageWidget init failed: {e}")
        return lbl

def delete_load_more_placeholders(self):
    """Load more placeholder widgets when scrolling near the end"""
    current_count = len(self.page_widgets)
    total_pages = len(self.pages_info)

    if current_count >= total_pages:
        return  # All pages already loaded

    # Calculate how many more to load (batch size)
    batch_size = min(self.visible_page_limit,
                     total_pages - self.page_widgets[-1:][0].layout_index)  # Load 20 more or whatever remains

    current_page = self.get_current_pageInfo_index()

    batch_size = current_page - self.page_widgets[-1:][0].layout_index if current_page > self.page_widgets[-1:][
        0].layout_index else batch_size

    print(f"Loading {batch_size} more placeholders ({current_count} -> {current_count + batch_size})")

    start_index = self.page_widgets[-1:][0].layout_index + 1
    end_index = start_index + batch_size

    for i in range(start_index, end_index):
        if i >= len(self.pages_info):
            break

        page_info = self.pages_info[i]

        prevPW = self.page_widgets[-1:][0] if i > 0 else None

        if prevPW is not None and prevPW.next is not None:
            page_widget = prevPW.next
        else:
            page_widget = PageWidget(
                page_info,
                i,
                prevPW,
                None,
                zoom=self.zoom_level)

        # Connect overlay change signal
        try:
            page_widget.overlay.annotation_changed.connect(
                lambda pw=page_widget, orig=page_info.page_num: self._save_vector_immediate(pw, orig)
            )
        except Exception as e:
            print(f"[PDFViewer] load_more_placeholders: connect failed for orig {page_info.page_num}: {e}")

        self.page_widgets.append(page_widget)
        self.pages_layout.addWidget(page_widget, 0, Qt.AlignCenter)

    print(f"Current indexPage: {self.get_current_pageInfo_index()}. "
          f"First indexPage: {self.page_widgets[0].layout_index}."
          f"Count pages prev current page: {self.get_current_pageInfo_index() - self.page_widgets[0].layout_index}.")
    count_first_pages = self.get_current_pageInfo_index() - self.page_widgets[0].layout_index
    if count_first_pages > self.visible_page_limit * 2:
        print(f"Count before {len(self.page_widgets)}")
        self.delete_placeholders(count_first_pages - self.visible_page_limit * 2, 0)

        print(f"Count after {len(self.page_widgets)}")

    # Update container size to account for new widgets
    # self.update_container_full_size()

    print(f"Loaded {batch_size} more placeholders, total: {len(self.page_widgets)}")

def delete_restore_first_placeholders(self, count):
    try:

        old_scroll = self.verticalScrollBar().value()

        total_height = 0
        spacing = self.pages_layout.spacing()

        countDeleted = 0
        for i in range(count):
            insertWidget = self.page_widgets[0].prev
            if insertWidget is None:
                continue

            display_size = insertWidget.calculate_display_size()
            total_height += display_size.height()
            total_height += spacing

            self.page_widgets.insert(0, insertWidget)
            self.pages_layout.insertWidget(0, insertWidget, 0, Qt.AlignCenter)
            countDeleted += 1

        margins = self.pages_layout.contentsMargins()
        total_height += margins.top()

        print(f"Restored first {countDeleted} PageWidgets")

        # self.verticalScrollBar().setValue(old_scroll + total_height)

        self.pages_layout.removeItem(self.main_spacer)
        if self.page_widgets[0].layout_index > 0:
            total_height = self.main_spacer.minimumSize().height() - total_height
            self.main_spacer = QSpacerItem(0, total_height, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.pages_layout.insertSpacerItem(0, self.main_spacer)

        # self.update_container_full_size()

        print(f"{len(self.page_widgets) - self.visible_page_limit * 2}")

        countDeleted = len(self.page_widgets) - self.visible_page_limit * 2 if countDeleted > len(
            self.page_widgets) - self.visible_page_limit * 2 else countDeleted

        self.delete_placeholders(countDeleted, 1)

    except Exception as e:
        print(e)
        return

def delete_delete_placeholders(self, count, type_delete: int):
    try:
        # 0 - start, 1 - end

        deleted_arr = self.page_widgets[:count] if type_delete == 0 else self.page_widgets[-count:]

        old_scroll = self.verticalScrollBar().value()

        total_height = 0
        spacing = self.pages_layout.spacing()

        # Add margins

        for item in deleted_arr:
            display_size = item.calculate_display_size()
            total_height += display_size.height()
            total_height += spacing
            self.pages_layout.removeWidget(item)
            # item.deleteLater()
            self.page_widgets.remove(item)

        margins = self.pages_layout.contentsMargins()
        total_height += margins.top()

        print(f"Deleted {'first' if type_delete == 0 else 'last'} {count} pages.")

        if type_delete == 0:
            # self.verticalScrollBar().setValue(old_scroll-total_height)

            self.pages_layout.removeItem(self.main_spacer)
            total_height += self.main_spacer.minimumSize().height()
            print(f"Insert Spacer {total_height} height. Current scroll: {self.verticalScrollBar().value()}")
            self.main_spacer = QSpacerItem(0, total_height, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.pages_layout.insertSpacerItem(0, self.main_spacer)

        # self.update_container_full_size()

    except Exception as e:
        print(e)
        return
