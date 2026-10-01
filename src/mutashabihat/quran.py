"""Word-level Quran text and the normalisation every comparison uses.

The text is QUL's QPC Hafs script. QUL's own word ranges index into the same
script, and using one script for every comparison means identical words always
compare equal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_MARKS = re.compile("[ً-ٟۖ-ۭـ࣓-ࣿ]")
_LETTERS = str.maketrans(
    {"ٱ": "ا", "أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و", "ئ": "ي", "ى": "ي", "ی": "ي"}
)
_VERSE_NUMBER = re.compile("[٠-٩]+")
HIZB_SIGN = "۞"  # standalone marker token, not a word


def skeleton(word: str) -> str:
    """Strip vowel marks and unify letter variants so equal words compare equal.

    The dagger alef becomes a real alef so Uthmani spellings line up with each
    other (ٱلۡكِتَٰبُ and ٱلۡكِتَٰبَ both give الكتاب). Hamza carriers collapse to their base
    letter and bare hamza is dropped.
    """
    word = word.replace("ٰ", "ا")
    word = _MARKS.sub("", word)
    return word.translate(_LETTERS).replace("ء", "")


def ayah_words(text: str) -> list[str]:
    """Split a QPC ayah into words, dropping the trailing verse number and ۞ markers."""
    tokens = text.replace("\xa0", " ").split()
    if tokens and _VERSE_NUMBER.fullmatch(tokens[-1]):
        tokens = tokens[:-1]
    return [t for t in tokens if t != HIZB_SIGN]


def key_order(key: str) -> tuple[int, int]:
    s, a = key.split(":")
    return int(s), int(a)


@dataclass(frozen=True)
class Quran:
    keys: tuple[str, ...]  # mushaf order, "surah:ayah"
    words: dict[str, tuple[str, ...]]  # diacritised QPC words
    skel: dict[str, tuple[str, ...]]  # skeleton words
    abs_id: dict[str, int]  # 1-based absolute ayah number

    @classmethod
    def load(cls, path: str | Path) -> "Quran":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = sorted(raw.values(), key=lambda r: r["id"])
        keys = tuple(r["verse_key"] for r in rows)
        assert [r["id"] for r in rows] == list(range(1, len(rows) + 1)), "ayah ids must be 1..N"
        assert list(keys) == sorted(keys, key=key_order), "ids must follow mushaf order"
        words = {r["verse_key"]: tuple(ayah_words(r["text"])) for r in rows}
        skel = {k: tuple(skeleton(w) for w in ws) for k, ws in words.items()}
        assert all(all(s for s in sk) for sk in skel.values()), "empty skeleton word"
        return cls(keys, words, skel, {r["verse_key"]: r["id"] for r in rows})

    def key_at(self, abs_id: int) -> str | None:
        """Key for a 1-based absolute ayah number, or None when out of range."""
        return self.keys[abs_id - 1] if 1 <= abs_id <= len(self.keys) else None

    def ordered(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if self.abs_id[a] <= self.abs_id[b] else (b, a)

    def seq(self, keys: list[str] | tuple[str, ...]) -> list[str]:
        """Concatenated skeleton words of consecutive ayahs (for multi-ayah blocks)."""
        out: list[str] = []
        for k in keys:
            out.extend(self.skel[k])
        return out
