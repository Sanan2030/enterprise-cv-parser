import re

from app.extraction.layout_engine import LayoutBlock
from app.intelligence.provenance import provenance
from app.normalization.date_normalizer import RANGE_PATTERN, DateNormalizer
from app.parsing.experience_parser import group_entries
from app.schemas.resume import Education


class EducationParser:
    def parse(self, blocks: list[LayoutBlock]) -> list[Education]:
        result = []
        for group in group_entries(blocks):
            text = "\n".join(b.text for b in group)
            dated = RANGE_PATTERN.search(text)
            start, end, _ = DateNormalizer.normalize_span(dated[0]) if dated else (None, None, False)
            parts = [
                p.strip(" -–—") for p in re.split(r"\n|\|", RANGE_PATTERN.sub("", text)) if p.strip(" -–—")
            ]
            institution = next(
                (
                    p
                    for p in parts
                    if re.search(
                        r"universit|university|college|institute|məktəb|университет|институт|академ", p, re.I
                    )
                ),
                parts[0] if parts else None,
            )
            degree = next(
                (
                    p
                    for p in parts
                    if re.search(
                        r"bachelor|master|ph\.?d|b\.?sc|m\.?sc|bakalavr|magistr|lisans|бакалавр|магистр",
                        p,
                        re.I,
                    )
                ),
                None,
            )
            gpa = re.search(r"\bGPA\s*:?\s*([\d.,]+(?:\s*/\s*[\d.,]+)?)", text, re.I)
            field = None
            if institution and institution.casefold() in {"university", "college", "institute"}:
                index = parts.index(institution)
                if index > 0:
                    institution = parts[index - 1] + " " + institution
            if degree and ":" in degree:
                degree, field = [p.strip() for p in degree.split(":", 1)]
            if degree is None:
                field = (
                    next(
                        (
                            p
                            for p in parts
                            if re.search(
                                r"information tech?nology|computer science|engineering|business administration",
                                p,
                                re.I,
                            )
                            and p not in institution
                        ),
                        None,
                    )
                    if institution
                    else None
                )
                if field:
                    field = re.sub(r"\bTecnology\b", "Technology", field, flags=re.I)
                elif len(parts) > 1 and parts[1] != institution and parts[1].casefold() != "university":
                    degree = parts[1]
            result.append(
                Education(
                    institution=institution,
                    degree=degree,
                    field_of_study=field,
                    start_date=start,
                    end_date=end,
                    graduation_date=end,
                    gpa=gpa[1] if gpa else None,
                    provenance=provenance(group[0], 0.7),
                )
            )
        return result
