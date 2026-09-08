import pytest

from app.normalization.date_normalizer import DateNormalizer


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Yanvar 2024", "2024-01"),
        ("Ocak 2024", "2024-01"),
        ("январь 2024", "2024-01"),
        ("January 2024", "2024-01"),
        ("2024", "2024"),
        ("2024-02", "2024-02"),
        ("02/2024", "2024-02"),
        ("2024-02-29", "2024-02-29"),
        ("31/12/2024", "2024-12-31"),
        ("2023-02-29", None),
        ("03/04/2024", None),
        ("January", None),
        ("nonsense", None),
    ],
)
def test_date(raw, expected):
    assert DateNormalizer.normalize(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Jan 2022 - Present", ("2022-01", None, True)),
        ("Yanvar 2020 – Dekabr 2021", ("2020-01", "2021-12", False)),
        ("Ocak 2020 - halen", ("2020-01", None, True)),
        ("январь 2020 — настоящее время", ("2020-01", None, True)),
        ("2018-2022", ("2018", "2022", False)),
        ("2020-01 - 2021-12", ("2020-01", "2021-12", False)),
        ("2024 - 2020", (None, None, False)),
    ],
)
def test_ranges(raw, expected):
    assert DateNormalizer.normalize_span(raw) == expected
