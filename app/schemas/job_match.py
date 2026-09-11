"""Bounded, validated job-matching inputs and explanatory scores."""

import json
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(max_length=20_000, strict=True)]
Score = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class WorkEvidence(EvidenceModel):
    position: Text | None = Field(default="", validation_alias=AliasChoices("position", "job_title"))
    start_date: Text | None = Field(default=None, validation_alias=AliasChoices("start_date", "startDate"))
    end_date: Text | None = Field(default=None, validation_alias=AliasChoices("end_date", "endDate"))
    current_position: bool = False
    responsibilities: Text | list[Text] = Field(default_factory=list)


class EducationEvidence(EvidenceModel):
    degree: Text | None = None
    field_of_study: Text | None = Field(
        default=None, validation_alias=AliasChoices("field_of_study", "fieldOfStudy")
    )


class CVEvidence(EvidenceModel):
    summary: Text = ""
    skills: list[Text] = Field(default_factory=list, max_length=500)
    experience: list[WorkEvidence] = Field(default_factory=list, max_length=200)
    education: list[EducationEvidence] = Field(default_factory=list, max_length=100)
    project_text: list[Text] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def adapt_parser_formats(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            raise ValueError("cv_data must be an object")
        data = dict(value)
        raw_skills = data.get("skills", {})
        skills = []
        if isinstance(raw_skills, dict):
            for category, entries in raw_skills.items():
                if category in {"soft", "soft_skills"}:
                    continue
                if not isinstance(entries, list):
                    raise ValueError("Each skill category must contain a list")
                for entry in entries:
                    skills.append(entry.get("name") if isinstance(entry, dict) else entry)
        elif isinstance(raw_skills, list):
            skills = raw_skills
        else:
            raise ValueError("skills must be an object or list")
        data["skills"] = skills
        profile = data.get("professional_profile", {})
        if not isinstance(profile, dict):
            raise ValueError("professional_profile must be an object")
        summary = data.get("summary", profile.get("professional_summary", ""))
        if isinstance(summary, dict):
            summary = summary.get("value", "")
        data["summary"] = summary or ""
        data["experience"] = data.get("experience", data.get("work_experience", []))
        project_text = []
        projects = data.get("projects", [])
        if not isinstance(projects, list) or len(projects) > 100:
            raise ValueError("projects must contain at most 100 entries")
        for project in projects:
            if not isinstance(project, dict):
                raise ValueError("Each project must be an object")
            for key in ("description", "technologies"):
                item = project.get(key, "")
                if isinstance(item, list):
                    if not all(isinstance(part, str) for part in item):
                        raise ValueError("Project technologies must be strings")
                    item = ", ".join(item)
                if item:
                    project_text.append(item)
        data["project_text"] = project_text
        return data

    @model_validator(mode="after")
    def has_evidence(self) -> "CVEvidence":
        if not (
            self.summary.strip()
            or any(s.strip() for s in self.skills)
            or self.experience
            or self.education
            or self.project_text
        ):
            raise ValueError("cv_data must contain skills, work history, education, projects, or a summary")
        return self


class JobMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_description: Text = Field(min_length=1)
    cv_data: dict[str, Any]

    @field_validator("job_description")
    @classmethod
    def meaningful_description(cls, value: str) -> str:
        value = value.strip()
        if not any(c.isalnum() for c in value):
            raise ValueError("Job description must contain text")
        return value

    @field_validator("cv_data")
    @classmethod
    def bounded_cv(cls, value: dict) -> dict:
        try:
            size = len(json.dumps(value, ensure_ascii=False, allow_nan=False))
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValueError("CV must contain finite JSON values") from exc
        if size > 100_000:
            raise ValueError("CV data exceeds 100,000 characters")
        CVEvidence.model_validate(value)
        return value


class MatchBreakdown(BaseModel):
    skill_match_score: Score
    semantic_similarity_score: Score
    experience_score: Score
    education_score: Score


class SkillsAnalysis(BaseModel):
    matched_skills: list[str]
    missing_skills: list[str]


class JobMatchResponse(BaseModel):
    match_percentage: Score
    verdict: Literal["Highly Suitable", "Suitable", "Partially Suitable", "Low Compatibility"]
    breakdown: MatchBreakdown
    skills_analysis: SkillsAnalysis
    recommendations: list[str]
    semantic_method: Literal["sentence-transformers", "tfidf", "cross-encoder"]
    experience_analysis: dict[str, float | None]
    education_analysis: dict[str, str | None]
    warnings: list[str]
    raw_match_percentage: Score = 0
    scoring_adjustments: list[str] = Field(default_factory=list)
    model_routing: dict[str, str] = Field(default_factory=dict)
