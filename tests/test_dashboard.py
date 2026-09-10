import pymupdf as fitz

from app.core.config import settings
from app.extraction.table_extractor import TableExtractor
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_adapter import adapt_resume
from app.services.resume_parser import ResumeParserService


def test_dashboard_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PDF Intelligence Platform" in response.text
    assert "processUploadedFile" in response.text
    assert client.get("/index.html").text == response.text


def test_new_endpoint_real_pdf(client, pdf_bytes):
    response = client.post(
        "/api/extract-cv",
        files={"file": ("cv.pdf", pdf_bytes, "application/pdf")},
        headers={"Origin": "http://localhost:5500"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == "*"
    data = DashboardResponse.model_validate(response.json())
    assert data.personalInformation.fullName == "Alex Morgan"
    assert data.contactInformation.email == "alex@example.org"
    assert data.contactInformation.mobilePhone == "+994501234567"
    assert data.experience[0].company == "Example Systems"
    assert data.experience[0].duration
    assert data.experience[0].endDate == "Present"
    assert data.education[0].university == "Example University"
    assert "Python" in data.skills.technical
    assert data.metadata.pages == 1
    assert data.metadata.words > 0
    assert data.personalInformation.gender == ""
    assert not {"professionalInformation", "confidenceScores", "tables"} & response.json().keys()


def test_cors_preflight(client):
    response = client.options(
        "/api/extract-cv",
        headers={
            "Origin": "null",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


def test_cors_error_response(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    response = client.post(
        "/api/extract-cv", content=b"x" * (1024 * 1024 + 65537), headers={"Origin": "http://localhost:5500"}
    )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "*"


def test_config_no_secrets(client):
    data = client.get("/api/config").json()
    assert set(data) == {"llmEnabled", "apiKeyRequired", "maxUploadBytes"}
    assert data["llmEnabled"] is False


def test_missing_fields_not_invented(pdf_bytes):
    resume = ResumeParserService().parse_pdf(pdf_bytes, "cv.pdf")
    resume.personal_information.full_name = None
    resume.personal_information.email = None
    resume.personal_information.phone = None
    resume.work_experience = []
    response = adapt_resume(resume, [])
    assert response.personalInformation.fullName == ""
    assert response.experience == []


def make_table_pdf():
    with fitz.open() as doc:
        page = doc.new_page()
        for x in (40, 220, 400):
            page.draw_line((x, 80), (x, 200))
        for y in (80, 120, 160, 200):
            page.draw_line((40, y), (400, y))
        for row, values in enumerate([("Skill", "Level"), ("Python", "Advanced"), ("SQL", "Intermediate")]):
            for col, value in enumerate(values):
                page.insert_text((50 + col * 180, 105 + row * 40), value)
        return doc.tobytes()


def test_real_table_preserves_first_row():
    tables = TableExtractor.extract(make_table_pdf())
    assert len(tables) == 1
    assert tables[0].headers == ["Column 1", "Column 2"]
    assert tables[0].rows == [["Skill", "Level"], ["Python", "Advanced"], ["SQL", "Intermediate"]]


def test_real_table_api(client):
    response = client.post(
        "/api/extract-cv", files={"file": ("table.pdf", make_table_pdf(), "application/pdf")}
    )
    assert response.status_code == 200, response.text
    assert "tables" not in response.json()


def test_vercel_uses_in_process_native_parser(client, monkeypatch, pdf_bytes):
    monkeypatch.setattr(settings, "IS_VERCEL", True)
    response = client.post("/api/extract-cv", files={"file": ("cv.pdf", pdf_bytes, "application/pdf")})
    assert response.status_code == 200, response.text
    assert response.json()["personalInformation"]["fullName"] == "Alex Morgan"
