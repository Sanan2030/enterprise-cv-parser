from pydantic import Field

from app.schemas.resume import Schema


class PersonalInformation(Schema):
    fullName: str = ""
    firstName: str = ""
    lastName: str = ""
    middleName: str = ""
    dateOfBirth: str = ""
    gender: str = ""
    nationality: str = ""
    maritalStatus: str = ""
    address: str = ""


class ContactInformation(Schema):
    email: str = ""
    mobilePhone: str = ""
    alternativePhone: str = ""
    linkedIn: str = ""
    gitHub: str = ""
    portfolio: str = ""


class ProfessionalInformation(Schema):
    currentJobTitle: str = ""
    currentCompany: str = ""
    totalExperience: str = ""
    careerLevel: str = ""
    industry: str = ""
    department: str = ""


class Experience(Schema):
    company: str = ""
    position: str = ""
    startDate: str = ""
    endDate: str = ""
    duration: str = ""
    responsibilities: str = ""
    department: str = ""
    location: str = ""
    employmentType: str = ""


class Education(Schema):
    university: str = ""
    degree: str = ""
    fieldOfStudy: str = ""
    startDate: str = ""
    endDate: str = ""
    gpa: str = ""
    academicAchievements: str = ""


class Skills(Schema):
    technical: list[str] = Field(default_factory=list)
    soft: list[str] = Field(default_factory=list)


class Language(Schema):
    language: str = ""
    level: str = ""


class Certification(Schema):
    certificateName: str = ""
    issuingOrganization: str = ""
    issueDate: str = ""
    credentialID: str = ""


class Project(Schema):
    projectName: str = ""
    description: str = ""
    technologies: str = ""
    role: str = ""


class Table(Schema):
    title: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class ConfidenceScores(Schema):
    fullName: float = Field(0, ge=0, le=100)
    email: float = Field(0, ge=0, le=100)
    phone: float = Field(0, ge=0, le=100)
    experience: float = Field(0, ge=0, le=100)
    education: float = Field(0, ge=0, le=100)
    skills: float = Field(0, ge=0, le=100)
    overall: float = Field(0, ge=0, le=100)


class Metadata(Schema):
    filename: str
    pages: int
    words: int
    emails: int
    phones: int
    pdfType: str
    documentLanguage: str
    processingTimeMs: float
    llmEnabled: bool
    warnings: list[str] = Field(default_factory=list)


class DashboardResponse(Schema):
    personalInformation: PersonalInformation = Field(default_factory=PersonalInformation)
    contactInformation: ContactInformation = Field(default_factory=ContactInformation)
    professionalInformation: ProfessionalInformation = Field(default_factory=ProfessionalInformation)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    languages: list[Language] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    summary: str = ""
    tables: list[Table] = Field(default_factory=list)
    confidenceScores: ConfidenceScores = Field(default_factory=ConfidenceScores)
    metadata: Metadata
