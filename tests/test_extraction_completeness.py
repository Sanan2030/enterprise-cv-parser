import pymupdf as fitz

from app.extraction.layout_engine import DocumentLayoutEngine
from app.parsing.education_parser import EducationParser
from app.parsing.experience_parser import ExperienceParser
from app.parsing.language_skills import parse_languages
from app.parsing.section_classifier import SectionClassifier
from app.services.dashboard_adapter import adapt_resume
from app.services.resume_parser import ResumeParserService


def test_full_schema_from_real_pdf():
    lines = [
        "Full Name: Alex Taylor Morgan",
        "DOB: 1990-05-21 | Gender: Female | Nationality: British",
        "Address: 12 Example Road, London",
        "alex@example.org | +994 50 123 45 67 | +994 55 123 45 67",
        "Portfolio: https://example.org/alex",
        "https://github.com/alex-example",
        "Experience",
        "Position: Software Engineer",
        "Company: Example Systems",
        "Start Date: Jan 2021",
        "End Date: Mar 2023",
        "Responsibilities: Built payment APIs.",
        "Education",
        "University: Example University",
        "Degree: Bachelor of Science",
        "Field of Study: Computer Science",
        "Start Date: Sep 2016",
        "End Date: Jun 2020",
        "GPA: 3.8/4.0",
        "Skills",
        "Python, SQL, Communication",
        "Languages",
        "English - C2",
        "Certifications",
        "Certificate: Cloud Developer",
        "Issuer: Example Academy",
        "Issue Date: Jan 2024",
        "Credential ID: ABC-123",
        "Projects",
        "Project: Payments API",
        "Description: Processes online payments.",
        "Technologies: Python, PostgreSQL",
        "Role: Backend Developer",
        "References",
        "Sam Reference | +994 70 123 45 67",
    ]
    with fitz.open() as doc:
        page = doc.new_page()
        for i, text in enumerate(lines):
            page.insert_text((35, 35 + 20 * i), text, fontsize=10)
        page.insert_link(
            {
                "kind": fitz.LINK_URI,
                "from": fitz.Rect(35, 20, 250, 36),
                "uri": "https://www.linkedin.com/in/alex-example/",
            }
        )
        data = doc.tobytes()
    result = adapt_resume(ResumeParserService().parse_pdf(data, "synthetic.pdf"))
    person = result.personalInformation
    assert (person.fullName, person.firstName, person.middleName, person.lastName) == (
        "Alex Taylor Morgan",
        "Alex",
        "Taylor",
        "Morgan",
    )
    assert (person.dateOfBirth, person.gender, person.nationality, person.address) == (
        "1990-05-21",
        "Female",
        "British",
        "12 Example Road, London",
    )
    contact = result.contactInformation
    assert contact.mobilePhone == "+994501234567"
    assert contact.alternativePhone == "+994551234567"
    assert contact.linkedIn.rstrip("/") == "https://www.linkedin.com/in/alex-example"
    assert contact.gitHub == "https://github.com/alex-example"
    assert contact.portfolio == "https://example.org/alex"
    job = result.experience[0]
    assert (job.company, job.position, job.startDate, job.endDate, job.duration) == (
        "Example Systems",
        "Software Engineer",
        "2021-01",
        "2023-03",
        "2 yrs 2 mos",
    )
    assert job.responsibilities == "Built payment APIs."
    edu = result.education[0]
    assert (edu.university, edu.degree, edu.fieldOfStudy, edu.gpa, edu.duration) == (
        "Example University",
        "Bachelor of Science",
        "Computer Science",
        "3.8/4.0",
        "3 yrs 9 mos",
    )
    assert "Python" in result.skills.technical
    assert "Communication" in result.skills.soft
    assert result.languages[0].level == "C2"
    cert = result.certifications[0]
    assert (cert.certificateName, cert.issuingOrganization, cert.issueDate, cert.credentialID) == (
        "Cloud Developer",
        "Example Academy",
        "2024-01",
        "ABC-123",
    )
    project = result.projects[0]
    assert (project.projectName, project.description, project.technologies, project.role) == (
        "Payments API",
        "Processes online payments.",
        "Python, PostgreSQL",
        "Backend Developer",
    )
    assert result.metadata.phones == 2


def test_azerbaijani_sections_and_wrapped_education(block):
    for heading, expected in [
        ("İŞ TƏCRÜBƏSİ", "work_experience"),
        ("DİLLƏR", "languages"),
        ("HAQQIMDA", "professional_summary"),
        ("REFERANSLAR", "references"),
        ("MARAQLAR", "interests"),
    ]:
        assert SectionClassifier.classify_block(heading)[0] == expected
    edu = EducationParser().parse(
        [
            block("Azerbaycan Texniki", 50),
            block("Universiteti", 65),
            block("Biotibbi Texnologiya", 80),
            block("Mühəndisliyi", 95),
            block("2016 - 2020", 110),
        ]
    )[0]
    assert edu.institution == "Azerbaycan Texniki Universiteti"
    assert edu.field_of_study == "Biotibbi Texnologiya Mühəndisliyi"
    languages = parse_languages(
        [
            block("İngiliscə", 50, width=65),
            block("B2", 50, x=160, width=15),
            block("Türkcə", 70, width=65),
            block("C2", 70, x=160, width=15),
        ]
    )
    assert [(entry.language, entry.cefr_level) for entry in languages] == [("İngiliscə", "B2"), ("Türkcə", "C2")]


def test_sidebar_sections_do_not_interrupt_main_column(block):
    blocks = [
        block("Alex Morgan", 20, x=200),
        block("Education", 80, width=120),
        block("Example University", 100, width=130),
        block("2016 - 2020", 150, width=120),
        block("Skills", 180, width=100),
        block("Python", 200, width=100),
        block("Summary", 70, x=210),
        block("Building software.", 95, x=210),
        block("Experience", 125, x=210),
        block("Developer | Example", 150, x=210),
        block("Jan 2021 - Present", 175, x=210),
    ]
    sections = SectionClassifier().segment_document(DocumentLayoutEngine.sort_reading_order(blocks, 600))
    assert [b.text for b in sections["education"]] == ["Example University", "2016 - 2020"]
    jobs = ExperienceParser().parse(sections["work_experience"])
    assert len(jobs) == 1 and jobs[0].start_date == "2021-01"


def test_multiple_labeled_jobs(block):
    lines = [
        "Position: Engineer",
        "Company: First Company",
        "Start Date: Jan 2021",
        "End Date: Jan 2022",
        "Responsibilities: Built APIs.",
        "Position: Analyst",
        "Company: Second Company",
        "Start Date: Feb 2022",
        "End Date: Present",
        "Responsibilities: Collected requirements.",
    ]
    jobs = ExperienceParser().parse([block(text, 30 + i * 15) for i, text in enumerate(lines)])
    assert len(jobs) == 2
    assert jobs[0].company == "First Company" and jobs[0].duration == "1 yr"
    assert jobs[1].company == "Second Company" and jobs[1].current_position
