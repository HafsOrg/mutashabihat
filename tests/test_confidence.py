import pytest

from mutashabihat.build import confidence


@pytest.mark.parametrize(
    "level, families, expected",
    [
        ("strong", {"qul", "furooq"}, "high"),  # two independent families
        ("strong", {"waqar"}, "high"),  # human-curated
        ("strong", {"qul"}, "medium"),  # one algorithmic family
        ("strong", {"furooq"}, "medium"),
        ("strong", {"text"}, "medium"),  # mined links are not independent evidence
        ("strong", {"qul", "text"}, "medium"),  # ...so text + one family is still one family
        ("moderate", {"qul", "furooq"}, "medium"),
        ("moderate", {"qul"}, "low"),
        ("moderate", {"waqar"}, "low"),
        ("weak", {"waqar", "qul"}, "low"),
        ("weak", {"qul", "furooq"}, "low"),
        ("weak", {"waqar"}, "unverified"),
        ("weak", {"srmdn"}, "unverified"),
        ("weak", {"qul"}, None),  # rejected
        ("weak", {"furooq"}, None),
    ],
)
def test_confidence_truth_table(level, families, expected):
    assert confidence(level, frozenset(families)) == expected
