import hashlib
from contextlib import contextmanager
from pathlib import Path

import httpx
import pymupdf as fitz
import pytest

from app.core.config import settings
from app.core.exceptions import OCRError
from app.extraction import serverless_ocr


def image_pdf():
    with fitz.open() as source, fitz.open() as scanned:
        page = source.new_page()
        for index, line in enumerate(
            [
                "Alex Morgan",
                "alex@example.org",
                "SUMMARY",
                "Python developer building reliable software services.",
            ]
        ):
            page.insert_text((60, 80 + index * 40), line, fontsize=18)
        image = page.get_pixmap(dpi=150).tobytes("png")
        target = scanned.new_page()
        target.insert_image(target.rect, stream=image)
        return scanned.tobytes()


def test_native_ocr_reads_raster_pdf(client, monkeypatch):
    directory = Path("/usr/share/tesseract-ocr/5/tessdata")
    if not (directory / "eng.traineddata").is_file():
        pytest.skip("Real OCR smoke test requires the English Tesseract model")
    monkeypatch.setattr(settings, "IS_VERCEL", True)
    monkeypatch.setattr(serverless_ocr, "english_model_directory", lambda: directory)
    response = client.post("/api/extract-cv", files={"file": ("scan.pdf", image_pdf(), "application/pdf")})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["metadata"]["pdfType"] == "ocr"
    assert data["contactInformation"]["email"] == "alex@example.org"


def test_vercel_invalid_pdf_returns_json(client, monkeypatch):
    monkeypatch.setattr(settings, "IS_VERCEL", True)
    response = client.post("/api/extract-cv", files={"file": ("bad.pdf", b"broken", "application/pdf")})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"]["code"] == "invalid_pdf"


def test_blank_pdf_returns_json(client, monkeypatch):
    monkeypatch.setattr(settings, "IS_VERCEL", True)
    with fitz.open() as doc:
        doc.new_page()
        payload = doc.tobytes()
    response = client.post("/api/extract-cv", files={"file": ("blank.pdf", payload, "application/pdf")})
    assert response.status_code == 422
    assert "No readable text" in response.json()["detail"]["message"]


def test_model_failure_returns_readable_json(client, monkeypatch):
    monkeypatch.setattr(settings, "IS_VERCEL", True)

    def unavailable():
        raise OCRError("OCR model could not be loaded.")

    monkeypatch.setattr(serverless_ocr, "english_model_directory", unavailable)
    response = client.post("/api/extract-cv", files={"file": ("scan.pdf", image_pdf(), "application/pdf")})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ocr_unavailable"


def test_model_download_validated_and_cached(monkeypatch, tmp_path):
    payload = b"synthetic model bytes"
    monkeypatch.setattr(serverless_ocr.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(serverless_ocr, "MODEL_SHA256", hashlib.sha256(payload).hexdigest())
    calls = []

    @contextmanager
    def stream(*args, **kwargs):
        calls.append(args)
        yield httpx.Response(200, content=payload, request=httpx.Request("GET", serverless_ocr.MODEL_URL))

    monkeypatch.setattr(serverless_ocr.httpx, "stream", stream)
    directory = serverless_ocr.english_model_directory()
    assert (directory / "eng.traineddata").read_bytes() == payload
    assert serverless_ocr.english_model_directory() == directory
    assert len(calls) == 1


def test_model_checksum_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(serverless_ocr.tempfile, "gettempdir", lambda: str(tmp_path))

    @contextmanager
    def stream(*args, **kwargs):
        yield httpx.Response(
            200, content=b"corrupted", request=httpx.Request("GET", serverless_ocr.MODEL_URL)
        )

    monkeypatch.setattr(serverless_ocr.httpx, "stream", stream)
    with pytest.raises(OCRError, match="integrity"):
        serverless_ocr.english_model_directory()
