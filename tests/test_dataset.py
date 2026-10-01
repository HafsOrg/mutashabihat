"""Invariants of the committed data/. These need no source files."""

import json
from pathlib import Path

import pytest

from mutashabihat.dataset import RANK, Dataset
from mutashabihat.gold import GOLD
from mutashabihat.quran import skeleton

DATA = Path(__file__).resolve().parents[1] / "data"


def order(key: str) -> tuple[int, int]:
    s, a = key.split(":")
    return int(s), int(a)


@pytest.fixture(scope="module")
def links() -> list[dict]:
    return json.loads((DATA / "links.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ds() -> Dataset:
    return Dataset.load()


def test_keys_are_valid_ordered_and_unique(links):
    seen = set()
    for L in links:
        for k in (L["a"], L["b"]):
            s, a = order(k)
            assert 1 <= s <= 114 and 1 <= a <= 286, k
        assert order(L["a"]) < order(L["b"]), (L["a"], L["b"])
        assert (L["a"], L["b"]) not in seen
        seen.add((L["a"], L["b"]))


def test_every_link_has_a_known_tier_and_matching_evidence(links):
    for L in links:
        assert L["confidence"] in RANK
        level = L["evidence"]["level"]
        if L["confidence"] == "unverified":
            assert level == "weak"
        if level == "weak":
            assert L["confidence"] in ("low", "unverified")
        if L["confidence"] in ("high", "medium"):
            assert level in ("strong", "moderate")
        assert L["families"]


def test_strong_evidence_is_never_below_medium_unless_text_only_single_family(links):
    for L in links:
        if L["evidence"]["level"] == "strong":
            assert L["confidence"] in ("high", "medium"), (L["a"], L["b"])


def test_rejected_pairs_are_not_in_links(links):
    rejected = {(r["a"], r["b"]) for r in json.loads((DATA / "rejected.json").read_text(encoding="utf-8"))}
    assert not rejected & {(L["a"], L["b"]) for L in links}
    assert all(r["evidence"]["level"] == "weak" for r in json.loads((DATA / "rejected.json").read_text(encoding="utf-8")))


def test_by_ayah_index_is_symmetric_and_complete(ds, links):
    assert sum(len(v) for v in ds.index.values()) == 2 * len(links)
    for (a, b), L in list(ds.links.items())[:500]:
        assert any(e["to"] == b and e["confidence"] == L["confidence"] for e in ds.index[a])
        assert any(e["to"] == a for e in ds.index[b])


def test_related_respects_min_confidence_and_orders_best_first(ds):
    high = ds.related("2:49", "high")
    assert high and all(e["confidence"] == "high" for e in high)
    everything = ds.related("2:49", "unverified")
    ranks = [RANK[e["confidence"]] for e in everything]
    assert ranks == sorted(ranks)


def test_link_lookup_works_in_either_order(ds):
    assert ds.link("7:141", "2:49") is ds.link("2:49", "7:141") is not None


def test_well_known_pairs_are_present_at_medium_or_better(ds):
    for a, b, note in GOLD:
        rec = ds.link(a, b)
        assert rec is not None, (a, b, note)
        assert rec["confidence"] in ("high", "medium"), (a, b, note, rec["confidence"])


def test_diff_texts_reflect_the_known_swap(ds):
    diffs = ds.link("2:49", "7:141")["diffs"]
    assert any(skeleton(d["a_text"]) == "يذبحون" and skeleton(d["b_text"]) == "يقتلون" for d in diffs)


def test_meta_counts_match_the_files(links):
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    assert meta["counts"]["links"] == len(links)
    by_tier = {}
    for L in links:
        by_tier[L["confidence"]] = by_tier.get(L["confidence"], 0) + 1
    assert meta["counts"]["links_by_confidence"] == by_tier
    assert meta["counts"]["rejected"] == len(json.loads((DATA / "rejected.json").read_text(encoding="utf-8")))


def test_phrase_occurrences_have_a_status():
    phrases = json.loads((DATA / "phrases.json").read_text(encoding="utf-8"))
    ok = {"identical", "variant", "unrelated", "unanchored"}
    assert all(o["status"] in ok for p in phrases for o in p["occurrences"])


def test_identical_groups_are_really_groups():
    groups = json.loads((DATA / "identical_groups.json").read_text(encoding="utf-8"))
    assert all(len(g["ayahs"]) >= 2 for g in groups)
    assert any(len(g["ayahs"]) >= 30 for g in groups)  # the Ar-Rahman refrain
