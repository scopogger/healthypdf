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
            print(f"Error open document: {e}")

    def auth(self, password: str):
        if not self.current_doc.authenticate(password):
            self.close()

    def get_page_count(self) -> int:
        return self.current_doc.page_count

    def get_page(self, num: int):
        try:
            # print(self.current_doc)
            return self.current_doc[num]
        except Exception as e:
            print(f"Error get page: {e}")

    def get_page_info(self, num_page: int) -> PageInfo:
        w, h = self.get_page_size(num_page)
        result = PageInfo(
            page_num=num_page,
            width=w,
            height=h,
            rotation=self.current_doc[num_page].rotation
        )
        return result

    # def render_page(self, page_num: int, zoom: float = 2.0, rotation: int = 0, format: str = "png", alpha: bool = False) -> bytes:
    #     worker_render = PageRenderWorker(page_num, zoom, None, rotation)

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

    def move_page(self, pno: int, to: int):
        self.current_doc.move_page(pno, to)

    def delete_page(self, pno: int):
        self.current_doc.delete_page(pno)

    def save(self, file_path: str, save_to_self: bool = True):
        if self.current_doc:
            self.current_doc.save(file_path, incremental=save_to_self, encryption=fitz.PDF_ENCRYPT_KEEP)

    def close(self):
        if self.current_doc:
            self.current_doc.close()
