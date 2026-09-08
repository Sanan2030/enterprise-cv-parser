from io import BytesIO
from unittest.mock import patch

import pymupdf as fitz
import pytest
from PIL import Image, ImageDraw

from app.core.config import settings
from app.core.exceptions import InvalidPDFException, OCRError, SecurityException
from app.extraction.layout_engine import DocumentLayoutEngine, LayoutBlock
from app.extraction.ocr_engine import OCREngine
from app.extraction.text_extractor import PDFTextExtractor
from app.ingestion.validator import PDFValidator


@pytest.mark.parametrize("content", [b"", b"not PDF", b"%PDF-1.7 fake %%EOF", b"%PDF-1.7 truncated"])
def test_reject_invalid(content):
    with pytest.raises(InvalidPDFException):
        PDFValidator.validate_file(content, "resume.pdf")


def test_valid_uppercase(pdf_bytes):
    assert PDFValidator.validate_file(pdf_bytes, "resume.PDF") == 1


def test_wrong_extension(pdf_bytes):
    with pytest.raises(InvalidPDFException):
        PDFValidator.validate_file(pdf_bytes, "resume.exe")


def test_size_limit():
    with pytest.raises(SecurityException):
        PDFValidator.validate_file(b"x" * (15 * 1024 * 1024 + 1), "resume.pdf")


def test_encrypted():
    with fitz.open() as doc:
        doc.new_page()
        content = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    with pytest.raises(InvalidPDFException, match="Encrypted"):
        PDFValidator.validate_file(content, "resume.pdf")


def test_page_limit(monkeypatch):
    monkeypatch.setattr(settings, "MAX_PAGES", 1)
    with fitz.open() as doc:
        doc.new_page()
        doc.new_page()
        content = doc.tobytes()
    with pytest.raises(SecurityException):
        PDFValidator.validate_file(content, "resume.pdf")


def test_native_links_and_line_boundaries(pdf_bytes):
    result = PDFTextExtractor().extract(pdf_bytes)
    assert result.method == "native"
    assert result.page_count == 1
    assert result.links[0].url == "https://github.com/example-user"
    assert any(b.text == "Education" for b in result.blocks)
    assert any("alex@example.org" in b.text for b in result.blocks)


def test_columns_preserve_all_blocks(block):
    blocks = [
        block("title", 10, width=520),
        block("L1", 50, width=150),
        block("R1", 50, x=250, width=280),
        block("L2", 80, width=150),
        block("R2", 80, x=250, width=280),
        block("footer", 140, width=520),
    ]
    result = DocumentLayoutEngine.sort_reading_order(blocks, 600)
    assert [b.text for b in result] == ["title", "L1", "L2", "R1", "R2", "footer"]
    assert len(result) == len(blocks)


def test_spanning_middle_band(block):
    blocks = [
        block("L1", 20, width=150),
        block("R1", 20, x=300),
        block("L2", 40, width=150),
        block("R2", 40, x=300),
        block("middle", 70, width=530),
        block("L3", 90, width=150),
        block("R3", 90, x=300),
        block("L4", 110, width=150),
        block("R4", 110, x=300),
    ]
    assert [b.text for b in DocumentLayoutEngine.sort_reading_order(blocks, 600)] == [
        "L1",
        "L2",
        "R1",
        "R2",
        "middle",
        "L3",
        "L4",
        "R3",
        "R4",
    ]


def scanned_page(doc):
    image = Image.new("RGB", (1200, 500), "white")
    ImageDraw.Draw(image).text((50, 100), "ALEX MORGAN Python developer", fill="black", font_size=55)
    data = BytesIO()
    image.save(data, format="PNG")
    image.close()
    page = doc.new_page(width=600, height=250)
    page.insert_image(page.rect, stream=data.getvalue())
    return page


def test_hybrid_page_routing(pdf_bytes):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        scanned_page(doc)
        data = doc.tobytes()
    blocks = [LayoutBlock((10, 10, 200, 40), "Scanned candidate details", 2, method="ocr")]
    with patch.object(OCREngine, "extract_page", return_value=(blocks, [])) as ocr:
        result = PDFTextExtractor().extract(data)
    assert ocr.call_count == 1
    assert result.method == "hybrid"
    assert result.page_count == 2
    assert any("alex@example.org" in b.text for b in result.blocks)


def test_blank_page_count(pdf_bytes):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        doc.new_page()
        data = doc.tobytes()
    result = PDFTextExtractor().extract(data)
    assert result.page_count == 2
    assert "No text on page 2." in result.warnings


def test_ocr_missing_language():
    with fitz.open() as doc:
        page = scanned_page(doc)
        with patch("pytesseract.get_languages", return_value=[]), pytest.raises(OCRError):
            OCREngine().extract_page(page)


def test_ocr_timeout():
    with fitz.open() as doc:
        page = scanned_page(doc)
        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            patch("pytesseract.image_to_data", side_effect=RuntimeError("timeout")),
            pytest.raises(OCRError),
        ):
            OCREngine().extract_page(page)


def test_real_tesseract(monkeypatch):
    monkeypatch.setattr(settings, "OCR_LANGUAGES", "eng")
    with fitz.open() as doc:
        page = scanned_page(doc)
        blocks, warnings = OCREngine().extract_page(page)
    assert "MORGAN" in " ".join(b.text for b in blocks).upper()
    assert not warnings
    assert all(0 <= b.x0 < b.x1 <= 600 for b in blocks)
