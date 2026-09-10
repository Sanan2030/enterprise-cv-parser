from datetime import date

import pytest

from app.normalization.duration import calculate_duration


@pytest.mark.parametrize(
    "start,end,current,expected",
    [
        ("2026-02", None, True, "7 mos"),
        ("2025-04", "2025-08", False, "4 mos"),
        ("2025-06", "2025-09", False, "3 mos"),
        ("2021-01", "2023-09", False, "2 yrs 8 mos"),
        ("2026-09-01", "2026-09-10", False, "9 days"),
        ("2024-02-29", "2025-02-28", False, "11 mos"),
        ("2024-01-31", "2024-02-29", False, "29 days"),
        ("2026-09", "2026-09", False, "Less than 1 month"),
        ("2026-09-11", None, True, ""),
        ("2024", "2025", False, ""),
        ("2024-02-30", "2024-04-01", False, ""),
        ("2025-13", "2026-01", False, ""),
        ("2025-06", "2025-04", False, ""),
        (None, None, False, ""),
    ],
)
def test_elapsed_duration(start, end, current, expected):
    assert calculate_duration(start, end, current=current, today=date(2026, 9, 10)) == expected
