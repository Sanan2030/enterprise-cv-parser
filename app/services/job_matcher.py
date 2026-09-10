"""Explainable job requirements matching, independent of PDF extraction."""

import re
import unicodedata
from collections.abc import Sequence
from datetime import date, datetime, timezone
from functools import lru_cache
from threading import Lock
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.core.logging import logger
from app.normalization.date_normalizer import CURRENT, DateNormalizer
from app.parsing.skill_extractor import SKILL_TAXONOMY
from app.schemas.job_match import CVEvidence, JobMatchRequest, JobMatchResponse

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_model_lock = Lock()
ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "react.js": "react",
    "reactjs": "react",
    "nodejs": "node.js",
    "golang": "go",
    "amazon web services": "aws",
    "sklearn": "scikit-learn",
    "c sharp": "c#",
}
NAMES = {
    "fastapi": "FastAPI",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "node.js": "Node.js",
    "c++": "C++",
    "c#": "C#",
    "aws": "AWS",
    "gcp": "GCP",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "ci/cd": "CI/CD",
}
DEGREES = [
    (1, "High school", r"high school|secondary school"),
    (2, "Associate", r"associate(?:'s)?(?: degree)?"),
    (3, "Bachelor", r"bachelor(?:'s)?|b\.?sc\.?|bakalavr|lisans|бакалавр"),
    (4, "Master", r"master(?:'s)?|m\.?sc\.?|magistr|yüksek lisans|магистр"),
    (5, "Doctorate", r"ph\.?d\.?|doctorate|doctoral|doktorant|доктор"),
]


def normalized(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold().replace("i\u0307", "i")


def canonical(skill: str) -> str:
    value = normalized(skill.strip())
    return ALIASES.get(value, value)


def display(skill: str) -> str:
    return NAMES.get(skill, skill.title())


def contains(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?<![\w+#])" + re.escape(phrase) + r"(?![\w+#])", text))


def skills_in(text: str, extra: Sequence[str] = ()) -> set[str]:
    text = normalized(text)
    vocabulary = {
        s for category, entries in SKILL_TAXONOMY.items() if category != "soft_skills" for s in entries
    }
    vocabulary.update({"node.js", "linux", "rest", "graphql", "oauth", "jwt", "spring security"})
    vocabulary.update(canonical(s) for s in extra if s.strip())
    skills = {canonical(s) for s in vocabulary | set(ALIASES) if contains(text, s)}
    # Explicit lists preserve named tools outside the curated vocabulary.
    for match in re.finditer(
        r"(?im)^\s*(?:required skills|technical skills|skills|bacarıqlar)\s*:\s*([^\n]+)", text
    ):
        for item in re.split(r"[,;]|\s+(?:and|və|ve)\s+|\s*&\s*", match[1]):
            item = item.strip().rstrip(".")
            if 0 < len(item) <= 60 and len(item.split()) <= 4:
                skills.add(canonical(item))
    return skills - {canonical(s) for s in SKILL_TAXONOMY["soft_skills"]}


@lru_cache(maxsize=2)
def embedding_model(local_only: bool) -> Any | None:
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(MODEL, device="cpu", local_files_only=local_only, trust_remote_code=False)
    except Exception as exc:
        # Optional dependency/model failures must not disable the endpoint.
        logger.bind(error_type=type(exc).__name__).info("job_match_tfidf_fallback")
        return None


def tfidf_similarity(cv_text: str, description: str) -> float:
    try:
        matrix = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, max_features=20_000, token_pattern=r"(?u)\b\w[\w+#.]*"
        ).fit_transform([cv_text, description])
    except ValueError:  # Empty vocabulary, including punctuation-only evidence.
        return 0.0
    return float(np.clip(cosine_similarity(matrix[0], matrix[1])[0, 0], 0, 1)) * 100


def semantic_similarity(cv_text: str, description: str) -> tuple[float, str, list[str]]:
    if settings.MATCH_SEMANTIC_BACKEND != "tfidf":
        with _model_lock:
            model = embedding_model(settings.MATCH_MODEL_LOCAL_ONLY)
            if model is not None:
                try:
                    vectors = []
                    for text in (cv_text, description):
                        tokens = model.tokenizer(text, add_special_tokens=False)["input_ids"]
                        capacity = max(1, model.max_seq_length - 2)
                        segments = [tokens[i : i + capacity] for i in range(0, len(tokens), capacity)] or [[]]
                        chunks = [model.tokenizer.decode(part) for part in segments]
                        embeddings = model.encode(
                            chunks, normalize_embeddings=True, show_progress_bar=False, batch_size=16
                        )
                        centroid = np.average(
                            embeddings, axis=0, weights=[max(1, len(part)) for part in segments]
                        )
                        vectors.append(centroid)
                    result = float(cosine_similarity([vectors[0]], [vectors[1]])[0, 0])
                    if not np.isfinite(result):
                        raise ValueError("Non-finite embedding similarity")
                    return float(np.clip(result, 0, 1)) * 100, "sentence-transformers", []
                except Exception as exc:
                    logger.bind(error_type=type(exc).__name__).warning("job_match_embedding_failed")
    return (
        tfidf_similarity(cv_text, description),
        "tfidf",
        ["TF-IDF measures lexical overlap; contextual embeddings were unavailable or disabled."],
    )


def experience_years(cv: CVEvidence, today: date) -> tuple[float, list[str]]:
    intervals = []
    warnings = []
    for job in cv.experience:
        start = DateNormalizer.normalize(job.start_date or "")
        ongoing = job.current_position or bool(re.fullmatch(CURRENT, job.end_date or "", re.I))
        end = today.isoformat() if ongoing else DateNormalizer.normalize(job.end_date or "")
        if not start or not end:
            warnings.append(
                "Work entries with missing or ambiguous dates were excluded from experience years."
            )
            continue

        def boundary(value: str) -> date:
            if len(value) < 10:
                warnings.append(
                    "Experience based on month/year-only dates is approximate (first day assumed)."
                )
            return date.fromisoformat(
                value + ("-01-01" if len(value) == 4 else "-01" if len(value) == 7 else "")
            )

        first, last = boundary(start), min(boundary(end), today)
        if first >= last:
            warnings.append("Future or reversed employment intervals were excluded.")
            continue
        intervals.append((first, last))
    merged = []
    for first, last in sorted(intervals):
        if merged and first <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(last, merged[-1][1]))
        else:
            merged.append((first, last))
    return sum((last - first).days for first, last in merged) / 365.2425, list(dict.fromkeys(warnings))


def required_years(description: str) -> float | None:
    number = r"(\d+(?:\.\d+)?)"
    pattern = number + r"(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*\+?\s*(years?|yrs?|months?|il|yıl|лет|года?)\b"
    requirements = []
    for match in re.finditer(pattern, normalized(description)):
        context = description[max(0, match.start() - 40) : match.end() + 60]
        if not re.search(r"experience|təcrüb|deneyim|опыт", context, re.I):
            continue
        value = float(match[1]) / (12 if match[2].startswith("month") else 1)
        requirements.append(value)
    return max(requirements) if requirements else None


def degree_level(text: str, *, requirement: bool = False) -> tuple[int | None, str | None]:
    matches = []
    for clause in re.split(r"[\n;]|\.(?=\s+[A-Z])", text):
        if requirement and re.search(r"not required|no degree|preferred|optional|üstünlük", clause, re.I):
            continue
        for level, name, pattern in DEGREES:
            if re.search(r"(?<!\w)(?:" + pattern + r")(?!\w)", clause, re.I):
                matches.append((level, name))
    return (min(matches) if requirement else max(matches)) if matches else (None, None)


class JobMatcherService:
    def analyze_compatibility(self, cv_data: dict, job_description: str) -> dict:
        request = JobMatchRequest(cv_data=cv_data, job_description=job_description)
        cv = CVEvidence.model_validate(request.cv_data)
        # Only professional evidence enters scoring; identity, contacts and demographics do not.
        text_parts = [cv.summary, *cv.skills, *cv.project_text]
        for job in cv.experience:
            text_parts.append(job.position or "")
            text_parts.extend(
                [job.responsibilities] if isinstance(job.responsibilities, str) else job.responsibilities
            )
        for education in cv.education:
            text_parts.extend([education.degree or "", education.field_of_study or ""])
        cv_text = "\n".join(part for part in text_parts if part)
        candidate_skills = skills_in(cv_text, cv.skills) | {canonical(s) for s in cv.skills if s.strip()}
        job_skills = skills_in(request.job_description, cv.skills)
        matched = sorted(candidate_skills & job_skills)
        missing = sorted(job_skills - candidate_skills)
        skill_score = 100 * len(matched) / len(job_skills) if job_skills else 0.0
        semantic_score, method, warnings = semantic_similarity(cv_text, request.job_description)
        years, date_warnings = experience_years(cv, datetime.now(timezone.utc).date())
        warnings.extend(date_warnings)
        needed = required_years(request.job_description)
        experience_score = min(100, 100 * years / needed) if needed else 100.0
        candidate_level, candidate_degree = degree_level("\n".join(e.degree or "" for e in cv.education))
        needed_level, needed_degree = degree_level(request.job_description, requirement=True)
        education_score = 100.0 if needed_level is None or (candidate_level or 0) >= needed_level else 0.0
        if not job_skills:
            warnings.append(
                "No hard skills recognized in the job description; skill coverage is unscored (0)."
            )
        if needed is None:
            warnings.append(
                "No numeric experience requirement recognized; experience imposes no penalty (100)."
            )
        if needed_level is None:
            warnings.append("No mandatory education level recognized; education imposes no penalty (100).")
        breakdown = {
            "skill_match_score": round(skill_score, 2),
            "semantic_similarity_score": round(semantic_score, 2),
            "experience_score": round(experience_score, 2),
            "education_score": round(education_score, 2),
        }
        score = round(
            sum(
                weight * breakdown[key]
                for weight, key in [
                    (0.4, "skill_match_score"),
                    (0.3, "semantic_similarity_score"),
                    (0.2, "experience_score"),
                    (0.1, "education_score"),
                ]
            ),
            2,
        )
        recommendations = []
        if missing:
            recommendations.append(
                "Missing documented skills: " + ", ".join(display(s) for s in missing) + "."
            )
        if needed is not None:
            recommendations.append(
                f"Documented experience: {years:.2f} years; required: {needed:g} years. "
                + (
                    "Requirement met."
                    if experience_score >= 100
                    else "Verify additional relevant experience."
                )
            )
        if needed_level is not None and education_score < 100:
            recommendations.append(
                f"Required education: {needed_degree}; verify the candidate's qualification."
            )
        if not recommendations:
            recommendations.append("Review the supporting CV evidence and role-specific requirements.")
        return JobMatchResponse(
            match_percentage=score,
            verdict="Highly Suitable"
            if score >= 80
            else "Suitable"
            if score >= 60
            else "Partially Suitable"
            if score >= 40
            else "Low Compatibility",
            breakdown=breakdown,
            skills_analysis={
                "matched_skills": [display(s) for s in matched],
                "missing_skills": [display(s) for s in missing],
            },
            recommendations=recommendations,
            semantic_method=method,
            experience_analysis={"candidate_years": round(years, 2), "required_years": needed},
            education_analysis={"candidate_level": candidate_degree, "required_level": needed_degree},
            warnings=list(dict.fromkeys(warnings)),
        ).model_dump()
