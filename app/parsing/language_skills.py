"""Language entries with spatially associated proficiency labels."""

import re

from app.extraction.layout_engine import LayoutBlock
from app.schemas.resume import LanguageSkill

LEVEL = re.compile(
    r"\b(?:[ABC][12]|native|fluent|advanced|intermediate|beginner|basic|proficient|"
    r"ana dili|orta|начальный|средний|родной)\b",
    re.I,
)


def parse_languages(blocks: list[LayoutBlock]) -> list[LanguageSkill]:
    result = []
    names: list[tuple[LayoutBlock, LanguageSkill]] = []
    for block in blocks:
        for item in re.split(r"[,;]", block.text):
            item = item.strip().lstrip("• ")
            if not item or re.search(r"\d{4}|https?://", item):
                continue
            level = LEVEL.search(item)
            if level and level.start() == 0:
                continue
            parts = re.split(r"\s*[:–—-]\s*", item, maxsplit=1)
            name = parts[0].strip()
            proficiency = parts[1] if len(parts) > 1 else None
            if level and proficiency is None:
                name = item[: level.start()].strip(" ()")
                proficiency = item[level.start() :].strip()
            if not name or len(name.split()) > 4:
                continue
            cefr = re.search(r"\b[ABC][12]\b", proficiency or "", re.I)
            entry = LanguageSkill(
                language=name, proficiency=proficiency, cefr_level=cefr[0].upper() if cefr else None
            )
            names.append((block, entry))
            result.append(entry)
    for block in blocks:
        if not LEVEL.match(block.text.strip()):
            continue
        candidates = [
            (abs(block.x0 - b.x0), block.y0 - b.y0, entry)
            for b, entry in names
            if b.page_num == block.page_num
            and 0 <= block.y0 - b.y0 <= 50
            and abs(block.x0 - b.x0) < 25
            and entry.proficiency is None
        ]
        if candidates:
            entry = min(candidates, key=lambda item: item[:2])[2]
            entry.proficiency = block.text.strip()
            cefr = re.search(r"\b[ABC][12]\b", block.text, re.I)
            entry.cefr_level = cefr[0].upper() if cefr else None
    return result
