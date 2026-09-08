import pytest
from pydantic import ValidationError

from app.parsing.education_parser import EducationParser
from app.parsing.experience_parser import ExperienceParser
from app.schemas.resume import ResumeParsedSchema, WorkExperience
from app.services.resume_parser import ResumeParserService


def test_two_jobs_with_inline_dates(block):
    jobs = ExperienceParser().parse(
        [
            block("Engineer | Example One | 2022 - Present", 30),
            block("- Built services", 50),
            block("Developer | Example Two | 2020 - 2022", 90),
            block("- Maintained databases", 110),
        ]
    )
    assert len(jobs) == 2
    assert [job.company for job in jobs] == ["Example One", "Example Two"]
    assert jobs[0].responsibilities == ["Built services"]
    assert jobs[1].responsibilities == ["Maintained databases"]


def test_separate_bold_headers(block):
    jobs = ExperienceParser().parse(
        [
            block("Engineer", 30, bold=True),
            block("Example One", 44, bold=True),
            block("2022 - Present", 58),
            block("- Built software", 74),
            block("Developer", 100, bold=True),
            block("Example Two", 114, bold=True),
            block("2020 - 2022", 128),
            block("- Maintained software", 144),
        ]
    )
    assert len(jobs) == 2
    assert jobs[1].company == "Example Two"
    assert jobs[0].current_position


def test_bullet_never_becomes_company(block):
    job = ExperienceParser().parse([block("Engineer | 2022 - Present"), block("- Built systems", 70)])[0]
    assert job.company is None
    assert job.responsibilities == ["Built systems"]


def test_two_degrees(block):
    education = EducationParser().parse(
        [
            block("Example University | Master of Science | 2022 - 2024", 20),
            block("GPA: 3.8/4.0", 40),
            block("Other University | Bachelor of Science | 2018 - 2022", 90),
        ]
    )
    assert len(education) == 2
    assert education[0].gpa == "3.8/4.0"
    assert education[1].institution == "Other University"


@pytest.mark.parametrize(
    "values",
    [
        {"start_date": "2024-13"},
        {"start_date": "2023-02-29"},
        {"start_date": "2024", "end_date": "2020"},
        {"current_position": True, "end_date": "2024"},
        {"unknown_property": "x"},
    ],
)
def test_schema_rejects_incoherent_data(values):
    with pytest.raises(ValidationError):
        WorkExperience.model_validate(values)


def test_nested_unknown_field_rejected(pdf_bytes):
    data = ResumeParserService().parse_pdf(pdf_bytes, "resume.pdf").model_dump()
    data["personal_information"]["email"]["provenance"]["made_up"] = True
    with pytest.raises(ValidationError):
        ResumeParsedSchema.model_validate(data)
