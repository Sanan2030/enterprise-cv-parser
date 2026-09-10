import unicodedata
from dataclasses import dataclass
from io import BytesIO

import pdfplumber
import pymupdf as fitz

from app.core.config import settings
from app.core.exceptions import InvalidPDFException, SecurityException
from app.extraction.hyperlink_extractor import Hyperlink, HyperlinkExtractor
from app.extraction.layout_engine import DocumentLayoutEngine, LayoutBlock
from app.extraction.text_integrity import conflicting_cmap, has_unknown_characters, hidden_text, is_hidden
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
                # Native coordinates and image contents use the unrotated page space.
                # A display rotation must not rotate upright image text for OCR.
                if page.rotation:
                    page.set_rotation(0)
                links.extend(HyperlinkExtractor.extract(page))
                hidden = hidden_text(page)
                blocks = []
                for group in page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)[
                    "blocks"
                ]:
                    for line in group.get("lines", []):
                        spans = line["spans"]
                        text = "".join(s["text"] for s in spans).strip()
                        if is_hidden(text, tuple(line["bbox"]), hidden):
                            continue
                        text = unicodedata.normalize("NFC", text)
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
                if any(has_unknown_characters(block.text) for block in blocks):
                    if settings.IS_VERCEL:
                        from app.extraction.serverless_ocr import ServerlessOCREngine

                        region_engine = ServerlessOCREngine()
                    else:
                        from app.extraction.ocr_engine import OCREngine

                        region_engine = OCREngine()

                    repaired = []
                    for block in blocks:
                        if has_unknown_characters(block.text):
                            replacements = region_engine.extract_region(page, block.bbox)
                            if replacements:
                                repaired.extend(replacements)
                                warnings.append(
                                    "Unreadable font characters were recovered with regional OCR."
                                )
                                continue
                        repaired.append(block)
                    blocks = repaired
                suspect_mapping = conflicting_cmap(page)
                if PDFDetector.needs_ocr(page, blocks) or suspect_mapping:
                    if suspect_mapping:
                        warnings.append(
                            "Conflicting PDF character mappings detected; rendered text was read with OCR."
                        )
                    if settings.IS_VERCEL:
                        from app.extraction.serverless_ocr import ServerlessOCREngine

                        ocr_blocks, ocr_warnings = ServerlessOCREngine().extract_page(page)
                        warnings.extend(ocr_warnings)
                        if ocr_blocks:
                            blocks = ocr_blocks
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
                blocks = DocumentLayoutEngine.join_line_fragments(blocks)
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
