import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from app.extraction.layout_engine import LayoutBlock
from app.main import app


@pytest.fixture
def block():
    def make(text, y=50, x=40, width=220, bold=False, page=1):
        return LayoutBlock((x, y, x + width, y + 12), text, page, 12, bold)

    return make


@pytest.fixture
def pdf_bytes():
    with fitz.open() as doc:
        page = doc.new_page()
        lines = [
            "Alex Morgan",
            "alex@example.org",
            "+994 50 123 45 67",
            "Summary",
            "Python backend developer building reliable software systems.",
            "Experience",
            "Backend Developer | Example Systems | Jan 2022 - Present",
            "- Built API services using Python and FastAPI.",
            "Education",
            "Example University | Bachelor of Science | 2018 - 2022",
            "Skills",
            "Python, SQL, C++, FastAPI, Docker",
            "Languages",
            "English - C1",
            "Certifications",
            "Cloud Engineering Certificate",
            "Projects",
            "Resume Parser",
        ]
        for i, text in enumerate(lines):
            page.insert_text((40, 45 + i * 25), text, fontsize=18 if i == 0 else 11)
        page.insert_link(
            {
                "kind": fitz.LINK_URI,
                "from": fitz.Rect(40, 30, 170, 48),
                "uri": "https://github.com/example-user",
            }
        )
        return doc.tobytes()


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client
