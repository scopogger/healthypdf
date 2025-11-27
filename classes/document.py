from dataclasses import dataclass
import fitz  # PyMuPDF
from fitz import Page


@dataclass
class PageInfo:
    """Information about a PDF page"""
    page_num: int  # original document page index
    width: float  # Store as float for precision
    height: float  # Store as float for precision
    rotation: int = 0


class Document:
    def __init__(self, file_path: str = None):
        self.file_path = file_path
        try:
            self.current_doc = fitz.open(file_path)
        except Exception as e:
            print(f"Error opening document: {e}")

    def auth(self, password: str):
        if not self.current_doc.authenticate(password):
            self.close()

    def get_page_count(self) -> int:
        return self.current_doc.page_count

    def get_page(self, num: int):
        try:
            return self.current_doc[num]
        except Exception as e:
            print(f"Error getting page: {e}")

    def get_page_info(self, num_page: int) -> PageInfo:
        w, h = self.get_page_size(num_page)
        result = PageInfo(
            page_num=num_page,
            width=w,
            height=h,
        )
        return result

    def get_page_size(self, num_page: int) -> tuple:
        if not 0 <= num_page < self.current_doc.page_count:
            raise IndexError(f'Page number {num_page} is out of range [0, {self.current_doc.page_count - 1}]')

        page = self.current_doc[num_page]
        rect = page.rect
        return rect.width, rect.height

    def need_auth(self) -> bool:
        return self.current_doc.needs_pass

    def new_page(self, in_width: float, in_height: float) -> Page:
        if self.current_doc:
            return self.current_doc.new_page(width=in_width, height=in_height)

    def save(self, file_path: str):
        if self.current_doc:
            self.current_doc.save(file_path)

    def close(self):
        if self.current_doc:
            self.current_doc.close()
