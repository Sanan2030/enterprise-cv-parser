import re
from datetime import date

import dateparser

MONTHS = dict(
    zip(
        "yanvar fevral mart aprel may iyun iyul avqust sentyabr oktyabr noyabr dekabr".split(),
        "january february march april may june july august september october november december".split(),
    )
)
CURRENT = r"(?:present|current|now|hal[- ]hazırda|hazırda|indiki|devam|günümüz|halen|по настоящее время|настоящее время|н\.\s*в\.)"
MONTH = r"[^\W\d_]{3,12}\.?"
DATE_TOKEN = rf"(?:\d{{4}}[-/.]\d{{1,2}}(?:[-/.]\d{{1,2}})?|\d{{1,2}}[/.]\d{{1,2}}[/.]\d{{4}}|\d{{1,2}}[/.]\d{{4}}|(?:\d{{1,2}}\s+)?{MONTH}\s+\d{{4}}|\d{{4}})"
RANGE_PATTERN = re.compile(
    rf"(?<!\w)(?P<start>{DATE_TOKEN})\s*(?:–|—|\s+-\s+|-(?=\d{{4}}\b)|\bto\b|\bдо\b)\s*(?P<end>{CURRENT}|{DATE_TOKEN})(?!\w)",
    re.I,
)


class DateNormalizer:
    @staticmethod
    def normalize(value: str) -> str | None:
        text = value.strip().casefold()
        if re.fullmatch(CURRENT, text, re.I) or not re.search(r"\b(?:19|20)\d{2}\b", text):
            return None
        if re.fullmatch(r"(?:19|20)\d{2}", text):
            return text
        numeric = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text)
        if numeric:
            a, b, year = map(int, numeric.groups())
            if a <= 12 and b <= 12 and a != b:
                return None
            day, month = (a, b) if a > 12 else (b, a)
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None
        iso = re.fullmatch(r"(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?", text)
        month_year = re.fullmatch(r"(\d{1,2})[/.](\d{4})", text)
        if iso or month_year:
            if iso:
                year, month = int(iso[1]), int(iso[2])
                day = int(iso[3] or 1)
            else:
                year, month, day = int(month_year[2]), int(month_year[1]), 1
            try:
                parsed = date(year, month, day)
                return parsed.isoformat() if iso and iso[3] else parsed.strftime("%Y-%m")
            except ValueError:
                return None
        for source, target in MONTHS.items():
            text = re.sub(rf"\b{source}\b", target, text)
        parsed = dateparser.parse(
            text,
            languages=["en", "tr", "ru"],
            settings={"PREFER_DAY_OF_MONTH": "first", "REQUIRE_PARTS": ["year", "month"]},
        )
        if parsed is None:
            return None
        return parsed.strftime("%Y-%m-%d" if re.match(r"\d{1,2}\s", text) else "%Y-%m")

    @staticmethod
    def normalize_span(value: str) -> tuple[str | None, str | None, bool]:
        match = RANGE_PATTERN.search(value)
        if match is None:
            return DateNormalizer.normalize(value), None, False
        current = bool(re.fullmatch(CURRENT, match["end"], re.I))
        start = DateNormalizer.normalize(match["start"])
        end = None if current else DateNormalizer.normalize(match["end"])
        if start and end and start[:7] > end[:7]:
            return None, None, False
        return start, end, current
