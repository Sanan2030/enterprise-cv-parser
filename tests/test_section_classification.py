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
