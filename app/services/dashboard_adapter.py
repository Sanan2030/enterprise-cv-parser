import re

import phonenumbers

from app.core.config import settings
from app.normalization.duration import calculate_duration
from app.parsing.entity_extractor import EMAIL_REGEX
from app.schemas.dashboard import (
    Certification,
    ContactInformation,
    DashboardResponse,
    Education,
    Experience,
    Language,
    Metadata,
    PersonalInformation,
    Project,
    Skills,
)
from app.schemas.resume import FieldWithMetadata, ResumeParsedSchema


def value(field: FieldWithMetadata | None) -> str:
    return field.value or "" if field else ""


def adapt_resume(resume: ResumeParsedSchema, tables: list | None = None) -> DashboardResponse:
    person = resume.personal_information
    text = "\n".join(p.source_text for group in resume.raw_sections.values() for p in group)
    contact_text = "\n".join(
        p.source_text for key in ("header", "personal_information") for p in resume.raw_sections.get(key, [])
    )

    def labeled(*labels: str) -> str:
        match = re.search(
            r"(?im)(?:^|[|;])\s*(?:" + "|".join(re.escape(label) for label in labels) + r")\s*:\s*([^\n|;]+)",
            contact_text,
        )
        return match[1].strip() if match else ""

    emails = set(EMAIL_REGEX.findall(contact_text))
    if value(person.email):
        emails.add(value(person.email))
    phones = list(
        dict.fromkeys(
            phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164)
            for m in phonenumbers.PhoneNumberMatcher(contact_text, settings.DEFAULT_PHONE_REGION)
        )
    )
    if value(person.phone) and value(person.phone) not in phones:
        phones.append(value(person.phone))
    all_skills = [
        skill for category in type(resume.skills).model_fields for skill in getattr(resume.skills, category)
    ]
    technical = list(dict.fromkeys(s.name for s in all_skills if s.category != "soft_skills"))
    soft = list(dict.fromkeys(s.name for s in resume.skills.soft_skills))

    return DashboardResponse(
        personalInformation=PersonalInformation(
            fullName=value(person.full_name),
            firstName=value(person.first_name),
            lastName=value(person.last_name),
            middleName=value(person.middle_name),
            dateOfBirth=value(person.date_of_birth),
            gender=value(person.gender),
            nationality=value(person.nationality) or labeled("nationality", "vətəndaşlıq"),
            maritalStatus=labeled("marital status", "ailə vəziyyəti"),
            address=value(person.location),
        ),
        contactInformation=ContactInformation(
            email=value(person.email),
            mobilePhone=value(person.phone),
            alternativePhone=value(person.alternative_phone),
            linkedIn=person.linkedin or "",
            gitHub=person.github or "",
            portfolio=person.portfolio or person.website or "",
        ),
        experience=[
            Experience(
                company=e.company or "",
                position=e.job_title or "",
                startDate=e.start_date or "",
                endDate="Present" if e.current_position else e.end_date or "",
                duration=calculate_duration(e.start_date, e.end_date, current=e.current_position),
                responsibilities="\n".join(e.responsibilities),
                location=e.location or "",
                employmentType=e.employment_type or "",
            )
            for e in resume.work_experience
        ],
        education=[
            Education(
                university=e.institution or "",
                degree=e.degree or "",
                fieldOfStudy=e.field_of_study or "",
                startDate=e.start_date or "",
                endDate=e.end_date or "",
                duration=calculate_duration(e.start_date, e.end_date),
                gpa=e.gpa or "",
            )
            for e in resume.education
        ],
        skills=Skills(technical=technical, soft=soft),
        languages=[
            Language(language=e.language, level=e.proficiency or e.cefr_level or "") for e in resume.languages
        ],
        certifications=[
            Certification(
                certificateName=e.certification_name or "",
                issuingOrganization=e.issuer or "",
                issueDate=e.issue_date or "",
                credentialID=e.credential_id or "",
            )
            for e in resume.certifications
        ],
        projects=[
            Project(
                projectName=e.project_name or "",
                description=e.description or "",
                technologies=", ".join(e.technologies),
                role=e.role or "",
            )
            for e in resume.projects
        ],
        summary=value(resume.professional_profile.professional_summary),
        metadata=Metadata(
            filename=resume.document.file_name,
            pages=resume.document.page_count,
            words=len(text.split()),
            emails=len(emails),
            phones=len(phones),
            pdfType=resume.quality.extraction_method,
            documentLanguage=resume.document.document_language.primary,
            processingTimeMs=resume.document.processing_time_ms,
            llmEnabled=settings.USE_LLM_FALLBACK,
            warnings=[
                w
                for w in resume.quality.warnings
                if "confidence" not in w.lower() and not w.startswith("spaCy NER model not configured")
            ],
        ),
    )
