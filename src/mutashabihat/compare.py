"""Objective, text-only comparison of two ayahs (or two ayah blocks).

Every link in the dataset is re-derived from the Quran text with these
functions, so the shared and differing words never depend on a source's own
word ranges (QUL's drift by a word or two in a few percent of cases).
"""

from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache

MAX_DIFFS = 10
FUZZY_MIN_LEN = 4  # shorter words must match exactly
FUZZY_RATIO = 0.75  # one letter off in a four-letter word is 0.75


PREFIXES = "وفبلك"  # conjunction/preposition letters that attach to the next word


def _strip_prefix(w: str) -> str:
    return w[1:] if len(w) >= 3 and w[0] in PREFIXES else w


@lru_cache(maxsize=None)
def words_match(x: str, y: str) -> bool:
    """Same word, the same word with/without a one-letter prefix (ولا/لا, كالذين/الذين),
    or a close variant (inflection, spelling) of a word with 4+ letters."""
    if x == y:
        return True
    sx, sy = _strip_prefix(x), _strip_prefix(y)
    if sx == y or x == sy or sx == sy:
        return True
    for u, v in ((x, y), (sx, sy)):
        if len(u) >= FUZZY_MIN_LEN and len(v) >= FUZZY_MIN_LEN and SequenceMatcher(None, u, v).ratio() >= FUZZY_RATIO:
            return True
    return False


def fuzzy_run(sa: list[str], sb: list[str]) -> tuple[int, int, int]:
    """Longest contiguous run where every word pair matches fuzzily.

    Returns (length, end_in_a, end_in_b) with 1-based end positions, (0, 0, 0) if none.
    """
    best = (0, 0, 0)
    prev = [0] * (len(sb) + 1)
    for i, x in enumerate(sa, 1):
        cur = [0] * (len(sb) + 1)
        for j, y in enumerate(sb, 1):
            if words_match(x, y):
                cur[j] = prev[j - 1] + 1
                if cur[j] > best[0]:
                    best = (cur[j], i, j)
        prev = cur
    return best


def gap_chain(sa: list[str], sb: list[str]) -> int:
    """Most fuzzy-matching words in order, allowing one skipped or swapped word between
    consecutive matches (قل إنما [علمها/العلم] عند الله). Counts matched words only."""
    n, m = len(sa), len(sb)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    best = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if words_match(sa[i - 1], sb[j - 1]):
                prev = 0
                for di, dj in ((1, 1), (2, 1), (1, 2), (2, 2)):
                    pi, pj = i - di, j - dj
                    if pi >= 1 and pj >= 1 and d[pi][pj] > prev:
                        prev = d[pi][pj]
                d[i][j] = prev + 1
                best = max(best, d[i][j])
    return best


def compare(sa: list[str], sb: list[str]) -> dict:
    """Word-level comparison of two skeleton sequences.

    Returns the longest common contiguous run, the difflib ratio, the shared
    blocks and the differing stretches. Word positions are 1-based, inclusive.
    """
    sm = SequenceMatcher(None, sa, sb, autojunk=False)
    blocks = [m for m in sm.get_matching_blocks() if m.size]
    run = max((m.size for m in blocks), default=0)
    shared = [
        {"a": [m.a + 1, m.a + m.size], "b": [m.b + 1, m.b + m.size], "n": m.size}
        for m in blocks
        if m.size >= 2
    ]
    # An empty side (pure insertion/deletion) is []. Positions are 1-based, inclusive.
    diffs = [
        {"a": [i1 + 1, i2] if i2 > i1 else [], "b": [j1 + 1, j2] if j2 > j1 else []}
        for tag, i1, i2, j1, j2 in sm.get_opcodes()
        if tag != "equal"
    ]
    shorter = min(len(sa), len(sb))
    frun, fa, fb = fuzzy_run(sa, sb)
    return {
        "run": run,
        "ratio": round(sm.ratio(), 3),
        "run_cover": round(run / shorter, 3) if shorter else 0.0,
        "fuzzy_run": frun,
        "chain": gap_chain(sa, sb),
        "fuzzy_cover": round(frun / shorter, 3) if shorter else 0.0,
        "fuzzy_span": {"a": [fa - frun + 1, fa], "b": [fb - frun + 1, fb]} if frun else None,
        "len_a": len(sa),
        "len_b": len(sb),
        "shared": shared,
        "diffs": diffs[:MAX_DIFFS],
        "diffs_truncated": len(diffs) > MAX_DIFFS,
    }


def relation(sa: list[str], sb: list[str], c: dict) -> str:
    """identical | contained | near | partial, from the comparison alone."""
    if sa == sb:
        return "identical"
    if c["run"] == min(len(sa), len(sb)):
        return "contained"  # the shorter ayah appears verbatim inside the longer one
    if c["ratio"] >= 0.8:
        return "near"
    return "partial"


def lexical_evidence(c: dict) -> str:
    """strong | moderate | weak: how much wording the two texts share.

    Evidence is the longest fuzzy run (inflection, spelling and one-letter
    prefix variants match), the gap-tolerant chain (one skipped or swapped word
    allowed between matches), and the exact difflib ratio. Thresholds come from
    the random-pair null distribution reported in reports/VERIFICATION.md: a
    random pair of ayahs reaches "strong" about 0.1% of the time. Re-measure
    with verify.py before changing them.
    """
    fr, cover, ratio, chain = c["fuzzy_run"], c["fuzzy_cover"], c["ratio"], c["chain"]
    if fr >= 4 or (fr >= 3 and cover >= 0.6) or ratio >= 0.7 or chain >= 6:
        return "strong"
    if fr == 3 or ratio >= 0.5 or (fr >= 2 and cover >= 0.99) or chain >= 4:
        return "moderate"
    return "weak"
