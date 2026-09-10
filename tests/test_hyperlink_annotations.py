import pymupdf as fitz

from app.extraction.hyperlink_extractor import HyperlinkExtractor
from app.services.resume_parser import ResumeParserService


def linked_name_pdf() -> bytes:
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 50), "Alex Morgan", fontsize=18)
        page.insert_text((40, 75), "alex@example.org")
        page.insert_text((40, 100), "Summary")
        page.insert_text((40, 125), "Backend developer.")
        page.insert_link(
            {
                "kind": fitz.LINK_URI,
                "from": fitz.Rect(40, 30, 160, 55),
                "uri": "https://www.linkedin.com/in/alex-morgan/?trk=public_profile",
            }
        )
        return document.tobytes()


def test_link_annotation_fallback_when_high_level_links_are_missing(monkeypatch):
    with fitz.open(stream=linked_name_pdf(), filetype="pdf") as document:
        page = document[0]
        monkeypatch.setattr(page, "get_links", lambda: [])
        links = HyperlinkExtractor.extract(page)
    assert links[0].url == "https://www.linkedin.com/in/alex-morgan/?trk=public_profile"


def test_linked_name_populates_linkedin_without_visible_url():
    resume = ResumeParserService().parse_pdf(linked_name_pdf(), "linked-name.pdf")
    assert resume.personal_information.full_name.value == "Alex Morgan"
    assert (
        resume.personal_information.linkedin == "https://www.linkedin.com/in/alex-morgan/?trk=public_profile"
    )
