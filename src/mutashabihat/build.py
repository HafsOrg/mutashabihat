"""Build the unified dataset from the staged sources.

    uv run python -m mutashabihat.build

Every claim from every source is re-checked against the Quran text. A pair is
kept only if the text supports it, or if a human-curated source lists it (in
which case it is labelled "unverified" or "low" instead of being dropped).
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from . import sources as S
from .compare import compare, lexical_evidence, relation
from .quran import Quran

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "sources"
DATA = ROOT / "data"

HUMAN = frozenset({"waqar", "srmdn"})
# "text" (mined) links come from the same text evidence the gate already uses, so
# they never count as an independent family when tiering.
NOT_INDEPENDENT = frozenset({"text"})
MINE_MIN_RATIO = 0.6  # whole-ayah similarity needed for a text-only (mined) link
MINE_TRIGRAM_DF_CAP = 120  # trigrams in more ayahs than this cannot seed a candidate
PHRASE_SEARCH = 3  # how far (words) QUL's range may be off before we give up re-anchoring
RANK = {"high": 0, "medium": 1, "low": 2, "unverified": 3}


def confidence(level: str, families: frozenset[str]) -> str | None:
    """Tier from text evidence and source agreement. None means rejected.

    high        strong text evidence, and two or more independent families or a human source
    medium      strong evidence from one algorithmic family, or moderate evidence from two
    low         moderate evidence from one family, or weak evidence but two families agree
    unverified  weak evidence, listed by one human-curated source only
    rejected    weak evidence from one algorithmic source

    "text" (mined) does not count as a family: it is the same evidence the gate uses.
    """
    independent = families - NOT_INDEPENDENT
    human = bool(independent & HUMAN)
    many = len(independent) >= 2
    if level == "strong":
        return "high" if (many or human) else "medium"
    if level == "moderate":
        return "medium" if many else "low"
    if many:
        return "low"
    return "unverified" if human else None


class Comparer:
    """Memoised ayah-pair comparison."""

    def __init__(self, q: Quran) -> None:
        self.q = q
        self._cache: dict[tuple[str, str], dict] = {}

    def __call__(self, a: str, b: str) -> dict:
        key = (a, b)
        if key not in self._cache:
            self._cache[key] = compare(list(self.q.skel[a]), list(self.q.skel[b]))
        return self._cache[key]


def mine_near_duplicates(q: Quran, cmp: Comparer) -> list[S.Claim]:
    """Pairs whose texts are similar enough to be linked on the text alone."""
    index: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for k in q.keys:
        s = q.skel[k]
        for i in range(len(s) - 2):
            index[tuple(s[i : i + 3])].add(k)
    candidates: set[tuple[str, str]] = set()
    for ks in index.values():
        if 2 <= len(ks) <= MINE_TRIGRAM_DF_CAP:
            candidates.update(itertools.combinations(sorted(ks, key=q.abs_id.__getitem__), 2))
    out = []
    for a, b in sorted(candidates, key=lambda p: (q.abs_id[p[0]], q.abs_id[p[1]])):
        c = cmp(a, b)
        if c["ratio"] >= MINE_MIN_RATIO and lexical_evidence(c) == "strong":
            out.append(S.Claim(a, b, "text", "text_mined"))
    return out


def span_text(q: Quran, key: str, span: list[int]) -> str:
    return " ".join(q.words[key][span[0] - 1 : span[1]]) if span else ""


def link_record(q: Quran, a: str, b: str, claims: list[S.Claim], c: dict) -> tuple[dict, str | None]:
    families = frozenset(x.family for x in claims)
    level = lexical_evidence(c)
    tier = confidence(level, families)
    rec: dict = {
        "a": a,
        "b": b,
        "confidence": tier,
        "relation": relation(list(q.skel[a]), list(q.skel[b]), c),
        "families": sorted(families),
        "sources": sorted({x.source for x in claims}),
        "evidence": {
            "level": level,
            "run": c["run"],
            "fuzzy_run": c["fuzzy_run"],
            "fuzzy_cover": c["fuzzy_cover"],
            "chain": c["chain"],
            "ratio": c["ratio"],
            "fuzzy_span": c["fuzzy_span"],
        },
        "shared": [dict(s, text=span_text(q, a, s["a"])) for s in c["shared"]],
        "diffs": [dict(d, a_text=span_text(q, a, d["a"]), b_text=span_text(q, b, d["b"])) for d in c["diffs"]],
        "diffs_truncated": c["diffs_truncated"],
    }
    by_source: dict[str, list[S.Claim]] = defaultdict(list)
    for x in claims:
        by_source[x.source].append(x)
    if "qul_matching" in by_source or "qul_phrase" in by_source:
        rows = by_source.get("qul_matching", [])
        qul: dict = {}
        if rows:
            qul["score"] = max(r.meta["score"] for r in rows)
            qul["coverage"] = max(r.meta["coverage"] for r in rows)
        if "qul_phrase" in by_source:
            qul["phrase_ids"] = sorted({r.meta["phrase_id"] for r in by_source["qul_phrase"]})
        rec["qul"] = qul
    if "waqar" in by_source:
        rec["waqar"] = {"show_context": any(r.meta["ctx"] for r in by_source["waqar"])}
    if "srmdn" in by_source:
        rec["srmdn"] = {"category": by_source["srmdn"][0].meta["category"]}
    if "furooq" in by_source:
        rec["furooq"] = {"score": max(r.meta["score"] for r in by_source["furooq"])}
    return rec, tier


def anchor_phrases(q: Quran, phrases: dict[str, dict]) -> list[dict]:
    """QUL phrase groups with every occurrence re-anchored against the text.

    QUL's word indexes drift by a word or two in a few percent of occurrences. A
    stated range is kept unless a same-width window within PHRASE_SEARCH words is
    clearly more similar to the source phrase, and the similarity is recorded.
    """
    out = []
    for pid in sorted(phrases, key=int):
        p = phrases[pid]
        sk, f, t = p["source"]["key"], p["source"]["from"], p["source"]["to"]
        source_ok = sk in q.skel and 1 <= f <= t <= len(q.skel[sk])
        src = list(q.skel[sk][f - 1 : t]) if source_ok else []
        occ = []
        for key in sorted(p["ayah"], key=lambda k: q.abs_id.get(k, 0)):
            if key not in q.skel:
                continue
            for rng in p["ayah"][key]:
                rf, rt = (rng[0], rng[0]) if len(rng) == 1 else (rng[0], rng[1])
                best = None
                if source_ok:
                    n = len(q.skel[key])
                    width = rt - rf + 1

                    def score(start: int, end: int) -> float:
                        return SequenceMatcher(None, src, list(q.skel[key][start - 1 : end]), autojunk=False).ratio()

                    # Keep QUL's range unless a same-width window nearby is clearly better:
                    # a variant phrase (different wording) must not be shrunk to fit the source.
                    stated = (score(rf, rt), 0, rf, rt) if 1 <= rf <= rt <= n else None
                    moved = None
                    for start in range(max(1, rf - PHRASE_SEARCH), rf + PHRASE_SEARCH + 1):
                        end = start + width - 1
                        if end <= n and (start, end) != (rf, rt):
                            cand = (score(start, end), -abs(start - rf), start, end)
                            if moved is None or cand > moved:
                                moved = cand
                    if stated is None:
                        best = moved if moved and moved[0] >= 0.5 else None
                    elif moved and moved[0] > stated[0] + 0.2:
                        best = moved
                    else:
                        best = stated
                if best is None:
                    occ.append({"ayah": key, "from": rf, "to": rt, "similarity": None, "status": "unanchored"})
                    continue
                r, _, start, end = best
                status = "identical" if r == 1.0 else "variant" if r >= 0.5 else "unrelated"
                occ.append(
                    {
                        "ayah": key,
                        "from": start,
                        "to": end,
                        "similarity": round(r, 3),
                        "status": status,
                        "shifted": (start, end) != (rf, rt),
                        "text": " ".join(q.words[key][start - 1 : end]),
                    }
                )
        summary: dict[str, int] = defaultdict(int)
        for o in occ:
            summary[o["status"]] += 1
        out.append(
            {
                "id": int(pid),
                "source": sk,
                "text": " ".join(q.words[sk][f - 1 : t]) if source_ok else None,
                "words": len(src) or None,
                "ayahs": p["ayahs"],
                "occurrences": occ,
                "summary": dict(sorted(summary.items())),
            }
        )
    return out


def block_records(q: Quran, raw_blocks: list[dict]) -> list[dict]:
    """Waqar's multi-ayah entries, checked on the concatenated words of each side."""
    seen: dict[tuple, dict] = {}
    for b in raw_blocks:
        x, y = sorted((tuple(b["a"]), tuple(b["b"])), key=lambda side: q.abs_id[side[0]])
        rec = seen.setdefault((x, y), {"a": list(x), "b": list(y), "ctx": False})
        rec["ctx"] = rec["ctx"] or b["ctx"]
    out = []
    for (x, y), rec in sorted(seen.items(), key=lambda kv: (q.abs_id[kv[0][0][0]], q.abs_id[kv[0][1][0]])):
        sa, sb = q.seq(x), q.seq(y)
        c = compare(sa, sb)
        level = lexical_evidence(c)
        out.append(
            {
                "a": rec["a"],
                "b": rec["b"],
                "show_context": rec["ctx"],
                "confidence": confidence(level, frozenset({"waqar"})),
                "relation": relation(sa, sb, c),
                "families": ["waqar"],
                "evidence": {
                    "level": level,
                    "run": c["run"],
                    "fuzzy_run": c["fuzzy_run"],
                    "fuzzy_cover": c["fuzzy_cover"],
                    "chain": c["chain"],
                    "ratio": c["ratio"],
                },
                "words_a": len(sa),
                "words_b": len(sb),
            }
        )
    return out


def identical_groups(q: Quran) -> list[dict]:
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for k in q.keys:
        groups[q.skel[k]].append(k)
    return [
        {"text": " ".join(q.words[ks[0]]), "ayahs": ks}
        for ks in sorted((v for v in groups.values() if len(v) > 1), key=lambda v: q.abs_id[v[0]])
    ]


def by_ayah(links: list[dict], q: Quran) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = defaultdict(list)
    for L in links:
        for x, y in ((L["a"], L["b"]), (L["b"], L["a"])):
            idx[x].append(
                {
                    "to": y,
                    "confidence": L["confidence"],
                    "relation": L["relation"],
                    "ratio": L["evidence"]["ratio"],
                }
            )
    for k in idx:
        idx[k].sort(key=lambda e: (RANK[e["confidence"]], -e["ratio"], q.abs_id[e["to"]]))
    return dict(sorted(idx.items(), key=lambda kv: q.abs_id[kv[0]]))


def write_json(path: Path, obj, one_per_line: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if one_per_line and isinstance(obj, list):
        body = "[\n" + ",\n".join(json.dumps(x, ensure_ascii=False, sort_keys=False) for x in obj) + "\n]\n"
    else:
        body = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    path.write_text(body, encoding="utf-8")


def build(out_dir: Path = DATA) -> dict:
    q = Quran.load(SRC / "qul" / "qpc-hafs.json")
    cmp = Comparer(q)

    qul_matching = S.load_qul_matching(SRC / "qul" / "matching-ayah.json", q)
    qul_phrase, raw_phrases = S.load_qul_phrases(SRC / "qul" / "phrases.json", q)
    waqar = S.load_waqar(SRC / "waqar" / "mutashabiha_data.json", q)
    srmdn = S.load_srmdn(SRC / "srmdn" / "pairs.json", q)
    furooq, furooq_skipped = S.load_furooq(SRC / "furooq" / "similarities.json", q)
    mined = mine_near_duplicates(q, cmp)

    merged: dict[tuple[str, str], list[S.Claim]] = defaultdict(list)
    for claim in itertools.chain(qul_matching, qul_phrase, waqar.claims, srmdn.claims, furooq, mined):
        merged[(claim.a, claim.b)].append(claim)

    links, rejected = [], []
    tier_by_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (a, b) in sorted(merged, key=lambda p: (q.abs_id[p[0]], q.abs_id[p[1]])):
        rec, tier = link_record(q, a, b, merged[(a, b)], cmp(a, b))
        for fam in rec["families"]:
            tier_by_source[fam][tier or "rejected"] += 1
        if tier is None:
            rejected.append(
                {
                    "a": a,
                    "b": b,
                    "families": rec["families"],
                    "sources": rec["sources"],
                    "evidence": rec["evidence"],
                    "reason": "weak text evidence, one algorithmic source only",
                }
            )
        else:
            links.append(rec)

    phrases = anchor_phrases(q, raw_phrases)
    blocks = block_records(q, waqar.blocks)
    groups = identical_groups(q)

    write_json(out_dir / "links.json", links, one_per_line=True)
    write_json(out_dir / "rejected.json", rejected, one_per_line=True)
    write_json(out_dir / "phrases.json", phrases, one_per_line=True)
    write_json(out_dir / "blocks.json", blocks, one_per_line=True)
    write_json(out_dir / "identical_groups.json", groups, one_per_line=True)
    write_json(out_dir / "by_ayah.json", by_ayah(links, q))
    write_json(out_dir / "notes_srmdn.json", dict(sorted(srmdn.notes.items())))

    tiers: dict[str, int] = defaultdict(int)
    for L in links:
        tiers[L["confidence"]] += 1
    manifest_sha = hashlib.sha256((SRC / "MANIFEST.json").read_bytes()).hexdigest()
    meta = {
        "schema_version": 1,
        "counts": {
            "links": len(links),
            "links_by_confidence": dict(sorted(tiers.items(), key=lambda kv: RANK[kv[0]])),
            "rejected": len(rejected),
            "phrases": len(phrases),
            "blocks": len(blocks),
            "identical_groups": len(groups),
            "ayahs_with_a_link": len({k for L in links for k in (L["a"], L["b"])}),
        },
        "parameters": {
            "mine_min_ratio": MINE_MIN_RATIO,
            "mine_trigram_df_cap": MINE_TRIGRAM_DF_CAP,
            "max_phrase_ayahs_for_pair_claims": S.MAX_PHRASE_AYAHS,
            "max_furooq_group": S.MAX_FUROOQ_GROUP,
            "furooq_groups_skipped": furooq_skipped,
            "waqar_ayah_offset": waqar.offset,
        },
        "claims_by_source": {
            "qul_matching": len(qul_matching),
            "qul_phrase": len(qul_phrase),
            "waqar": len(waqar.claims),
            "srmdn_curated": len(srmdn.claims),
            "furooq": len(furooq),
            "text_mined": len(mined),
        },
        "pairs_by_family_and_confidence": {f: dict(v) for f, v in sorted(tier_by_source.items())},
        "sources_manifest_sha256": manifest_sha,
    }
    write_json(out_dir / "meta.json", meta)
    return meta


if __name__ == "__main__":
    print(json.dumps(build(), indent=1, ensure_ascii=False))
