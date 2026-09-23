import pytest

from app.extraction.hyperlink_extractor import Hyperlink
from app.normalization.phone_normalizer import PhoneNormalizer
from app.normalization.url_normalizer import URLNormalizer
from app.parsing.entity_extractor import EntityExtractor
from app.parsing.skill_extractor import SkillExtractor
from app.schemas.resume import ResumeParsedSchema
from app.services.resume_parser import ResumeParserService


def test_full_phone_and_email():
    result = EntityExtractor.extract_contact_info("alex@example.org +994 50 123 45 67", [])
    assert result["phone"] == "+994501234567"
    assert result["email"] == "alex@example.org"


def test_date_not_phone():
    assert EntityExtractor.extract_contact_info("2018 - 2022", [])["phone"] is None


def test_annotation_email():
    result = EntityExtractor.extract_contact_info("", [Hyperlink("mailto:alex@example.org", 1, (0, 0, 1, 1))])
    assert result["email"] == "alex@example.org"


def test_social_host_boundary():
    result = EntityExtractor.extract_contact_info("https://github.com.evil.org/profile", [])
    assert result["github"] is None


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "https://user:pwd@example.com",
        "https://example.com:bad",
        "https://exa mple.com",
    ],
)
def test_url_rejected(value):
    assert URLNormalizer.normalize(value) is None


def test_url_normalized():
    assert URLNormalizer.normalize("github.com/example-user") == "https://github.com/example-user"


def test_invalid_phone():
    assert PhoneNormalizer.normalize("123") is None


def test_skills_punctuation_and_no_inference():
    skills = SkillExtractor().extract_skills("Python, C++; C#; Spring Boot; JavaScript.")
    names = {s.name.lower() for s in skills.programming_languages}
    assert {"python", "c++", "c#", "javascript"} <= names
    assert "java" not in names


def test_unknown_explicit_skill():
    result = SkillExtractor().extract_skills("CustomTool", "CustomTool")
    assert result.other_skills[0].name == "CustomTool"


def test_end_to_end_nested_schema(pdf_bytes):
    result = ResumeParserService().parse_pdf(pdf_bytes, "resume.pdf")
    restored = ResumeParsedSchema.model_validate_json(result.model_dump_json())
    assert restored.personal_information.full_name.value == "Alex Morgan"
    assert restored.personal_information.email.provenance.page == 1
    assert restored.work_experience[0].company == "Example Systems"
    assert restored.work_experience[0].start_date == "2022-01"
    assert restored.work_experience[0].current_position
    assert restored.education[0].institution == "Example University"
    assert restored.education[0].start_date == "2018"
    assert restored.languages[0].cefr_level == "C1"
    assert restored.certifications and restored.projects and restored.raw_sections


def test_no_fake_name(block):
    blocks = [block("Summary"), block("Python Developer")]
    assert EntityExtractor().extract(blocks, blocks, []).full_name is None


from app.parsing.gender_detector import detect_gender, normalize_explicit_gender


@pytest.mark.parametrize(
    ("full_name", "expected"),
    [
        ("Leyla Məmmədova", "female"),
        ("Sənan Nəbiyev", "male"),
        ("Aygül Hüseynli", "female"),
        ("Murad Əliyev", "male"),
        ("Aysel Məmməd qızı", "female"),
        ("Tural Məmməd oğlu", "male"),
    ],
)
def test_gender_detector_name_rules(full_name, expected):
    prediction = detect_gender(full_name)
    assert prediction["gender"] == expected
    assert 0.8 <= prediction["confidence"] <= 1.0
    assert prediction["reason"]


@pytest.mark.parametrize("full_name", ["Arzu Məmmədzadə", "Xəyal Əliyev", "Dəniz Hüseynli", "Tərlan Quliyev"])
def test_gender_detector_ambiguous_first_names_do_not_guess_without_context(full_name):
    prediction = detect_gender(full_name)
    assert prediction["gender"] == "unknown"
    assert prediction["confidence"] <= 0.25


def test_gender_detector_ambiguous_name_uses_military_context():
    prediction = detect_gender("Arzu Məmmədzadə", "2019-2020 Hərbi xidmət")
    assert prediction["gender"] == "male"
    assert prediction["confidence"] >= 0.7


def test_gender_detector_ambiguous_name_uses_female_context():
    prediction = detect_gender("Arzu Məmmədzadə", "Arzu xanım layihənin rəhbəri olmuşdur.")
    assert prediction["gender"] == "female"
    assert prediction["confidence"] >= 0.7


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Kişi", "male"), ("Male", "male"), ("Qadın", "female"), ("Женский", "female")],
)
def test_explicit_gender_normalization(raw, expected):
    prediction = normalize_explicit_gender(raw)
    assert prediction["gender"] == expected
    assert prediction["confidence"] == 0.99


def test_gender_detector_unknown_for_missing_name():
    assert detect_gender(None) == {
        "gender": "unknown",
        "confidence": 0.0,
        "reason": "Full name is missing.",
    }
