"""Read the built dataset: look up what is related to an ayah.

    from mutashabihat.dataset import Dataset
    ds = Dataset.load()                      # reads data/
    ds.related("2:49")                       # medium confidence and up, best first
    ds.related("2:49", min_confidence="high")
    ds.link("2:49", "7:141")                 # full record: evidence, shared words, differences
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
RANK = {"high": 0, "medium": 1, "low": 2, "unverified": 3}


def _key_order(key: str) -> tuple[int, int]:
    s, a = key.split(":")
    return int(s), int(a)


@dataclass
class Dataset:
    links: dict[tuple[str, str], dict]
    index: dict[str, list[dict]]

    @classmethod
    def load(cls, data_dir: str | Path = DATA) -> "Dataset":
        d = Path(data_dir)
        links = {(r["a"], r["b"]): r for r in json.loads((d / "links.json").read_text(encoding="utf-8"))}
        index = json.loads((d / "by_ayah.json").read_text(encoding="utf-8"))
        return cls(links, index)

    def related(self, ayah: str, min_confidence: str = "medium") -> list[dict]:
        """Ayahs related to `ayah` at or above `min_confidence`, best first."""
        limit = RANK[min_confidence]
        return [e for e in self.index.get(ayah, []) if RANK[e["confidence"]] <= limit]

    def link(self, x: str, y: str) -> dict | None:
        """The full record for a pair, in either order."""
        a, b = sorted((x, y), key=_key_order)
        return self.links.get((a, b))
