"""Checks that need the staged sources (skipped when sources/ is absent)."""

import json
import random
from pathlib import Path

import pytest

from mutashabihat import build as B
from mutashabihat.compare import compare, lexical_evidence
from mutashabihat.quran import Quran

ROOT = Path(__file__).resolve().parents[1]
QPC = ROOT / "sources" / "qul" / "qpc-hafs.json"
pytestmark = pytest.mark.skipif(not QPC.exists(), reason="sources/ not staged (see scripts/stage_sources.py)")


@pytest.fixture(scope="module")
def q() -> Quran:
    return Quran.load(QPC)


def test_text_base_is_the_whole_mushaf(q):
    assert len(q.keys) == 6236
    assert q.keys[0] == "1:1" and q.keys[-1] == "114:6"
    assert len(q.skel["2:255"]) == 50 or len(q.skel["2:255"]) > 40


def test_stored_evidence_can_be_recomputed_from_the_text(q):
    links = [json.loads(line.rstrip(",")) for line in (ROOT / "data" / "links.json").read_text(encoding="utf-8").splitlines()[1:-1]]
    for L in random.Random(7).sample(links, 150):
        c = compare(list(q.skel[L["a"]]), list(q.skel[L["b"]]))
        assert L["evidence"]["level"] == lexical_evidence(c)
        assert L["evidence"]["fuzzy_run"] == c["fuzzy_run"] and L["evidence"]["ratio"] == c["ratio"]
        assert L["confidence"] == B.confidence(L["evidence"]["level"], frozenset(L["families"]))


def test_build_is_reproducible(tmp_path):
    B.build(tmp_path)
    for name in ("links.json", "rejected.json", "phrases.json", "blocks.json", "by_ayah.json", "meta.json"):
        assert (tmp_path / name).read_bytes() == (ROOT / "data" / name).read_bytes(), name
