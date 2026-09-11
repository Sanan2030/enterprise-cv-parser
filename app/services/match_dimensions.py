"""Deterministic requirement coverage and dated professional evidence dimensions."""

import re
from datetime import date

from app.normalization.date_normalizer import CURRENT, DateNormalizer
from app.parsing.skill_extractor import SKILL_TAXONOMY
from app.schemas.job_match import CVEvidence
from app.services.match_policy import clean_text, positive_evidence

WEIGHTS = {
    "skills": {"hard_skills_match": 0.5, "tools_and_frameworks_match": 0.3, "soft_skills_match": 0.2},
    "context": {"domain_relevance": 0.3, "responsibilities_match": 0.5, "summary_alignment": 0.2},
    "experience": {"years_of_experience_fit": 0.6, "title_seniority_match": 0.25, "recency_factor": 0.15},
    "education": {"degree_level_fit": 0.6, "field_of_study_relevance": 0.25, "certifications_match": 0.15},
}
SOFT = set(SKILL_TAXONOMY["soft_skills"]) | {"agile", "scrum", "kanban"}
TOOLS = {
    s
    for k, entries in SKILL_TAXONOMY.items()
    if k in {"software_tools", "frameworks", "libraries", "databases", "cloud", "devops"}
    for s in entries
} | {"linux", "node.js", "jira", "confluence", "excel", "power bi", "tableau"}
DOMAINS = {
    "software": r"software|backend|frontend|devops|computer science|computing|informatics",
    "finance": r"financ\w*|banking|fintech|accounting",
    "healthcare": r"healthcare|medicine|medical|nursing|patient care",
    "creative": r"advertising|film production|creative production",
    "hospitality": r"culinary|restaurant|chef|hospitality",
    "engineering": r"mechanical engineering|electrical engineering|civil engineering",
}
FIELDS = {
    "computer science": r"computer science|computing|informatics",
    "software engineering": r"software engineering",
    "business": r"business administration|business management",
    "finance": r"finance|accounting|economics",
    "medicine": r"medicine|nursing",
    "engineering": r"mechanical engineering|electrical engineering|civil engineering",
}
CERTIFICATES = {
    "pmp": r"pmp|project management professional",
    "cka": r"cka|certified kubernetes administrator",
    "aws solutions architect": r"aws (?:certified )?solutions architect(?: associate)?",
    "cissp": r"cissp|certified information systems security professional",
    "cpa": r"cpa|certified public accountant",
    "scrum master": r"psm|csm|certified scrum master|professional scrum master",
    "cpr": r"cpr|cardiopulmonary resuscitation",
}


def evidence(text: str) -> str:
    return positive_evidence(clean_text(text)[0])


def recognized(text: str, vocabulary: dict[str, str]) -> set[str]:
    return {key for key, pattern in vocabulary.items() if re.search(r"\b(?:" + pattern + r")\b", text, re.I)}


def coverage(candidate: set[str], required: set[str]) -> float:
    return round(100 * len(candidate & required) / len(required), 2) if required else 0.0


def aggregate(group: str, scores: dict[str, float]) -> float:
    return round(sum(scores[key] * weight for key, weight in WEIGHTS[group].items()), 2)


def recency(cv: CVEvidence, today: date) -> float:
    dates = []
    for job in cv.experience:
        start = DateNormalizer.normalize(job.start_date or "")
        ongoing = job.current_position or re.fullmatch(CURRENT, job.end_date or "", re.I)
        end = today.isoformat() if ongoing else DateNormalizer.normalize(job.end_date or "")
        if not start or not end:
            continue

        def boundary(value: str) -> date:
            return date.fromisoformat(
                value + ("-01-01" if len(value) == 4 else "-01" if len(value) == 7 else "")
            )

        first, last = boundary(start), min(today, boundary(end))
        if first < last:
            dates.append(last)
    if not dates:
        return 0.0
    age = (today - max(dates)).days / 365.2425
    return round(100 * 2 ** (-max(0, age - 1) / 5), 2)


def title_fit(cv: CVEvidence, jd: str) -> float:
    levels = [
        (1, r"intern|trainee"),
        (2, r"junior|entry level"),
        (3, r"mid.level"),
        (4, r"senior"),
        (5, r"lead|principal|staff|director"),
    ]

    def level(text: str) -> int:
        return max(
            (n for n, pattern in levels if re.search(r"\b(?:" + pattern + r")\b", text, re.I)), default=0
        )

    roles = {
        "developer": r"developer|engineer|programmer",
        "analyst": r"analyst",
        "manager": r"manager|director",
        "chef": r"chef",
        "nurse": r"nurse",
    }
    target = recognized(jd, roles)
    required = level(jd)
    if not target and not required:
        return 100.0
    scores = []
    for job in cv.experience:
        title = evidence(job.position or "")
        relevance = coverage(recognized(title, roles), target) if target else 100.0
        seniority = min(100, 100 * level(title) / required) if required else 100
        scores.append(relevance * seniority / 100)
    return round(max(scores, default=0), 2)


ROLE_FAMILIES = {
    "backend": r"backend|back.end|api developer",
    "frontend": r"frontend|front.end|react developer",
    "devops": r"devops|site reliability|platform engineer|cloud engineer",
    "ml": r"machine learning|ml engineer|data scientist",
    "data": r"data engineer|data analyst",
    "business": r"business analyst",
    "finance": r"financial analyst|accountant|accounting",
    "hospitality": r"chef|cook|kitchen",
    "software": r"software developer|software engineer|programmer",
    "healthcare": r"nurse|physician|doctor",
}


def relevant_history(cv: CVEvidence, jd: str) -> CVEvidence:
    """Filter positions, never candidate-wide skills, before merging dated intervals."""
    target = recognized(jd, ROLE_FAMILIES)
    if not target and re.search(r"\b(python|fastapi|docker|kubernetes|software|developer)\b", jd, re.I):
        target = {"software"}
    target_domains = recognized(jd, DOMAINS)
    selected = []
    for job in cv.experience:
        title = evidence(job.position or "")
        duties = evidence(
            job.responsibilities if isinstance(job.responsibilities, str) else " ".join(job.responsibilities)
        )
        family = recognized(title, ROLE_FAMILIES)
        domains = recognized(title + " " + duties, DOMAINS)
        if target:
            related = bool(family & target) or (
                target == {"software"} and bool(family & {"backend", "frontend", "devops"})
            )
            # Generic software roles require role-specific evidence in their duties.
            if family == {"software"}:
                related = related or bool(recognized(duties, ROLE_FAMILIES) & target)
        else:
            related = bool(domains & target_domains) if target_domains else bool(title or duties)
        if related:
            selected.append(job)
    return cv.model_copy(update={"experience": selected})


def normalized_weights(weights: dict[str, float], active: dict[str, bool]) -> dict[str, float]:
    total = sum(value for key, value in weights.items() if active[key])
    return {key: value / total if active[key] and total else 0.0 for key, value in weights.items()}


def contextual_requirements(jd: str) -> str:
    """Exclude administrative requirements from duties/summary semantic comparisons."""
    clauses = re.split(r"[;\n]|(?<=[.!?])\s+", jd)
    selected = [
        clause
        for clause in clauses
        if not re.search(
            r"required skills\s*:|\b(?:bachelor|master|phd|degree|certification|minimum|years? of experience)\b",
            clause,
            re.I,
        )
    ]
    return "\n".join(selected).strip() or jd
