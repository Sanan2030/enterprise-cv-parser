import re
from statistics import mean

import phonenumbers

from app.core.config import settings
from app.parsing.entity_extractor import EMAIL_REGEX
from app.schemas.dashboard import (
    Certification,
    ConfidenceScores,
    ContactInformation,
    DashboardResponse,
    Education,
    Experience,
    Language,
    Metadata,
    PersonalInformation,
    ProfessionalInformation,
    Project,
    Skills,
    Table,
)
from app.schemas.resume import FieldWithMetadata, ResumeParsedSchema


def value(field: FieldWithMetadata | None) -> str:
    return field.value or "" if field else ""


def score(field: FieldWithMetadata | None) -> float:
    return round(field.confidence * 100, 1) if field and field.value else 0


def adapt_resume(resume: ResumeParsedSchema, tables: list[Table]) -> DashboardResponse:
    person = resume.personal_information
    text = "\n".join(p.source_text for group in resume.raw_sections.values() for p in group)

    def labeled(*labels: str) -> str:
        match = re.search(
            r"(?im)(?:^|[|;])\s*(?:" + "|".join(re.escape(label) for label in labels) + r")\s*:\s*([^\n|;]+)",
            text,
        )
        return match[1].strip() if match else ""

    emails = set(EMAIL_REGEX.findall(text))
    if value(person.email):
        emails.add(value(person.email))
    phones = list(
        dict.fromkeys(
            phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164)
            for m in phonenumbers.PhoneNumberMatcher(text, settings.DEFAULT_PHONE_REGION)
        )
    )
    if value(person.phone) and value(person.phone) not in phones:
        phones.append(value(person.phone))
    current = next((job for job in resume.work_experience if job.current_position), None)
    all_skills = [
        skill for category in type(resume.skills).model_fields for skill in getattr(resume.skills, category)
    ]
    technical = list(dict.fromkeys(s.name for s in all_skills if s.category != "soft_skills"))
    soft = list(dict.fromkeys(s.name for s in resume.skills.soft_skills))

    def entries_score(entries: list) -> float:
        scores = [e.provenance.confidence * 100 for e in entries if e.provenance]
        return round(mean(scores), 1) if scores else 0

    return DashboardResponse(
        personalInformation=PersonalInformation(
            fullName=value(person.full_name),
            firstName=value(person.first_name),
            lastName=value(person.last_name),
            middleName=labeled("middle name"),
            dateOfBirth=labeled("date of birth", "doğum tarixi", "дата рождения"),
            gender=labeled("gender", "cins", "пол"),
            nationality=value(person.nationality) or labeled("nationality", "vətəndaşlıq"),
            maritalStatus=labeled("marital status", "ailə vəziyyəti"),
            address=value(person.location),
        ),
        contactInformation=ContactInformation(
            email=value(person.email),
            mobilePhone=value(person.phone),
            alternativePhone=next((p for p in phones if p != value(person.phone)), ""),
            linkedIn=person.linkedin or "",
            gitHub=person.github or "",
            portfolio=person.portfolio or person.website or "",
        ),
        professionalInformation=ProfessionalInformation(
            currentJobTitle=current.job_title or ""
            if current
            else value(resume.professional_profile.professional_title),
            currentCompany=current.company or "" if current else "",
            totalExperience=labeled("total experience"),
            careerLevel=labeled("career level"),
            industry=labeled("industry"),
            department=labeled("department"),
        ),
        experience=[
            Experience(
                company=e.company or "",
                position=e.job_title or "",
                startDate=e.start_date or "",
                endDate="Present" if e.current_position else e.end_date or "",
                duration=e.duration or "",
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
        tables=tables,
        confidenceScores=ConfidenceScores(
            fullName=score(person.full_name),
            email=score(person.email),
            phone=score(person.phone),
            experience=entries_score(resume.work_experience),
            education=entries_score(resume.education),
            skills=round(mean(s.confidence for s in all_skills) * 100, 1) if all_skills else 0,
            overall=round(resume.quality.overall_confidence * 100, 1),
        ),
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
            warnings=resume.quality.warnings,
        ),
    )
