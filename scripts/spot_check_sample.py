#!/usr/bin/env python3
"""Print a seeded sample of links per tier (and rejected pairs) for manual reading.

    python scripts/spot_check_sample.py [seed] [per_tier]

reports/SPOT_CHECK.md records a human reading of the default sample.
"""

import json
import random
import sys
from pathlib import Path

from mutashabihat.quran import Quran

ROOT = Path(__file__).resolve().parent.parent
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20261001
n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
q = Quran.load(ROOT / "sources" / "qul" / "qpc-hafs.json")
links = json.loads((ROOT / "data" / "links.json").read_text(encoding="utf-8"))
rejected = json.loads((ROOT / "data" / "rejected.json").read_text(encoding="utf-8"))
rnd = random.Random(seed)


def show(rec: dict, label: str) -> None:
    e = rec["evidence"]
    print(f"[{label}] {rec['a']} ~ {rec['b']} | {','.join(rec['families'])} | run={e['fuzzy_run']} chain={e['chain']} ratio={e['ratio']}")
    print("    A:", " ".join(q.words[rec["a"]])[:150])
    print("    B:", " ".join(q.words[rec["b"]])[:150])


for tier in ("high", "medium", "low", "unverified"):
    pool = [r for r in links if r["confidence"] == tier]
    print(f"\n######## {tier}: {len(pool)} links, sample {n}")
    for r in rnd.sample(pool, n):
        show(r, tier)
print(f"\n######## rejected: {len(rejected)}, sample {n}")
for r in rnd.sample(rejected, n):
    show(r, "rejected")
