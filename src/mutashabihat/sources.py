"""Loaders that turn each upstream dataset into uniform claims about ayah pairs.

A claim says "source S relates ayah A to ayah B". It carries no truth value;
build.py checks every claim against the Quran text before it counts.

Source families (used to count independent agreement):
    qul     QUL matching-ayah rows and QUL shared phrases (same provider)
    waqar   Waqar144's hand-curated list
    srmdn   srmdn's hand-curated pairs
    furooq  Furooq's similarity groups
"""

from __future__ import annotations

import itertools
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .compare import compare
from .quran import Quran

MAX_PHRASE_AYAHS = 10  # larger phrase groups are refrains/formulae: kept in the phrase layer only
MAX_FUROOQ_GROUP = 10  # larger groups are loose clusters, not pairwise evidence


@dataclass(frozen=True)
class Claim:
    a: str
    b: str
    family: str
    source: str
    meta: dict = field(default_factory=dict, compare=False, hash=False)


def _load(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pair(q: Quran, x: str, y: str) -> tuple[str, str] | None:
    if x == y or x not in q.abs_id or y not in q.abs_id:
        return None
    return q.ordered(x, y)


# --------------------------------------------------------------------- QUL


def load_qul_matching(path: str | Path, q: Quran) -> list[Claim]:
    out = []
    for src, rows in _load(path).items():
        for row in rows:
            p = _pair(q, src, row["matched_ayah_key"])
            if p:
                out.append(
                    Claim(
                        *p,
                        "qul",
                        "qul_matching",
                        {
                            "from": src,
                            "score": row["score"],
                            "coverage": row["coverage"],
                            "matched_words": row["matched_words_count"],
                        },
                    )
                )
    return out


def load_qul_phrases(path: str | Path, q: Quran) -> tuple[list[Claim], dict[str, dict]]:
    """Pair claims from small phrase groups, plus every phrase for the phrase layer."""
    phrases = _load(path)
    claims: list[Claim] = []
    for pid, p in phrases.items():
        ayahs = sorted(p["ayah"], key=lambda k: q.abs_id.get(k, 0))
        if 2 <= len(ayahs) <= MAX_PHRASE_AYAHS:
            for x, y in itertools.combinations(ayahs, 2):
                pr = _pair(q, x, y)
                if pr:
                    claims.append(Claim(*pr, "qul", "qul_phrase", {"phrase_id": int(pid)}))
    return claims, phrases


# ------------------------------------------------------------------- Waqar


@dataclass
class WaqarData:
    claims: list[Claim]
    blocks: list[dict]  # multi-ayah entries
    offset: int
    offset_report: dict
    dropped_out_of_range: int


def _as_list(x) -> list[int]:
    return list(x) if isinstance(x, list) else [x]


def detect_waqar_offset(entries: dict[str, list[dict]], q: Quran) -> tuple[int, dict]:
    """Waqar's ayah numbers are absolute, but 0-based. Measure it instead of assuming it.

    For every juz file, compare the mean word-sequence similarity of the linked
    ayahs under offset 0 and offset +1. A real mutashabih pair is far more
    similar under the right offset.
    """
    report: dict[str, dict] = {}
    for juz, ents in entries.items():
        scores = {0: [], 1: []}
        for e in ents:
            s, ms = _as_list(e["src"]["ayah"]), e["muts"]
            if len(s) != 1:
                continue
            for m in ms:
                t = _as_list(m["ayah"])
                if len(t) != 1:
                    continue
                for off in (0, 1):
                    ka, kb = q.key_at(s[0] + off), q.key_at(t[0] + off)
                    if ka and kb:
                        scores[off].append(compare(list(q.skel[ka]), list(q.skel[kb]))["ratio"])
        report[juz] = {
            "links": len(scores[0]),
            "mean_ratio_offset_0": round(statistics.fmean(scores[0]), 3) if scores[0] else None,
            "mean_ratio_offset_1": round(statistics.fmean(scores[1]), 3) if scores[1] else None,
        }
    usable = [r for r in report.values() if r["links"] >= 5]
    if not all(r["mean_ratio_offset_1"] > r["mean_ratio_offset_0"] for r in usable):
        raise SystemExit("Waqar offset is not consistently +1; inspect offset_report before building")
    return 1, report


def load_waqar(path: str | Path, q: Quran) -> WaqarData:
    entries = _load(path)
    offset, report = detect_waqar_offset(entries, q)
    claims: list[Claim] = []
    blocks: list[dict] = []
    bad = 0
    for ents in entries.values():
        for e in ents:
            side_a = [q.key_at(n + offset) for n in _as_list(e["src"]["ayah"])]
            for m in e["muts"]:
                side_b = [q.key_at(n + offset) for n in _as_list(m["ayah"])]
                if None in side_a or None in side_b:
                    bad += 1
                    continue
                ctx = bool(e.get("ctx"))
                if len(side_a) == 1 and len(side_b) == 1:
                    p = _pair(q, side_a[0], side_b[0])
                    if p:
                        claims.append(Claim(*p, "waqar", "waqar", {"ctx": ctx}))
                else:
                    blocks.append({"a": side_a, "b": side_b, "ctx": ctx})
    return WaqarData(claims, blocks, offset, report, bad)


# ------------------------------------------------------------------- srmdn


@dataclass
class SrmdnData:
    claims: list[Claim]
    notes: dict[str, dict]  # "a|b" -> {category, note}
    dropped: list[tuple[str, str, str]]
    status_counts: dict[str, int]


def load_srmdn(path: str | Path, q: Quran) -> SrmdnData:
    """Only the curated pairs are used.

    The 'pending' pairs are Waqar's raw numbers read as 1-based, so every one is
    shifted by an ayah (build verification proves this); the 'dropped' pairs
    were rejected after being read through the same shift.
    """
    rows = _load(path)
    claims, notes, dropped = [], {}, []
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if r["status"] == "dropped":
            dropped.append((r["ayah1"], r["ayah2"], r["note"]))
        if r["status"] != "curated":
            continue
        p = _pair(q, r["ayah1"], r["ayah2"])
        if p:
            claims.append(Claim(*p, "srmdn", "srmdn", {"category": r["category"]}))
            notes[f"{p[0]}|{p[1]}"] = {"category": r["category"], "note": r["note"]}
    return SrmdnData(claims, notes, dropped, counts)


# ------------------------------------------------------------------ Furooq


def load_furooq(path: str | Path, q: Quran) -> tuple[list[Claim], int]:
    """Pairs inside Furooq groups of at most MAX_FUROOQ_GROUP verses. Returns (claims, skipped_groups)."""
    claims, skipped = [], 0
    for gi, g in enumerate(_load(path)):
        keys = [f"{v['sura_id']}:{v['aya_id']}" for v in g["verses"]]
        if len(keys) > MAX_FUROOQ_GROUP:
            skipped += 1
            continue
        for x, y in itertools.combinations(keys, 2):
            p = _pair(q, x, y)
            if p:
                claims.append(Claim(*p, "furooq", "furooq", {"score": g["score"], "group": gi, "group_size": len(keys)}))
    return claims, skipped
