import pymupdf as fitz

from app.extraction.layout_engine import LayoutBlock


class PDFDetector:
    @staticmethod
    def needs_ocr(page: fitz.Page, blocks: list[LayoutBlock]) -> bool:
        text = "".join(b.text for b in blocks)
        if text.count("\ufffd") > max(2, len(text) * 0.1):
            return True
        images = page.get_image_info()
        coverage = sum((fitz.Rect(i["bbox"]) & page.rect).get_area() for i in images) / page.rect.get_area()
        return (not text.strip() and bool(images)) or (len(text.strip()) < 80 and coverage > 0.4)
