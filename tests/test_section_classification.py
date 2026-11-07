import pytest

from app.parsing.section_classifier import SectionClassifier


@pytest.mark.parametrize(
    "label,section",
    [
        ("WORK EXPERIENCE", "work_experience"),
        ("Təhsil", "education"),
        ("Eğitim:", "education"),
        ("Образование", "education"),
        ("SKILLS", "skills"),
        ("İş təcrübəsi", "work_experience"),
        ("Summary", "professional_summary"),
        ("PROFESSIONAL EXPERIENCE", "work_experience"),
        ("SKILLS & TOOLS", "skills"),
        ("Education and Certifications", "education"),
        ("EDUCATION & CERTIFICATIONS", "education"),
    ],
)
def test_headers(label, section):
    assert SectionClassifier.classify_block(label)[0] == section


@pytest.mark.parametrize(
    "text",
    [
        "Experienced Python engineer",
        "Education platform developer",
        "Summary of achievements delivered",
        "skills in Python",
        "",
        "Built projects for customers.",
    ],
)
def test_not_headers(text):
    assert SectionClassifier.classify_block(text)[0] is None


def test_inline_header(block):
    result = SectionClassifier().segment_document(
        [block("Skills: Python, C++"), block("Education"), block("Example University")]
    )
    assert result["skills"][0].text == "Python, C++"
    assert result["education"][0].text == "Example University"


def test_grouped_lines(block):
    result = SectionClassifier().segment_document([block("Summary\nBuilds systems.\nSkills\nPython")])
    assert result["professional_summary"][0].text == "Builds systems."
    assert result["skills"][0].text == "Python"


def test_combined_resume_headings_do_not_leak_into_summary(block):
    result = SectionClassifier().segment_document([
        block("PROFILE"), block("Builds digital products."),
        block("PROFESSIONAL EXPERIENCE"),
        block("Example Group | Business Analyst | Jul 2026 - Present"),
        block("SKILLS & TOOLS"), block("SQL, Jira"),
        block("EDUCATION & CERTIFICATIONS"),
        block("BSc, IT | Example University | 2022 - 2026"),
        block("Project Management Training | Example Center | 2024 - 2024"),
        block("Professional Scrum Product Owner (PSPO)"),
        block("LANGUAGES"), block("English - C1"),
    ])
    assert [b.text for b in result["professional_summary"]] == ["Builds digital products."]
    assert len(result["work_experience"]) == 1
    assert [b.text for b in result["skills"]] == ["SQL, Jira"]
    assert len(result["education"]) == 1
    assert len(result["certifications"]) == 2
    assert len(result["languages"]) == 1
