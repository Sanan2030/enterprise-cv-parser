from dataclasses import dataclass
from io import BytesIO

import pdfplumber
import pymupdf as fitz

from app.core.config import settings
from app.core.exceptions import InvalidPDFException, SecurityException
from app.extraction.hyperlink_extractor import Hyperlink, HyperlinkExtractor
from app.extraction.layout_engine import DocumentLayoutEngine, LayoutBlock
from app.ingestion.pdf_detector import PDFDetector
from app.ingestion.validator import PDFValidator


@dataclass
class ExtractionResult:
    blocks: list[LayoutBlock]
    links: list[Hyperlink]
    method: str
    page_count: int
    warnings: list[str]


class PDFTextExtractor:
    def extract(self, pdf_bytes: bytes, filename: str = "resume.pdf") -> ExtractionResult:
        page_count = PDFValidator.validate_file(pdf_bytes, filename)
        all_blocks, links, warnings = [], [], []
        methods = set()
        total_chars = 0
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                links.extend(HyperlinkExtractor.extract(page))
                blocks = []
                for group in page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)[
                    "blocks"
                ]:
                    for line in group.get("lines", []):
                        spans = line["spans"]
                        text = "".join(s["text"] for s in spans).strip()
                        if text:
                            blocks.append(
                                LayoutBlock(
                                    tuple(line["bbox"]),
                                    text,
                                    page.number + 1,
                                    max(s["size"] for s in spans),
                                    any(s["flags"] & 16 for s in spans),
                                )
                            )
                if not blocks and not page.get_image_info():
                    with pdfplumber.open(BytesIO(pdf_bytes)) as fallback:
                        for word in fallback.pages[page.number].extract_words():
                            blocks.append(
                                LayoutBlock(
                                    (word["x0"], word["top"], word["x1"], word["bottom"]),
                                    word["text"],
                                    page.number + 1,
                                    confidence=0.8,
                                )
                            )
                if PDFDetector.needs_ocr(page, blocks):
                    if settings.IS_VERCEL:
                        warnings.append(
                            f"Page {page.number + 1} needs OCR, which is unavailable on the Vercel deployment."
                        )
                    else:
                        from app.extraction.ocr_engine import OCREngine

                        ocr_blocks, ocr_warnings = OCREngine().extract_page(page)
                        warnings.extend(ocr_warnings)
                        if ocr_blocks:
                            blocks = ocr_blocks
                        else:
                            warnings.append(f"No OCR text on page {page.number + 1}.")
                if not blocks:
                    warnings.append(f"No text on page {page.number + 1}.")
                total_chars += sum(len(b.text) for b in blocks)
                if total_chars > settings.MAX_TEXT_CHARS:
                    raise SecurityException("Extracted text exceeds the character limit.")
                methods.update(b.method for b in blocks)
                all_blocks.extend(DocumentLayoutEngine.sort_reading_order(blocks, page.rect.width))
        if not all_blocks:
            raise InvalidPDFException("No readable text found in PDF.")
        return ExtractionResult(
            all_blocks,
            links,
            "hybrid" if len(methods) > 1 else next(iter(methods)),
            page_count,
            sorted(set(warnings)),
        )
