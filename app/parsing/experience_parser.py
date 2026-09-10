import re

from app.extraction.layout_engine import LayoutBlock
from app.intelligence.provenance import provenance
from app.normalization.date_normalizer import RANGE_PATTERN, DateNormalizer
from app.normalization.duration import calculate_duration
from app.schemas.resume import WorkExperience


def group_entries(blocks: list[LayoutBlock]) -> list[list[LayoutBlock]]:
    """Split at dated headers; associate separate preceding bold title/company lines."""
    groups: list[list[LayoutBlock]] = []
    current: list[LayoutBlock] = []
    dated = False
    for block in blocks:
        match = RANGE_PATTERN.search(block.text)
        if match and dated:
            carried = []
            if match.start() == 0:
                while current and len(carried) < 2 and not RANGE_PATTERN.search(current[-1].text):
                    tail = current[-1]
                    if tail.text.startswith(("-", "•", "*")) or len(tail.text) > 90 or not tail.is_bold:
                        break
                    carried.insert(0, current.pop())
            if current:
                groups.append(current)
            current = carried
        elif (
            dated
            and block.is_bold
            and current
            and block.y0 - current[-1].y1 > 12
            and not block.text.startswith(("-", "•"))
        ):
            groups.append(current)
            current = []
            dated = False
        current.append(block)
        dated = dated or bool(match)
    if current:
        groups.append(current)
    return groups


class ExperienceParser:
    def parse(self, blocks: list[LayoutBlock]) -> list[WorkExperience]:
        result = []
        for group in group_entries(blocks):
            dated = next((RANGE_PATTERN.search(b.text) for b in group if RANGE_PATTERN.search(b.text)), None)
            start, end, current = DateNormalizer.normalize_span(dated[0]) if dated else (None, None, False)
            header = []
            responsibilities = []
            for b in group:
                is_bullet = b.text.lstrip().startswith(("•", "-", "*"))
                clean = RANGE_PATTERN.sub("", b.text).strip(" |,–—-")
                if b.method == "ocr":
                    clean = re.sub(r"^[eo]\s+(?=As(?:a|\s))", "", clean)
                    clean = re.sub(r"^Asa\s+", "As a ", clean)
                if not clean:
                    continue
                if len(header) < 2 and not is_bullet and len(clean) < 120:
                    header.extend(
                        part.strip() for part in re.split(r"\s*\|\s*|\s+at\s+", clean) if part.strip()
                    )
                else:
                    responsibilities.append(clean.lstrip("•*- "))
            result.append(
                WorkExperience(
                    job_title=header[0] if header else None,
                    company=header[1] if len(header) > 1 else None,
                    start_date=start,
                    end_date=end,
                    current_position=current,
                    duration=calculate_duration(start, end, current=current),
                    responsibilities=responsibilities,
                    provenance=provenance(group[0], 0.65),
                )
            )
        return result
