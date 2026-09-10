"""Elapsed employment duration without inventing missing calendar dates."""

import re
from datetime import date, datetime, timezone


def calculate_duration(
    start: str | None, end: str | None, *, current: bool = False, today: date | None = None
) -> str:
    today = today or datetime.now(timezone.utc).date()
    if not start or not re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", start):
        return ""
    end = today.isoformat() if current else end
    if not end or not re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", end):
        return ""
    try:
        first = date.fromisoformat(start if len(start) == 10 else start + "-01")
        last = date.fromisoformat(end if len(end) == 10 else end + "-01")
    except ValueError:
        return ""
    if last < first:
        return ""
    months = (last.year - first.year) * 12 + last.month - first.month
    if len(start) == len(end) == 10:
        months -= last.day < first.day
        if months == 0:
            days = (last - first).days
            return f"{days} day" + ("s" if days != 1 else "")
    years, months = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} yr" + ("s" if years != 1 else ""))
    if months:
        parts.append(f"{months} mo" + ("s" if months != 1 else ""))
    return " ".join(parts) or "Less than 1 month"
