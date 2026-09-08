import tempfile
from pathlib import Path

from pydantic import SecretStr

from app.core.config import settings


def test_health(client):
    assert client.get("/api/v1/health").json()["status"] == "healthy"


def test_real_parse_worker(client, pdf_bytes):
    before = set(Path(tempfile.gettempdir()).glob("cv-parser-*"))
    response = client.post(
        "/api/v1/resume/parse", files={"file": ("resume.PDF", pdf_bytes, "application/pdf")}
    )
    assert response.status_code == 200, response.text
    assert response.json()["personal_information"]["email"]["value"] == "alex@example.org"
    assert set(Path(tempfile.gettempdir()).glob("cv-parser-*")) == before


def test_invalid_pdf(client):
    before = set(Path(tempfile.gettempdir()).glob("cv-parser-*"))
    response = client.post(
        "/api/v1/resume/parse", files={"file": ("resume.pdf", b"wrong", "application/pdf")}
    )
    assert response.status_code == 422
    assert set(Path(tempfile.gettempdir()).glob("cv-parser-*")) == before


def test_missing_file(client):
    assert client.post("/api/v1/resume/parse").status_code == 422


def test_wrong_type(client):
    assert (
        client.post("/api/v1/resume/parse", files={"file": ("resume.txt", b"text", "text/plain")}).status_code
        == 415
    )


def test_api_key(client, monkeypatch, pdf_bytes):
    monkeypatch.setattr(settings, "API_KEY", SecretStr("test-key"))
    assert (
        client.post(
            "/api/v1/resume/parse", files={"file": ("cv.pdf", pdf_bytes, "application/pdf")}
        ).status_code
        == 401
    )


def test_body_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    response = client.post("/api/v1/resume/parse", content=b"x" * (1024 * 1024 + 65537))
    assert response.status_code == 413


def test_ocr_child_timeout_cleanup(client, monkeypatch, pdf_bytes):
    monkeypatch.setattr(settings, "PARSE_TIMEOUT", 0.001)
    before = set(Path(tempfile.gettempdir()).glob("cv-parser-*"))
    response = client.post("/api/v1/resume/parse", files={"file": ("cv.pdf", pdf_bytes, "application/pdf")})
    assert response.status_code == 504
    assert set(Path(tempfile.gettempdir()).glob("cv-parser-*")) == before
