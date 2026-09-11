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
    assert b["skills"] == {
        "hard_skills_match": 100,
        "tools_and_frameworks_match": 50,
        "soft_skills_match": 0,
    }
    assert b["skill_match_score"] == 81.25
    assert b["experience"]["years_of_experience_fit"] == b["education_score"] == 100
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
    assert result["breakdown"]["education"]["degree_level_fit"] == 0
    assert result["breakdown"]["education_score"] == 0
    assert result["breakdown"]["experience"]["years_of_experience_fit"] == pytest.approx(50, abs=0.1)
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


def test_all_nested_scores_and_exact_aggregation(cv):
    from app.services.match_dimensions import WEIGHTS

    result = matcher.JobMatcherService().analyze_compatibility(
        cv, "Python Docker Agile senior developer; Master in Computer Science; PMP required"
    )
    b = result["breakdown"]
    mapping = {
        "skills": "skill_match_score",
        "context": "semantic_similarity_score",
        "experience": "experience_score",
        "education": "education_score",
    }
    for group, expected in WEIGHTS.items():
        weights = result["effective_weights"][group]
        assert set(b[group]) == set(expected)
        assert all(0 <= value <= 100 for value in b[group].values())
        assert b[mapping[group]] == round(sum(b[group][key] * weight for key, weight in weights.items()), 2)
    assert result["raw_match_percentage"] == round(
        sum(b[key] * result["effective_weights"]["overall"][group] for group, key in mapping.items()), 2
    )
    b["skills"]["hard_skills_match"] = 101
    with pytest.raises(ValidationError):
        JobMatchResponse.model_validate(result)


def test_independent_skill_categories(cv):
    cv["skills"]["soft"] = ["Agile", "Leadership"]
    result = matcher.JobMatcherService().analyze_compatibility(
        cv, "Required skills: Python, Java, Docker, Redis; Agile and Leadership required"
    )
    assert result["breakdown"]["skills"] == {
        "hard_skills_match": 50,
        "tools_and_frameworks_match": 50,
        "soft_skills_match": 100,
    }
    assert result["breakdown"]["skill_match_score"] == 60


def test_credentials_and_major_are_mapped(cv):
    cv["certifications"] = [{"certificateName": "Project Management Professional"}]
    result = matcher.JobMatcherService().analyze_compatibility(
        cv, "Python; Bachelor in Computer Science; PMP and CKA required"
    )
    assert result["breakdown"]["education"] == {
        "degree_level_fit": 100,
        "field_of_study_relevance": 100,
        "certifications_match": 50,
    }
    assert result["breakdown"]["education_score"] == 92.5
    native = CVEvidence.model_validate(
        {"certifications": [{"certification_name": "PMP"}, {"certification_name": None}]}
    )
    assert native.certifications[0].name == "PMP"


def test_missing_major_and_optional_credential(cv):
    cv["education"] = [{"degree": "Bachelor of Science", "fieldOfStudy": "Culinary Arts"}]
    result = matcher.JobMatcherService().analyze_compatibility(
        cv, "Python; Bachelor in Computer Science; PMP optional"
    )
    assert result["breakdown"]["education"]["field_of_study_relevance"] == 0
    assert result["breakdown"]["education"]["certifications_match"] == 0


def test_title_and_recency_use_work_evidence():
    from app.services.match_dimensions import recency, title_fit

    recent = CVEvidence.model_validate(
        {"experience": [{"position": "Senior Developer", "startDate": "2020-01-01", "endDate": "Present"}]}
    )
    old = CVEvidence.model_validate(
        {"experience": [{"position": "Junior Developer", "startDate": "2010-01-01", "endDate": "2015-01-01"}]}
    )
    today = date(2026, 1, 1)
    assert title_fit(recent, "Senior Developer") == 100
    assert title_fit(old, "Senior Developer") == 50
    assert title_fit(recent, "Senior Nurse") == 0
    assert recency(recent, today) == 100
    assert 0 < recency(old, today) < 30
    missing = CVEvidence.model_validate({"experience": [{"position": "Senior Developer"}]})
    assert recency(missing, today) == 0


def test_summary_and_duties_score_separately(cv):
    cv["summary"] = "Python software backend developer"
    cv["experience"][0]["responsibilities"] = "Prepared restaurant meals"
    result = matcher.JobMatcherService().analyze_compatibility(cv, "Python software backend developer")
    detail = result["breakdown"]["context"]
    assert detail["summary_alignment"] == 100
    assert detail["responsibilities_match"] == 0
    assert detail["domain_relevance"] == 100


def test_empty_evidence_does_not_invent_semantic_matches():
    result = matcher.JobMatcherService().analyze_compatibility(
        {"skills": ["Python"]}, "Python software developer"
    )
    assert result["breakdown"]["context"] == {
        "domain_relevance": 0,
        "responsibilities_match": 0,
        "summary_alignment": 0,
    }
    assert result["breakdown"]["experience"]["recency_factor"] == 0


def test_nested_api_response(client, cv):
    result = client.post(
        "/api/v1/match-job", json={"cv_data": cv, "job_description": "Python Docker developer"}
    )
    assert result.status_code == 200
    b = result.json()["breakdown"]
    assert all(len(b[group]) == 3 for group in ("skills", "context", "experience", "education"))


@pytest.mark.parametrize("bad", [{"soft_skills": 42}, {"certifications": 42}, {"skills": {"soft": 42}}])
def test_new_evidence_validation(bad):
    with pytest.raises(ValidationError):
        JobMatchRequest(cv_data={"summary": "Python developer", **bad}, job_description="Python")


def test_unrelated_tenure_is_excluded():
    cv = {
        "skills": ["Python", "Docker"],
        "experience": [
            {"position": "Chef", "startDate": "2000-01-01", "endDate": "2020-01-01"},
            {"position": "Financial Analyst", "startDate": "2020-01-01", "endDate": "2024-01-01"},
            {"position": "DevOps Engineer", "startDate": "2024-01-01", "endDate": "2025-01-01"},
        ],
    }
    result = matcher.JobMatcherService().analyze_compatibility(
        cv, "DevOps Engineer. Python Docker. 5 years of experience"
    )
    assert result["experience_analysis"]["candidate_years"] == pytest.approx(1, abs=0.01)
    assert result["breakdown"]["experience"]["years_of_experience_fit"] == pytest.approx(20, abs=0.1)


def test_weights_remove_unstated_education_and_tools():
    result = matcher.JobMatcherService().analyze_compatibility({"skills": ["Python"]}, "Python developer")
    weights = result["effective_weights"]
    assert weights["overall"]["education"] == 0
    assert sum(weights["overall"].values()) == pytest.approx(1)
    assert weights["skills"]["hard_skills_match"] == 1
    assert weights["skills"]["tools_and_frameworks_match"] == 0
    assert all(value == 0 for value in result["breakdown"]["education"].values())


def test_missing_required_certification_stays_active(cv):
    result = matcher.JobMatcherService().analyze_compatibility(cv, "Python. PMP required")
    assert result["effective_weights"]["education"]["certifications_match"] == 1
    assert result["breakdown"]["education"]["certifications_match"] == 0


def test_old_benchmark_responses_still_deserialize():
    import json
    from pathlib import Path

    report = json.loads(Path("reports/benchmark_match_results.json").read_text())
    for row in report["results"]:
        JobMatchResponse.model_validate(row["response"])


def test_semantic_context_uses_scoped_requirements(cv, monkeypatch):
    seen = []

    def semantic(text, jd):
        seen.append(jd)
        return 88, "sentence-transformers", []

    monkeypatch.setattr(matcher, "semantic_similarity", semantic)
    result = matcher.JobMatcherService().analyze_compatibility(
        cv, "Backend Developer. Build REST services. Bachelor required. Minimum 5 years of experience."
    )
    assert result["breakdown"]["context"]["responsibilities_match"] == 88
    assert result["breakdown"]["context"]["summary_alignment"] == 88
    assert "Bachelor" not in seen[-1]


def test_technical_requirement_without_explicit_title_rejects_chef_years():
    result = matcher.JobMatcherService().analyze_compatibility(
        {
            "skills": ["Python"],
            "experience": [{"position": "Chef", "startDate": "2000-01-01", "endDate": "2025-01-01"}],
        },
        "Python FastAPI; 5 years of experience",
    )
    assert result["experience_analysis"]["candidate_years"] == 0
