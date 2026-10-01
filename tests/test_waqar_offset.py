import pytest

from mutashabihat.quran import Quran
from mutashabihat.sources import detect_waqar_offset


def tiny_quran(texts: list[str]) -> Quran:
    keys = tuple(f"1:{i + 1}" for i in range(len(texts)))
    skel = {k: tuple(t.split()) for k, t in zip(keys, texts)}
    return Quran(keys, dict(skel), skel, {k: i + 1 for i, k in enumerate(keys)})


TEXTS = ["x1 y1 z1", "p q r s", "x1 y1 z1 w", "m n o", "p q r s t", "m n o u", "k l", "k l v"]


def entries(pairs):
    return {"1": [{"src": {"ayah": a}, "muts": [{"ayah": b}]} for a, b in pairs]}


def test_zero_based_numbers_are_detected():
    # 0-based (0, 2) is 1-based ayahs (1, 3): "x1 y1 z1" vs "x1 y1 z1 w". Five links so the juz is usable.
    pairs = [(0, 2), (1, 4), (3, 5), (6, 7), (0, 2)]
    offset, report = detect_waqar_offset(entries(pairs), tiny_quran(TEXTS))
    assert offset == 1
    assert report["1"]["mean_ratio_offset_1"] > report["1"]["mean_ratio_offset_0"]


def test_one_based_numbers_are_refused():
    pairs = [(1, 3), (2, 5), (4, 6), (7, 8), (1, 3)]
    with pytest.raises(SystemExit):
        detect_waqar_offset(entries(pairs), tiny_quran(TEXTS))
