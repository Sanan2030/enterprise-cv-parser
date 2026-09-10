import re
from datetime import date
from typing import Annotated, List, Literal, Optional, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def validate_partial_date(value: str) -> str:
    if not re.fullmatch(r"(?:19|20)\d{2}(?:-\d{2}(?:-\d{2})?)?", value):
        raise ValueError("Expected YYYY, YYYY-MM or YYYY-MM-DD")
    parts = [int(part) for part in value.split("-")]
    date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    return value


PartialDate = Annotated[str, AfterValidator(validate_partial_date)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Provenance(Schema):
    page: int = Field(default=1, ge=1, description="1-indexed page number")
    source_text: str = Field(default="", description="Exact raw text snippet")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class FieldWithMetadata(Schema):
    value: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Optional[Provenance] = None


class PersonalInformation(Schema):
    middle_name: Optional[FieldWithMetadata] = None
    date_of_birth: Optional[FieldWithMetadata] = None
    gender: Optional[FieldWithMetadata] = None
    alternative_phone: Optional[FieldWithMetadata] = None
    first_name: Optional[FieldWithMetadata] = None
    last_name: Optional[FieldWithMetadata] = None
    full_name: Optional[FieldWithMetadata] = None
    email: Optional[FieldWithMetadata] = None
    phone: Optional[FieldWithMetadata] = None
    location: Optional[FieldWithMetadata] = None
    country: Optional[FieldWithMetadata] = None
    nationality: Optional[FieldWithMetadata] = None
    website: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other_links: List[str] = Field(default_factory=list)


class ProfessionalProfile(Schema):
    professional_summary: Optional[FieldWithMetadata] = None
    career_objective: Optional[FieldWithMetadata] = None
    professional_title: Optional[FieldWithMetadata] = None


class WorkExperience(Schema):
    job_title: Optional[str] = None
    company: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[PartialDate] = None
    end_date: Optional[PartialDate] = None
    current_position: bool = False
    duration: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    extracted_skills: List[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None

    @model_validator(mode="after")
    def coherent_dates(self) -> Self:
        if self.current_position and self.end_date:
            raise ValueError("A current position cannot have an end date")
        if self.start_date and self.end_date and self.start_date[:7] > self.end_date[:7]:
            raise ValueError("End date precedes start date")
        return self


class Education(Schema):
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    institution: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[PartialDate] = None
    end_date: Optional[PartialDate] = None
    graduation_date: Optional[PartialDate] = None
    gpa: Optional[str] = None
    provenance: Optional[Provenance] = None


class ExtractedSkill(Schema):
    name: str
    category: str
    source_text: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    explicit: bool = True


class SkillsCategorized(Schema):
    programming_languages: List[ExtractedSkill] = Field(default_factory=list)
    frameworks: List[ExtractedSkill] = Field(default_factory=list)
    libraries: List[ExtractedSkill] = Field(default_factory=list)
    databases: List[ExtractedSkill] = Field(default_factory=list)
    cloud: List[ExtractedSkill] = Field(default_factory=list)
    devops: List[ExtractedSkill] = Field(default_factory=list)
    data_science: List[ExtractedSkill] = Field(default_factory=list)
    machine_learning: List[ExtractedSkill] = Field(default_factory=list)
    artificial_intelligence: List[ExtractedSkill] = Field(default_factory=list)
    business_analysis: List[ExtractedSkill] = Field(default_factory=list)
    project_management: List[ExtractedSkill] = Field(default_factory=list)
    software_tools: List[ExtractedSkill] = Field(default_factory=list)
    methodologies: List[ExtractedSkill] = Field(default_factory=list)
    soft_skills: List[ExtractedSkill] = Field(default_factory=list)
    other_skills: List[ExtractedSkill] = Field(default_factory=list)


class Certification(Schema):
    certification_name: Optional[str] = None
    issuer: Optional[str] = None
    issue_date: Optional[PartialDate] = None
    expiration_date: Optional[PartialDate] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None


class LanguageSkill(Schema):
    language: str
    proficiency: Optional[str] = None
    cefr_level: Optional[str] = None


class Project(Schema):
    project_name: Optional[str] = None
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)
    role: Optional[str] = None
    dates: Optional[str] = None
    url: Optional[str] = None
    github_url: Optional[str] = None


class QualityControl(Schema):
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)
    missing_sections: List[str] = Field(default_factory=list)
    extraction_method: Literal["native", "ocr", "hybrid"] = "native"


class LanguageDetectionResult(Schema):
    primary: str = "und"
    secondary: List[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0, le=1)


class DocumentMetadata(Schema):
    file_name: str
    page_count: int = Field(ge=1)
    document_language: LanguageDetectionResult
    processing_time_ms: float = Field(ge=0)


class ResumeParsedSchema(Schema):
    document: DocumentMetadata
    personal_information: PersonalInformation
    professional_profile: ProfessionalProfile
    work_experience: List[WorkExperience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    skills: SkillsCategorized = Field(default_factory=SkillsCategorized)
    certifications: List[Certification] = Field(default_factory=list)
    languages: List[LanguageSkill] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    raw_sections: dict[str, list[Provenance]] = Field(default_factory=dict)
    quality: QualityControl
