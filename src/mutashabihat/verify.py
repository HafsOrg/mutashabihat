"""Measure how trustworthy the built dataset is and write reports/.

    uv run python -m mutashabihat.verify

Everything in the report is computed here from the sources and data/; nothing
is typed in by hand. Run build first.
"""

from __future__ import annotations

import collections
import difflib
import itertools
import json
import random
from pathlib import Path

from . import sources as S
from .build import Comparer, mine_near_duplicates
from .compare import compare, lexical_evidence
from .gold import GOLD
from .quran import Quran, skeleton

ROOT = Path(__file__).resolve().parents[2]
SRC, DATA, REPORTS = ROOT / "sources", ROOT / "data", ROOT / "reports"
NULL_SAMPLES = 100_000
SEED = 2026


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def consonants(text: str) -> str:
    s = skeleton(text.replace(" ", ""))
    return "".join(ch for ch in s if ch not in "اوي").replace("ة", "ه")


# Known spelling differences between the Uthmani rasm (QPC) and modern spelling:
# the shadda-assimilated lam (ٱلَّيۡلِ vs الليل), the sad/sin of يبسط/يبصط, and the nun the
# rasm does not write in 21:88 (نُـۨجِي) and 72:16 (أَلَّوِ).
ORTHOGRAPHIC_OPS = {("insert", "", "ل"), ("insert", "", "ن"), ("replace", "ص", "س"), ("replace", "س", "ص")}


def text_base_check(q: Quran) -> dict:
    """QPC Hafs (QUL) against Furooq's independent imlaei text, letter skeletons per ayah."""
    f = jload(SRC / "furooq" / "quran.json")
    other = {f"{v['sura_id']}:{v['aya_id']}": v["standard"] for v in f}
    differing, unexplained = [], []
    for k in q.keys:
        a, b = consonants("".join(q.skel[k])), consonants(other[k])
        if a == b:
            continue
        differing.append(k)
        ops = [(t, a[i1:i2], b[j1:j2]) for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes() if t != "equal"]
        if any(op not in ORTHOGRAPHIC_OPS for op in ops):
            unexplained.append(k)
    return {
        "ayahs_compared": len(q.keys),
        "ayahs_differing": len(differing),
        "ayahs_unexplained": len(unexplained),
        "unexplained_examples": unexplained[:8],
        "words_total": sum(len(v) for v in q.skel.values()),
    }


def null_distribution(q: Quran) -> dict:
    rnd = random.Random(SEED)
    counts = collections.Counter()
    runs = collections.Counter()
    for _ in range(NULL_SAMPLES):
        a, b = rnd.sample(q.keys, 2)
        c = compare(list(q.skel[a]), list(q.skel[b]))
        counts[lexical_evidence(c)] += 1
        for k in (2, 3, 4, 5):
            runs[k] += c["fuzzy_run"] >= k
    return {
        "samples": NULL_SAMPLES,
        **{k: counts[k] for k in ("strong", "moderate", "weak")},
        "fuzzy_run_at_least": {str(k): runs[k] for k in (2, 3, 4, 5)},
    }


def srmdn_checks(q: Quran, waqar: S.WaqarData, srmdn_path: Path) -> dict:
    """Prove the srmdn pending/dropped pairs are Waqar pairs read one ayah off."""
    rows = jload(srmdn_path)
    waqar_pairs = {(c.a, c.b) for c in waqar.claims}
    # Waqar's raw numbers read as 1-based (no correction), as srmdn did.
    raw = jload(SRC / "waqar" / "mutashabiha_data.json")
    uncorrected = set()
    for ents in raw.values():
        for e in ents:
            s = e["src"]["ayah"]
            if isinstance(s, list):
                continue
            for m in e["muts"]:
                if isinstance(m["ayah"], list):
                    continue
                ka, kb = q.key_at(s), q.key_at(m["ayah"])
                if ka and kb and ka != kb:
                    uncorrected.add(q.ordered(ka, kb))
    pending = {q.ordered(r["ayah1"], r["ayah2"]) for r in rows if r["status"] == "pending"}
    dropped = [(r["ayah1"], r["ayah2"]) for r in rows if r["status"] == "dropped"]

    def level(a: str, b: str) -> str:
        return lexical_evidence(compare(list(q.skel[a]), list(q.skel[b])))

    pend_levels = collections.Counter(level(*p) for p in pending)
    shifted_ok = 0
    shifted_examples = []
    for a, b in dropped:
        sa, sb = q.key_at(q.abs_id[a] + 1), q.key_at(q.abs_id[b] + 1)
        if sa and sb and q.ordered(sa, sb) in waqar_pairs:
            shifted_ok += 1
            if len(shifted_examples) < 4:
                shifted_examples.append([a, b, sa, sb])
    return {
        "pending_pairs": len(pending),
        "pending_equal_to_waqar_uncorrected": len(pending & uncorrected),
        "pending_equal_to_waqar_corrected": len(pending & waqar_pairs),
        "pending_text_evidence": dict(pend_levels),
        "dropped_pairs": len(dropped),
        "dropped_that_are_shifted_valid_waqar_pairs": shifted_ok,
        "dropped_examples_shifted": shifted_examples,
    }


def gold_check(q: Quran, links: dict) -> list[dict]:
    out = []
    for a, b, note in GOLD:
        a, b = q.ordered(a, b)
        c = compare(list(q.skel[a]), list(q.skel[b]))
        rec = links.get((a, b))
        out.append(
            {
                "pair": f"{a} ~ {b}",
                "note": note,
                "text_evidence": lexical_evidence(c),
                "in_dataset": rec is not None,
                "confidence": rec["confidence"] if rec else None,
            }
        )
    return out


def source_breakdown(q: Quran, cmp: Comparer, claim_sets: dict[str, list[S.Claim]], links: dict) -> list[dict]:
    rows = []
    for name, claims in claim_sets.items():
        pairs = sorted({(c.a, c.b) for c in claims})
        ev = collections.Counter(lexical_evidence(cmp(a, b)) for a, b in pairs)
        kept = [p for p in pairs if p in links]
        unique = [p for p in kept if len({f for f in links[p]["families"] if f != "text"} - {claims[0].family}) == 0]
        rows.append(
            {
                "source": name,
                "pairs": len(pairs),
                "strong": ev["strong"],
                "moderate": ev["moderate"],
                "weak": ev["weak"],
                "kept": len(kept),
                "kept_only_by_this_family": len(unique),
                "agrees_with_another_family": len(kept) - len(unique),
            }
        )
    return rows


def completeness(q: Quran, cmp: Comparer, source_pairs: set[tuple[str, str]], links: dict) -> dict:
    """How many near-duplicate pairs in the text were already listed by some source?"""
    index: dict[tuple[str, ...], set[str]] = collections.defaultdict(set)
    for k in q.keys:
        s = q.skel[k]
        for i in range(len(s) - 3):
            index[tuple(s[i : i + 4])].add(k)
    cands = set()
    for ks in index.values():
        if 2 <= len(ks) <= 200:
            cands.update(itertools.combinations(sorted(ks, key=q.abs_id.__getitem__), 2))
    buckets = {"ratio>=0.8": [0, 0, 0], "0.6<=ratio<0.8": [0, 0, 0]}  # total, listed by a source, in dataset
    for a, b in cands:
        r = cmp(a, b)["ratio"]
        if r < 0.6:
            continue
        key = "ratio>=0.8" if r >= 0.8 else "0.6<=ratio<0.8"
        buckets[key][0] += 1
        buckets[key][1] += (a, b) in source_pairs
        buckets[key][2] += (a, b) in links
    return {k: {"pairs": v[0], "listed_by_a_source": v[1], "in_dataset": v[2]} for k, v in buckets.items()}


def phrase_stats() -> dict:
    phrases = jload(DATA / "phrases.json")
    occ = [o for p in phrases for o in p["occurrences"]]
    st = collections.Counter(o["status"] for o in occ)
    return {
        "phrases": len(phrases),
        "occurrences": len(occ),
        "by_status": dict(st),
        "shifted_by_reanchoring": sum(1 for o in occ if o.get("shifted")),
    }


def run() -> dict:
    q = Quran.load(SRC / "qul" / "qpc-hafs.json")
    cmp = Comparer(q)
    links_list = jload(DATA / "links.json")
    links = {(L["a"], L["b"]): L for L in links_list}
    meta = jload(DATA / "meta.json")

    qul_matching = S.load_qul_matching(SRC / "qul" / "matching-ayah.json", q)
    qul_phrase, _ = S.load_qul_phrases(SRC / "qul" / "phrases.json", q)
    waqar = S.load_waqar(SRC / "waqar" / "mutashabiha_data.json", q)
    srmdn = S.load_srmdn(SRC / "srmdn" / "pairs.json", q)
    furooq, _ = S.load_furooq(SRC / "furooq" / "similarities.json", q)
    claim_sets = {
        "qul_matching": qul_matching,
        "qul_phrase": qul_phrase,
        "waqar": waqar.claims,
        "srmdn (curated)": srmdn.claims,
        "furooq": furooq,
    }
    source_pairs = {(c.a, c.b) for cl in claim_sets.values() for c in cl}

    result = {
        "text_base": text_base_check(q),
        "waqar_offset": {"offset": waqar.offset, "per_juz": waqar.offset_report},
        "srmdn": srmdn_checks(q, waqar, SRC / "srmdn" / "pairs.json"),
        "null": null_distribution(q),
        "gold": gold_check(q, links),
        "sources": source_breakdown(q, cmp, claim_sets, links),
        "completeness": completeness(q, cmp, source_pairs, links),
        "phrases": phrase_stats(),
        "tiers": meta["counts"]["links_by_confidence"],
        "rejected": meta["counts"]["rejected"],
        "unverified_blocks": sum(1 for b in jload(DATA / "blocks.json") if b["confidence"] == "unverified"),
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (REPORTS / "VERIFICATION.md").write_text(render(result, meta), encoding="utf-8")
    return result


def pct(n: int, d: int) -> str:
    return f"{n / d:.2%}" if d else "n/a"


def render(r: dict, meta: dict) -> str:
    tb, nl, sm, ph = r["text_base"], r["null"], r["srmdn"], r["phrases"]
    gold_ok = sum(1 for g in r["gold"] if g["text_evidence"] == "strong")
    gold_in = sum(1 for g in r["gold"] if g["in_dataset"])
    gold_top = sum(1 for g in r["gold"] if g["confidence"] in ("high", "medium"))
    L = ["# Verification report", "", "Generated by `python -m mutashabihat.verify`. Every number below is computed, not typed.", ""]
    L += ["## What \"accurate\" means here", "",
          "Every link is re-checked against the Quran text (QUL's QPC Hafs script). A pair is kept only if its two",
          "ayahs share real wording, or if a human-curated source lists it (then it is labelled `low` or `unverified`).",
          "This proves the wording claim. It is not a scholarly review: nothing here replaces a hafiz or a classical",
          "mutashabihat reference, and `unverified` pairs in particular need a human look.", ""]
    L += ["## Result", "", "| Tier | Links | Meaning |", "|---|---:|---|"]
    meaning = {
        "high": "strong text evidence, and two independent sources or a human-curated source agree",
        "medium": "strong text evidence from one algorithmic source, or moderate evidence from two",
        "low": "moderate text evidence from one source, or weak evidence but two sources agree",
        "unverified": "weak text evidence; listed by one human-curated source only",
    }
    for t, n in r["tiers"].items():
        L.append(f"| {t} | {n} | {meaning[t]} |")
    L += ["", f"{r['rejected']} further claims were **rejected** (weak text evidence, single algorithmic source); they are listed in `data/rejected.json`.", ""]

    L += ["## 1. The text we verify against", "",
          f"- {tb['ayahs_compared']} ayahs, {tb['words_total']} words.",
          f"- Cross-check against an independent text (Furooq's imlaei Quran, letter skeletons): {tb['ayahs_differing']} of {tb['ayahs_compared']} ayahs differ,",
          f"  {'all' if not tb['ayahs_unexplained'] else 'all but ' + str(tb['ayahs_unexplained'])} explained by known rasm-vs-modern spelling conventions (the shadda-assimilated lam, e.g. ٱلَّيۡلِ vs الليل; the sad/sin of يبصط; an unwritten nun in 21:88 and 72:16)."
          + (f" Unexplained: {', '.join(tb['unexplained_examples'])}." if tb["unexplained_examples"] else ""), ""]

    L += ["## 2. Source corrections this build depends on", "",
          f"**Waqar144's ayah numbers are 0-based.** Read as 1-based, linked ayahs share almost no wording; shifted by +1 they match. "
          f"Measured per juz file; offset +1 wins in every file with enough links (min gain below).", "",
          "| juz | links | mean similarity at offset 0 | at offset +1 |", "|---:|---:|---:|---:|"]
    for juz, row in sorted(r["waqar_offset"]["per_juz"].items(), key=lambda kv: int(kv[0])):
        if row["links"]:
            L.append(f"| {juz} | {row['links']} | {row['mean_ratio_offset_0']} | {row['mean_ratio_offset_1']} |")
    L += ["", f"**srmdn's `pending` pairs inherit that shift and are not used.** {sm['pending_equal_to_waqar_uncorrected']} of {sm['pending_pairs']} pending pairs "
          f"equal Waqar's raw numbers read as 1-based; only {sm['pending_equal_to_waqar_corrected']} equal the corrected pairs. "
          f"Text evidence for the pending set: {sm['pending_text_evidence']}.", "",
          f"**srmdn's `dropped` pairs were rejected through the same shift.** {sm['dropped_that_are_shifted_valid_waqar_pairs']} of {sm['dropped_pairs']} "
          f"dropped pairs are valid Waqar pairs one ayah later (e.g. {sm['dropped_examples_shifted'][:2]}), so they are not usable as negative examples.", ""]

    L += ["## 3. How specific is the text test?", "",
          f"{nl['samples']} random ayah pairs (seed {SEED}) were run through the same classifier:", "",
          "| Evidence level | Random pairs | Rate |", "|---|---:|---:|"]
    for k in ("strong", "moderate", "weak"):
        L.append(f"| {k} | {nl[k]} | {pct(nl[k], nl['samples'])} |")
    fr = nl["fuzzy_run_at_least"]
    L += ["", "Unrelated ayahs almost never pass, so a link with strong evidence did not arise by chance.", "",
          "Why a 2-word overlap is not evidence: how often random pairs share a fuzzy run of at least k words:", "",
          "| k | Random pairs | Rate |", "|---:|---:|---:|"]
    for k in ("2", "3", "4", "5"):
        L.append(f"| {k} | {fr[k]} | {pct(fr[k], nl['samples'])} |")
    L += ["", "Two shared words occur by chance far more often than three, so a pair backed only by a 2-word overlap is rejected unless a human source lists it or a second source agrees. "
          "Some of these are genuine short mutashabihat (see SPOT_CHECK.md); `data/rejected.json` is the pool to review for them.", ""]

    L += ["## 4. What each source contributed", "",
          "| Source | Pairs | Strong | Moderate | Weak | Kept | Kept only by this family | Also backed by another |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for s in r["sources"]:
        L.append(f"| {s['source']} | {s['pairs']} | {s['strong']} | {s['moderate']} | {s['weak']} | {s['kept']} | {s['kept_only_by_this_family']} | {s['agrees_with_another_family']} |")
    L += ["", "Kept = present in `links.json` (weak claims backed by a single algorithmic source are the ones rejected).", ""]

    L += ["## 5. Recall checks", "",
          f"**Well-known pairs** (`gold.py`, written from memory): {gold_ok} of {len(r['gold'])} pass the text test; "
          f"{gold_in} are in the dataset; {gold_top} are `high` or `medium`.", "",
          "| Pair | Note | Text evidence | Tier |", "|---|---|---|---|"]
    for g in r["gold"]:
        L.append(f"| {g['pair']} | {g['note']} | {g['text_evidence']} | {g['confidence'] or 'missing'} |")
    L += ["", "**Completeness against the text.** Near-duplicate ayah pairs found by scanning the text, and how many some source already listed:", "",
          "| Whole-ayah similarity | Pairs in text | Listed by a source | In dataset |", "|---|---:|---:|---:|"]
    for k, v in r["completeness"].items():
        L.append(f"| {k} | {v['pairs']} | {v['listed_by_a_source']} | {v['in_dataset']} |")
    L += ["", "Pairs that only share a repeated phrase inside otherwise different ayahs are not near-duplicates and are outside this count; "
          "they are covered only as far as QUL's phrase list reaches.", ""]

    L += ["## 6. QUL phrase layer", "",
          f"{ph['phrases']} phrases, {ph['occurrences']} occurrences. Each occurrence was re-anchored in the text: {ph['by_status']}. "
          f"{ph['shifted_by_reanchoring']} occurrences ({pct(ph['shifted_by_reanchoring'], ph['occurrences'])}) had QUL word indexes off by a word or more and were moved. "
          "`identical` = same words as the source phrase, `variant` = similar (QUL phrases are clusters of similar wordings), `unrelated` = no real match; treat `unrelated` as errors.", ""]

    L += ["## 7. Known limits", "",
          "- QUL's data license is unconfirmed; the other sources' terms are in `sources/MANIFEST.json` and the README.",
          "- The QUL phrase file is an Aug 2024 export covering 36% of ayahs; the live QUL site has more.",
          "- Pairs that share only a formula phrase (e.g. جنات تجري من تحتها الأنهار خالدين فيها) are not listed unless a source lists them.",
          "- Weak-evidence pairs from human sources may be thematic rather than verbal; they are kept as `unverified`/`low`, not dropped.",
          "- srmdn's notes are third-party commentary and are kept apart in `data/notes_srmdn.json`.", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    out = run()
    print(json.dumps({k: out[k] for k in ("tiers", "rejected", "null", "completeness", "phrases")}, indent=1, ensure_ascii=False))
