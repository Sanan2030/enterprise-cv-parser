"""Real generated PDFs exercising the ten previously observed failure cases."""

from pathlib import Path

import pymupdf as fitz
import pytest
import reportlab

from app.core.config import settings
from app.core.exceptions import OCRError
from app.extraction import serverless_ocr
from app.extraction.text_integrity import hidden_text
from app.services.dashboard_adapter import adapt_resume
from app.services.resume_parser import ResumeParserService
from scripts import stress_test


@pytest.fixture(scope="module")
def stress_corpus(tmp_path_factory):
    root = tmp_path_factory.mktemp("stress-regressions")
    # ReportLab's bundled font keeps fixture generation portable outside Linux.
    if not Path(stress_test.FONT).exists():
        stress_test.FONT = str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")
    cases = stress_test.generate(root)
    return root, {case["id"]: case for case in cases}


@pytest.mark.parametrize(
    "case_id",
    [
        "04_native_wrapped_name",
        "06_columns_reverse_columns",
        "07_columns_three_columns",
        "11_ocr_scan_rotated",
        "14_encoding_incorrect_cmap",
        "15_encoding_accented_missing_cmap",
        "16_encoding_unicode_decomposed",
        "17_headers_career_journey",
        "18_headers_professional_background",
        "19_headers_employment_record",
    ],
)
@pytest.mark.parametrize("vercel", [True, False])
def test_previously_failed_pdf(case_id, stress_corpus, monkeypatch, vercel):
    root, cases = stress_corpus
    monkeypatch.setattr(settings, "IS_VERCEL", vercel)
    monkeypatch.setattr(settings, "USE_LLM_FALLBACK", False)
    # Use the deployed model logic: actual OCR, not mocked results.
    case = cases[case_id]
    response = adapt_resume(ResumeParserService().parse_pdf((root / case["file"]).read_bytes(), "case.pdf"))
    data = response.model_dump()
    for path, expected in case["expected"].items():
        actual = stress_test.get_path(data, path)
        if isinstance(expected, dict):
            assert expected["contains"] in actual, path
        else:
            assert actual == expected, path


def test_background_before_text_does_not_hide_content():
    with fitz.open() as doc:
        page = doc.new_page()
        page.draw_rect(page.rect, fill=(1, 1, 1))
        page.insert_text((40, 50), "Alex Morgan")
        assert not hidden_text(page)


def test_regional_ocr_failure_is_controlled(monkeypatch):
    with fitz.open() as doc:
        page = doc.new_page()

        def broken(*args, **kwargs):
            raise RuntimeError("OCR failure")

        monkeypatch.setattr(fitz.Page, "get_pixmap", broken)
        with pytest.raises(OCRError, match="Regional PDF OCR failed"):
            serverless_ocr.ServerlessOCREngine().extract_region(page, (10, 10, 100, 50))
