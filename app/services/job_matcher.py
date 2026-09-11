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
from app.services import match_dimensions as dimensions
from app.services.job_reranker import rerank
from app.services.match_policy import clean_text, conflicting_domain, job_constraints, positive_evidence

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
    "php": "PHP",
    "cpr": "CPR",
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
    return skills - dimensions.SOFT


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
    if (
        settings.MATCH_SEMANTIC_BACKEND != "tfidf"
        and not settings.IS_VERCEL
        and len(cv_text) + len(description) <= 32_000
    ):
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
        cv.skills = list(dict.fromkeys(clean_text(skill)[0] for skill in cv.skills if clean_text(skill)[0]))
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
        cv_text, sanitized = clean_text(cv_text)
        cv_text = positive_evidence(cv_text)
        description, _ = clean_text(request.job_description)
        positive_job, forbidden = job_constraints(description, skills_in)
        candidate_skills = skills_in(cv_text, cv.skills) | {canonical(s) for s in cv.skills if s.strip()}
        job_skills = skills_in(positive_job, cv.skills) - forbidden
        matched = sorted(candidate_skills & job_skills)
        missing = sorted(job_skills - candidate_skills)
        semantic_score, method, warnings = semantic_similarity(cv_text, positive_job)
        if sanitized:
            warnings.append("Instruction-like or repetitive content was excluded from scoring evidence.")
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
                "No numeric experience requirement recognized; years-of-experience fit imposes no penalty (100)."
            )
        if needed_level is None:
            warnings.append(
                "No mandatory education level recognized; degree-level fit imposes no penalty (100)."
            )
        duties = dimensions.evidence(
            "\n".join(
                job.responsibilities
                if isinstance(job.responsibilities, str)
                else "\n".join(job.responsibilities)
                for job in cv.experience
            )
        )
        summary = dimensions.evidence(cv.summary)
        soft_text = dimensions.evidence("\n".join([cv_text, *cv.soft_skills]))
        soft_vocabulary = {item: re.escape(item) for item in dimensions.SOFT}
        required_soft = dimensions.recognized(positive_job, soft_vocabulary)
        candidate_soft = dimensions.recognized(soft_text, soft_vocabulary)
        required_tools = job_skills & dimensions.TOOLS
        required_hard = job_skills - dimensions.TOOLS
        skills_detail = {
            "hard_skills_match": dimensions.coverage(candidate_skills, required_hard),
            "tools_and_frameworks_match": dimensions.coverage(candidate_skills, required_tools),
            "soft_skills_match": dimensions.coverage(candidate_soft, required_soft),
        }
        if not job_skills and not required_soft:
            skills_detail = dict.fromkeys(skills_detail, 0.0)

        def similarity(text: str) -> float:
            if not text.strip():
                return 0.0
            value, _, notes = semantic_similarity(text, positive_job)
            warnings.extend(notes)
            return round(value, 2)

        context_detail = {
            "domain_relevance": dimensions.coverage(
                dimensions.recognized(cv_text, dimensions.DOMAINS),
                dimensions.recognized(positive_job, dimensions.DOMAINS),
            ),
            "responsibilities_match": similarity(duties),
            "summary_alignment": similarity(summary),
        }
        experience_detail = {
            "years_of_experience_fit": round(experience_score, 2),
            "title_seniority_match": dimensions.title_fit(cv, positive_job),
            "recency_factor": dimensions.recency(cv, datetime.now(timezone.utc).date()),
        }
        academic_text = dimensions.evidence(
            "\n".join((entry.degree or "") + " " + (entry.field_of_study or "") for entry in cv.education)
        )
        credential_text = dimensions.evidence("\n".join(entry.name or "" for entry in cv.certifications))
        education_detail = {
            "degree_level_fit": education_score,
            "field_of_study_relevance": dimensions.coverage(
                dimensions.recognized(academic_text, dimensions.FIELDS),
                dimensions.recognized(positive_job, dimensions.FIELDS),
            ),
            "certifications_match": dimensions.coverage(
                dimensions.recognized(credential_text, dimensions.CERTIFICATES),
                dimensions.recognized(positive_job, dimensions.CERTIFICATES),
            ),
        }
        groups = {
            "skills": skills_detail,
            "context": context_detail,
            "experience": experience_detail,
            "education": education_detail,
        }
        keys = {
            "skills": "skill_match_score",
            "context": "semantic_similarity_score",
            "experience": "experience_score",
            "education": "education_score",
        }
        breakdown = {
            **groups,
            **{keys[group]: dimensions.aggregate(group, values) for group, values in groups.items()},
        }
        baseline = sum(weight * breakdown[key] for weight, key in zip((0.4, 0.3, 0.2, 0.1), keys.values()))
        domain_conflict = conflicting_domain(cv_text, description)
        complex_input = bool(
            forbidden or domain_conflict or re.search(r"\b[A-Z]{2,4}\b|\bnot\b", description)
        )
        routing = {"stage_1": method, "stage_2": "not_needed"}
        if (40 <= baseline <= 70 or complex_input) and (duties or summary):
            refined, reason = rerank(duties or summary, positive_job)
            routing["stage_2"] = reason
            if refined is not None:
                field = "responsibilities_match" if duties else "summary_alignment"
                context_detail[field] = round(refined, 2)
                method = "cross-encoder"
                routing["reranked_field"] = field
            else:
                warnings.append(
                    "Contextual reranker unavailable within resource policy; deterministic guards and baseline scoring were used."
                )
        breakdown["semantic_similarity_score"] = dimensions.aggregate("context", context_detail)
        semantic_score = breakdown["semantic_similarity_score"]
        warnings.append(
            "Subcategories without recognized requirements score 100 (no constraint); missing summary, duties or valid work dates score 0. See documented aggregation weights."
        )
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
        raw_score = score
        adjustments = []
        violations = sorted(candidate_skills & forbidden)
        if violations:
            score = 0.0
            adjustments.append("Hard exclusion violated: " + ", ".join(display(s) for s in violations))
        elif domain_conflict:
            score = min(score, 9.0)
            adjustments.append("Explicit acronym domain conflict: compatibility capped below 10%.")
        elif not matched:
            score = min(score, 9.0, semantic_score * 0.09)
            adjustments.append(
                "No documented required hard-skill overlap: unrelated experience and education cannot establish compatibility."
            )
        logger.bind(
            stage_1=routing["stage_1"], stage_2=routing["stage_2"], adjustments=len(adjustments)
        ).info("job_match_routing")
        recommendations = []
        recommendations.extend(adjustments)
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
            raw_match_percentage=raw_score,
            scoring_adjustments=adjustments,
            model_routing=routing,
        ).model_dump()
