"""Synthetic resume geometry: no personal CV data is committed."""

import pymupdf as fitz

from app.extraction.layout_engine import DocumentLayoutEngine, LayoutBlock
from app.parsing.entity_extractor import EntityExtractor
from app.parsing.language_skills import parse_languages
from app.parsing.skill_extractor import SkillExtractor
from app.services.dashboard_adapter import adapt_resume
from app.services.resume_parser import ResumeParserService


def test_wrapped_name_and_inline_nationality():
    blocks = [
        LayoutBlock((50, 20, 130, 58), "ALEX", 1, 28),
        LayoutBlock((50, 51, 190, 89), "MORGAN", 1, 28),
        LayoutBlock(
            (50, 100, 500, 112), "Nationality: Canada | LinkedIn: https://linkedin.com/in/example", 1, 9
        ),
    ]
    person = EntityExtractor().extract(blocks, blocks, [])
    assert person.full_name.value == "ALEX MORGAN"
    assert person.first_name.value == "ALEX"
    assert person.last_name.value == "MORGAN"
    assert person.nationality.value == "Canada"
    assert person.linkedin == "https://linkedin.com/in/example"


def test_spatial_language_levels_are_not_languages():
    blocks = [
        LayoutBlock((50, 10, 120, 22), "English", 1),
        LayoutBlock((330, 10, 400, 22), "Russian", 1),
        LayoutBlock((330, 35, 430, 47), "Intermediate", 1),
        LayoutBlock((50, 35, 160, 47), "Advanced (C1)", 1),
    ]
    entries = parse_languages(blocks)
    assert [(e.language, e.proficiency) for e in entries] == [
        ("English", "Advanced (C1)"),
        ("Russian", "Intermediate"),
    ]


def test_fragments_join_without_merging_bullet_columns():
    blocks = [
        LayoutBlock((50, 10, 56, 22), "•", 1, 10),
        LayoutBlock((56, 10, 75, 22), "SQL", 1, 10),
        LayoutBlock((80, 10, 130, 22), "(queries)", 1, 10),
        LayoutBlock((140, 10, 146, 22), "•", 1, 10),
        LayoutBlock((146, 10, 200, 22), "Teamwork", 1, 10),
    ]
    joined = DocumentLayoutEngine.join_line_fragments(blocks)
    assert [b.text for b in joined] == ["• SQL (queries)", "• Teamwork"]


def test_wrapped_skill_is_not_split_into_explanatory_words():
    text = "• SQL (writing complex queries, joins,\naggregations)\n• Azure\nDevOps"
    result = SkillExtractor().extract_skills(text, text)
    names = [s.name for category in type(result).model_fields for s in getattr(result, category)]
    assert "Azure DevOps" in names
    assert not any(word in names for word in ["queries", "joins", "aggregations)", "DevOps"])


def test_real_pdf_pipeline_keeps_right_aligned_education_dates():
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        for x, y, text, size in [
            (50, 50, "ALEX", 28),
            (50, 81, "MORGAN", 28),
            (50, 105, "alex@example.org", 10),
            (50, 125, "Nationality: Canada | LinkedIn: https://linkedin.com/in/example", 9),
            (50, 165, "EDUCATION", 12),
            (50, 190, "Example University", 10),
            (450, 190, "09/2022 - 01/2026", 9),
            (50, 210, "Bachelor of Science: Information Technology", 10),
            (50, 240, "Center of Communication", 10),
            (450, 240, "04/2024 - 07/2024", 9),
            (50, 260, "Project Manager", 10),
            (50, 300, "LANGUAGES", 12),
            (50, 325, "English", 10),
            (330, 325, "Russian", 10),
            (50, 350, "Advanced (C1)", 9),
            (330, 350, "Intermediate", 9),
        ]:
            page.insert_text((x, y), text, fontsize=size)
        payload = document.tobytes()
    result = adapt_resume(ResumeParserService().parse_pdf(payload, "example.pdf"), [])
    assert result.personalInformation.fullName == "ALEX MORGAN"
    assert result.personalInformation.nationality == "Canada"
    assert len(result.education) == 2
    assert result.education[0].startDate == "2022-09"
    assert result.education[0].fieldOfStudy == "Information Technology"
    assert result.education[1].endDate == "2024-07"
    assert len(result.languages) == 2
    assert result.languages[0].level == "Advanced (C1)"
