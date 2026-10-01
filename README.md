# mutashabihat

A unified, text-verified dataset of Quran mutashabihat (similar and repeated wording), merged from five public
sources. Every link is re-checked against the Quran text and carries its evidence: the shared words, the exact
differences, how many sources agree, and a confidence tier.

> **Status: private, for our own use.** No license is chosen yet; QUL's data terms are unconfirmed (see Sources).

## Use it

```python
from mutashabihat.dataset import Dataset

ds = Dataset.load()
ds.related("2:49")                         # medium confidence and up, best first
ds.related("2:49", min_confidence="high")
ds.link("2:49", "7:141")["diffs"]          # يُذَبِّحُونَ / يُقَتِّلُونَ
```

Or read the JSON directly. Word positions are 1-based and index the words of the QUL QPC Hafs text (`ayah.split()`
after dropping the verse number and ۞).

## Files (`data/`)

| File | What |
|---|---|
| `links.json` | One record per related ayah pair (a before b in mushaf order). The main file. |
| `by_ayah.json` | Index: ayah → related ayahs with confidence and relation, best first. |
| `phrases.json` | QUL's 814 shared-phrase groups, every occurrence re-anchored against the text. |
| `blocks.json` | Multi-ayah entries (Waqar), checked on the concatenated words. |
| `identical_groups.json` | Ayahs with exactly the same text (e.g. the 31 Ar-Rahman refrains). |
| `rejected.json` | Claims dropped for weak text evidence. Kept so nothing is lost silently. |
| `notes_srmdn.json` | srmdn's free-text notes. Third-party commentary, not verified. |
| `meta.json` | Counts, build parameters, hash of the source manifest. |

A link record:

```jsonc
{ "a": "2:49", "b": "7:141", "confidence": "high", "relation": "near",   // identical | contained | near | partial
  "families": ["furooq","qul","srmdn","text","waqar"], "sources": ["…"],
  "evidence": { "level": "strong", "run": 9, "fuzzy_run": 9, "chain": 9, "ratio": 0.889, "fuzzy_span": {…} },
  "shared": [{ "a": [3,8], "b": [3,8], "n": 6, "text": "…" }],             // exact shared stretches
  "diffs":  [{ "a": [9,9], "b": [9,9], "a_text": "يُذَبِّحُونَ", "b_text": "يُقَتِّلُونَ" }],
  "qul": {…}, "waqar": {"show_context": false}, "srmdn": {"category": "lafzi"}, "furooq": {…} }
```

## Confidence tiers

Evidence is `strong`, `moderate` or `weak` shared wording (fuzzy match: inflection, spelling and one-letter
prefix variants count; one swapped or skipped word is tolerated in the chain). The cut-offs are set from the rate
at which random ayah pairs reach them (0.08% for strong).

| Tier | Links | Rule |
|---|---:|---|
| high | 1,457 | strong evidence, and two independent source families or a human-curated source agree |
| medium | 2,874 | strong evidence from one algorithmic source, or moderate evidence from two |
| low | 1,526 | moderate evidence from one source, or weak evidence but two sources agree |
| unverified | 179 | weak evidence; one human-curated source (Waqar, srmdn) lists it |

Use **high + medium** by default. `low` and `unverified` are real but weaker; `unverified` needs a human look.
Counts are from the current build; `data/meta.json` is the source of truth.

## How it was built

1. **Stage** the inputs at pinned commits (`scripts/stage_sources.py`, `sources/MANIFEST.json`).
2. **Correct the sources.** Waqar's ayah numbers are 0-based (measured per juz, not assumed). srmdn's `pending` and
   `dropped` pairs carry the same shift and are not used.
3. **Check every claim against the text** and keep, tier or reject it. QUL's own word ranges are not trusted: spans
   and differences are recomputed, and phrase ranges that drifted are re-anchored.
4. **Add** near-duplicate ayah pairs found in the text itself (whole-ayah similarity ≥ 0.6). They never count as an
   independent source.
5. **Verify** (`python -m mutashabihat.verify` → `reports/VERIFICATION.md`) and run the tests.

## Verification highlights

- 23 of 23 well-known pairs (`gold.py`, written from memory, text-checked first) are in the dataset at high/medium.
- All 761 near-duplicate pairs (similarity ≥ 0.8) found by scanning the text were already listed by some source.
- 0.08% of random ayah pairs reach `strong`; a 2-word overlap is chance 2% of the time, so 2-word pairs are
  rejected unless a human source or a second source backs them.
- The text base matches an independent Quran text (differences are spelling conventions only).
- A manual read of 32 sampled kept links (8 per tier) found none wrong; 5 of the 16 sampled `low` and `unverified` links were generic or thematic (`reports/SPOT_CHECK.md`).

**Not verified:** this proves the wording claim. It does not say which pairs a hafiz is likely to confuse, and it is
not a scholarly review. About a third of a sample of the rejected pairs were genuine two-word mutashabihat.

## Sources

| Source | Used for | Terms |
|---|---|---|
| QUL (Tarteel) "Mutashabihat ul Quran" + matching-ayah + QPC Hafs text | phrases, ayah matches, the verification text | **unconfirmed**: QUL code is MIT, no data license found |
| [Waqar144/Quran_Mutashabihat_Data](https://github.com/Waqar144/Quran_Mutashabihat_Data) | hand-curated pairs (based on Qari Idrees Al-Asim's work) | free to use, **credit requested** |
| [srmdn/quran-mutashabihat](https://github.com/srmdn/quran-mutashabihat) | 283 curated pairs and notes | CC BY 4.0 (curated pairs): **attribution required** |
| [alinice1998/Furooq](https://github.com/alinice1998/Furooq) | similarity groups (≤ 10 verses), independent text for cross-check | MIT |
| [arriqaaq/ilm](https://github.com/arriqaaq/ilm) | only the QPC Hafs file; no data of its own | Apache-2.0 (code) |

Raw inputs are not committed (`sources/` is git-ignored except the manifest) because of the QUL terms.

## Rebuild

```sh
uv sync
python scripts/stage_sources.py --qul-phrases-zip "<Mutashabihat ul Quran.json.bz2>" --qul-matching-zip <matching-ayah.json.zip>
uv run python -m mutashabihat.build      # ~30 s, deterministic
uv run python -m mutashabihat.verify     # ~1 min, writes reports/
uv run pytest
```

The QUL files need a free QUL login to download. The phrases download is a ZIP despite its `.bz2` name.
