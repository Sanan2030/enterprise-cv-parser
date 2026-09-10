"""Read explicit labels without consuming adjacent fields."""

import re

from app.normalization.date_normalizer import CURRENT, DateNormalizer


def labeled(text: str, *labels: str) -> str | None:
    match = re.search(
        r"(?:^|[\n|;])\s*(?:" + "|".join(re.escape(s) for s in labels) + r")\s*:\s*([^\n|;]+)", text, re.I
    )
    return match[1].strip() if match else None


def labeled_dates(text: str) -> tuple[str | None, str | None, bool]:
    start = labeled(text, "start date", "from")
    end = labeled(text, "end date", "to")
    current = bool(end and re.fullmatch(CURRENT, end, re.I))
    begin, finish = DateNormalizer.normalize(start or ""), DateNormalizer.normalize(end or "")
    if begin and finish and begin > finish:
        return None, None, False
    return begin, finish, current
