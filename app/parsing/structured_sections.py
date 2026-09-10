"""Preserve multiline certification and project records without inventing fields."""

import re

from app.extraction.layout_engine import LayoutBlock
from app.normalization.date_normalizer import DateNormalizer
from app.schemas.resume import Certification, Project


def records(blocks: list[LayoutBlock], labels: dict[str, str], name_key: str) -> list[dict]:
    result: list[dict] = []
    current: dict = {}
    previous = None
    for block in blocks:
        text = block.text.strip().lstrip("• ")
        label, colon, content = text.partition(":")
        key = labels.get(label.casefold()) if colon else None
        if current and (
            key == name_key
            or (
                not key
                and (
                    block.is_bold
                    or (previous and block.y0 - previous.y1 > 12)
                    or name_key == "certification_name"
                )
            )
        ):
            result.append(current)
            current = {}
        if key:
            current[key] = content.strip()
        elif not current:
            current[name_key] = text
        else:
            current["description"] = (current.get("description", "") + "\n" + text).strip()
        previous = block
    if current:
        result.append(current)
    return result


def parse_certifications(blocks: list[LayoutBlock]) -> list[Certification]:
    labels = {
        "certificate": "certification_name",
        "certification": "certification_name",
        "certificate name": "certification_name",
        "name": "certification_name",
        "issuer": "issuer",
        "issuing organization": "issuer",
        "organization": "issuer",
        "issue date": "issue_date",
        "issued": "issue_date",
        "credential id": "credential_id",
        "credential url": "credential_url",
    }
    result = []
    for entry in records(blocks, labels, "certification_name"):
        entry.pop("description", None)
        if "issue_date" in entry:
            entry["issue_date"] = DateNormalizer.normalize(entry["issue_date"])
        result.append(Certification(**entry))
    return result


def parse_projects(blocks: list[LayoutBlock]) -> list[Project]:
    labels = {
        "project": "project_name",
        "project name": "project_name",
        "name": "project_name",
        "description": "description",
        "technologies": "technologies",
        "tech stack": "technologies",
        "role": "role",
        "url": "url",
        "github": "github_url",
    }
    result = []
    for entry in records(blocks, labels, "project_name"):
        if "technologies" in entry:
            entry["technologies"] = [s.strip() for s in re.split(r"[,;]", entry["technologies"]) if s.strip()]
        result.append(Project(**entry))
    return result
