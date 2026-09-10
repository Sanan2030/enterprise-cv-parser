from app.normalization.date_normalizer import DateNormalizer
from app.parsing.education_parser import EducationParser
from app.parsing.entity_extractor import EntityExtractor


def test_ocr_short_date_range():
    assert DateNormalizer.normalize_span("01.05-23-01.08.23") == ("2023-05-01", "2023-08-01", False)
    assert DateNormalizer.normalize("31.02.23") is None


def test_subject_not_swallowed_into_year_range(block):
    result = EducationParser().parse(
        [
            block("BAKU ENGINEERING", 10),
            block("UNIVERSITY", 25),
            block("Information Tecnology", 45),
            block("2022-2026", 65),
        ]
    )[0]
    assert result.institution == "BAKU ENGINEERING UNIVERSITY"
    assert result.degree is None
    assert result.field_of_study == "Information Technology"
    assert (result.start_date, result.end_date) == ("2022", "2026")


def test_labeled_github_username_without_invented_linkedin():
    result = EntityExtractor.extract_contact_info("GitHub: Sanan2030_\nLinkedIn: Sanan Nabizada", [])
    assert result["github"] == "https://github.com/Sanan2030"
    assert result["linkedin"] is None
