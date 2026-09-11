from datetime import date

import numpy as np
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import settings
from app.schemas.job_match import CVEvidence, JobMatchRequest, JobMatchResponse
from app.services import job_matcher as matcher
from app.services.dashboard_adapter import adapt_resume
from app.services.resume_parser import ResumeParserService


@pytest.fixture(autouse=True)
def lexical_backend(monkeypatch):
    monkeypatch.setattr(settings, "MATCH_SEMANTIC_BACKEND", "tfidf")
    from app.services import job_reranker

    monkeypatch.setattr(job_reranker, "model_cached", lambda: False)


@pytest.fixture
def cv():
    return {
        "summary": "Backend software engineer building Python APIs.",
        "skills": {"technical": ["Python", "FastAPI", "Docker"]},
        "experience": [
            {
                "position": "Backend Developer",
                "startDate": "2020-01-01",
                "endDate": "2025-01-01",
                "responsibilities": "Built REST services.",
            }
        ],
        "education": [{"degree": "Bachelor of Science", "fieldOfStudy": "Computer Science"}],
    }


def test_weighted_formula_and_missing_skills(cv):
    result = matcher.JobMatcherService().analyze_compatibility(
        cv,
        "Python, FastAPI, Docker, Redis, Kubernetes. Minimum 3 years of experience. Bachelor degree required.",
    )
    JobMatchResponse.model_validate(result)
    b = result["breakdown"]
    assert b["skill_match_score"] == 60
    assert b["experience_score"] == b["education_score"] == 100
    assert result["match_percentage"] == round(
        0.4 * b["skill_match_score"]
        + 0.3 * b["semantic_similarity_score"]
        + 0.2 * b["experience_score"]
        + 0.1 * b["education_score"],
        2,
    )
    assert result["skills_analysis"]["missing_skills"] == ["Kubernetes", "Redis"]
    assert result["semantic_method"] == "tfidf"


def test_real_tfidf():
    assert matcher.tfidf_similarity("Python Docker", "Python Docker") == pytest.approx(100)
    assert matcher.tfidf_similarity("Python Docker", "nursing hospital") == 0
    assert matcher.tfidf_similarity("!", "...") == 0


def test_skill_aliases_boundaries():
    skills = matcher.skills_in("JavaScript, postgres, k8s, C++, C#")
    assert {"javascript", "postgresql", "kubernetes", "c++", "c#"} <= skills
    assert "java" not in skills


def test_unknown_explicit_skill(cv):
    result = matcher.JobMatcherService().analyze_compatibility(cv, "Required skills: Python, Temporal")
    assert result["skills_analysis"]["missing_skills"] == ["Temporal"]


def test_conjoined_skill_list(cv):
    result = matcher.JobMatcherService().analyze_compatibility(
        cv, "Required skills: Python, FastAPI and Docker"
    )
    assert result["breakdown"]["skill_match_score"] == 100
    assert result["skills_analysis"]["missing_skills"] == []


def test_overlapping_and_ongoing_experience():
    evidence = CVEvidence.model_validate(
        {
            "experience": [
                {"startDate": "2020-01-01", "endDate": "2022-01-01"},
                {"startDate": "2021-01-01", "endDate": "Present"},
                {"startDate": "2030-01-01", "endDate": "Present"},
            ]
        }
    )
    years, warnings = matcher.experience_years(evidence, date(2024, 1, 1))
    assert years == pytest.approx(4, abs=0.01)
    assert warnings


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Minimum 3-5 years of experience", 3),
        ("Experience: 2+ years", 2),
        ("18 months of experience", 1.5),
        ("Ən az 3 il iş təcrübəsi", 3),
        ("3 yıl deneyim", 3),
        ("Опыт работы 3 года", 3),
        ("Annual leave: 30 days", None),
    ],
)
def test_experience_requirements(description, expected):
    assert matcher.required_years(description) == expected


def test_missing_dates_do_not_invent_experience():
    evidence = CVEvidence.model_validate({"experience": [{"startDate": "03/04/2020", "endDate": "2023"}, {}]})
    years, warnings = matcher.experience_years(evidence, date(2025, 1, 1))
    assert years == 0 and warnings


def test_education_and_unknown_requirements(cv):
    result = matcher.JobMatcherService().analyze_compatibility(
        cv, "Python; Master degree required; 10 years of experience"
    )
    assert result["breakdown"]["education_score"] == 0
    assert result["breakdown"]["experience_score"] == pytest.approx(50, abs=0.1)
    assert matcher.degree_level("Bachelor or Master degree", requirement=True) == (3, "Bachelor")
    assert matcher.degree_level("Master preferred", requirement=True) == (None, None)
    no_requirements = matcher.JobMatcherService().analyze_compatibility(cv, "Manage the team")
    assert no_requirements["warnings"]
    assert no_requirements["breakdown"]["skill_match_score"] == 0


def test_personal_attributes_do_not_affect_matching(cv):
    service = matcher.JobMatcherService()
    first = service.analyze_compatibility(cv, "Python developer")
    cv["personalInformation"] = {
        "fullName": "Different Person",
        "gender": "Female",
        "dateOfBirth": "1960-01-01",
        "nationality": "Other",
    }
    cv["contactInformation"] = {"email": "python@docker.org"}
    assert service.analyze_compatibility(cv, "Python developer") == first


def test_both_parser_formats(pdf_bytes):
    native = ResumeParserService().parse_pdf(pdf_bytes, "test.pdf")
    service = matcher.JobMatcherService()
    a = service.analyze_compatibility(native.model_dump(), "Python FastAPI 2 years of experience")
    b = service.analyze_compatibility(
        adapt_resume(native).model_dump(), "Python FastAPI 2 years of experience"
    )
    assert a["skills_analysis"] == b["skills_analysis"]
    assert a["experience_analysis"] == b["experience_analysis"]


def test_embedding_unavailable_falls_back(cv, monkeypatch):
    monkeypatch.setattr(settings, "MATCH_SEMANTIC_BACKEND", "auto")
    monkeypatch.setattr(matcher, "embedding_model", lambda local_only: None)
    result = matcher.JobMatcherService().analyze_compatibility(cv, "Python")
    assert result["semantic_method"] == "tfidf"


def test_embedding_failure_falls_back(cv, monkeypatch):
    class Broken:
        def tokenizer(self, *args, **kwargs):
            raise RuntimeError("unavailable")

    monkeypatch.setattr(settings, "MATCH_SEMANTIC_BACKEND", "auto")
    monkeypatch.setattr(matcher, "embedding_model", lambda local_only: Broken())
    assert matcher.JobMatcherService().analyze_compatibility(cv, "Python")["semantic_method"] == "tfidf"


def test_embedding_chunking_and_cosine(monkeypatch):
    class Tokenizer:
        def __call__(self, text, **kwargs):
            return {"input_ids": list(range(len(text.split())))}

        def decode(self, ids):
            return " ".join(map(str, ids))

    class Encoder:
        max_seq_length = 4
        tokenizer = Tokenizer()
        chunks = []

        def encode(self, chunks, **kwargs):
            self.chunks.extend(chunks)
            return np.array([[1.0, 0.0] for _ in chunks])

    encoder = Encoder()
    monkeypatch.setattr(settings, "MATCH_SEMANTIC_BACKEND", "auto")
    monkeypatch.setattr(matcher, "embedding_model", lambda local_only: encoder)
    score, method, _ = matcher.semantic_similarity("one two three four five", "one two")
    assert score == 100 and method == "sentence-transformers"
    assert len(encoder.chunks) == 4


@pytest.mark.parametrize(
    "cv_data,jd",
    [
        ({}, "Python"),
        ({"skills": 42}, "Python"),
        ({"skills": ["Python"]}, "   "),
        ({"skills": ["Python"]}, "x" * 20001),
        ({"skills": ["x" * 100001]}, "Python"),
        ({"experience": [{"startDate": 123}]}, "Python"),
    ],
)
def test_invalid_inputs(cv_data, jd):
    with pytest.raises(ValidationError):
        JobMatchRequest(cv_data=cv_data, job_description=jd)


def test_api_success_and_validation(client, cv):
    response = client.post("/api/v1/match-job", json={"cv_data": cv, "job_description": "Python developer"})
    assert response.status_code == 200
    JobMatchResponse.model_validate(response.json())
    assert (
        client.post("/api/v1/match-job", json={"cv_data": {}, "job_description": "Python"}).status_code == 422
    )


def test_api_auth(client, cv, monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", SecretStr("test-key"))
    payload = {"cv_data": cv, "job_description": "Python"}
    assert client.post("/api/v1/match-job", json=payload).status_code == 401
    assert (
        client.post("/api/v1/match-job", json=payload, headers={"x-api-key": "test-key"}).status_code == 200
    )


def test_api_capacity(client, cv, monkeypatch):
    class Full:
        def locked(self):
            return True

    monkeypatch.setattr(client.app.state, "parse_slots", Full())
    response = client.post("/api/v1/match-job", json={"cv_data": cv, "job_description": "Python"})
    assert response.status_code == 503 and response.headers["retry-after"] == "5"
