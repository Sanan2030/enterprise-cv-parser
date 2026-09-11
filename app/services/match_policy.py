"""Deterministic evidence and constraint guards, independent of model predictions."""

import re
import unicodedata

CLAUSES = re.compile(r"[;\n]+|(?<=[.!?])\s+")
INSTRUCTION = re.compile(
    r"(?i)(?:system\s*(?:instruction|prompt)|ignore\s+(?:all\s+|previous\s+|job\s+)?(?:instructions|requirements)|match_percentage|<\|?system\|?>)"
)
NEGATIVE = re.compile(
    r"(?i)\b(?:must\s+not|mustn't|shall\s+not|no|without|never|do\s+not|don't|lack(?:s|ing)?)\b"
)


def clean_text(text: str) -> tuple[str, bool]:
    text = "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")
    changed = False
    lines = []
    for line in text.splitlines():
        if INSTRUCTION.search(line):
            line = line[: INSTRUCTION.search(line).start()].strip()
            changed = True
        tokens = re.findall(r"\w+", line.casefold())
        if len(tokens) >= 40 and len(set(tokens)) / len(tokens) < 0.18 and not re.search(r"[.!?]", line):
            changed = True
            continue
        lines.append(line)
    clauses = [s.strip() for s in CLAUSES.split("\n".join(lines)) if s.strip()]
    unique = list(dict.fromkeys(clauses))
    return "\n".join(unique), changed or len(unique) != len(clauses)


def positive_evidence(text: str) -> str:
    return "\n".join(clause for clause in CLAUSES.split(text) if not NEGATIVE.search(clause))


def job_constraints(text: str, extract_skills) -> tuple[str, set[str]]:
    positive, forbidden = [], set()
    for clause in CLAUSES.split(text):
        if re.search(r"(?i)not required|optional|nice to have", clause):
            continue
        if re.search(
            r"(?i)must\s+not|mustn't|shall\s+not|prohibited|strictly\s+no|\bno\s+\w+\s+experience\b", clause
        ):
            forbidden.update(extract_skills(clause))
        else:
            positive.append(clause)
    return "\n".join(positive), forbidden


def conflicting_domain(cv: str, jd: str) -> bool:
    """Only explicit contradictory acronym expansions trigger this guard."""
    expansions = {
        "cpr": [
            r"cardiopulmonary|resuscitation|patient care",
            r"creative production|advertising|film production",
        ],
        "ba": [r"business analys", r"bachelor of arts"],
    }
    for acronym, domains in expansions.items():
        if re.search(rf"\b{acronym}\b", cv, re.I) and re.search(rf"\b{acronym}\b", jd, re.I):
            candidate = {i for i, pattern in enumerate(domains) if re.search(pattern, cv, re.I)}
            required = {i for i, pattern in enumerate(domains) if re.search(pattern, jd, re.I)}
            if candidate and required and candidate.isdisjoint(required):
                return True
    return False
