import gc
from typing import Optional, Dict, Set
from PySide6.QtGui import QPixmap
from collections import OrderedDict


class PageCache:
    """Ultra-aggressive LRU Cache - keys are original page numbers"""

    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self.cache: OrderedDict[int, QPixmap] = OrderedDict()

    def get(self, orig_page_num: int) -> Optional[QPixmap]:
        if orig_page_num in self.cache:
            self.cache.move_to_end(orig_page_num)
            return self.cache[orig_page_num]
        return None

    def put(self, orig_page_num: int, pixmap: QPixmap):
        if orig_page_num in self.cache:
            self.cache.move_to_end(orig_page_num)
        else:
            self.cache[orig_page_num] = pixmap
            while len(self.cache) > self.max_size:
                oldest = next(iter(self.cache))
                # Properly clean up the QPixmap before deletion
                oldest_pixmap = self.cache[oldest]
                if not oldest_pixmap.isNull():
                    oldest_pixmap = QPixmap()  # Explicitly clean
                del self.cache[oldest]
                gc.collect()

    def clean(self):
        """Thoroughly clear all cached pixmaps"""
        for key in list(self.cache.keys()):
            pixmap = self.cache[key]
            if not pixmap.isNull():
                pixmap = QPixmap()  # Explicitly clean
            del self.cache[key]
        self.cache.clear()
        gc.collect()
