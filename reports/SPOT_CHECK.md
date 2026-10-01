# Manual spot-check

A human-style reading of a seeded sample from the final build, done by Claude (not a hafiz or a scholar).
It checks whether the sampled links are real wording matches; it does not judge how likely a hafiz is to
confuse them. Reproduce the sample with `python scripts/spot_check_sample.py` (seed 20261001, 8 per group).

Key: ✓ genuine shared wording or a recognised mutashabih; ~ real but generic (a stock ending or opening) or
thematic only; ✗ wrong.

| Group | Sampled | ✓ | ~ | ✗ |
|---|---:|---:|---:|---:|
| high | 8 | 8 | 0 | 0 |
| medium | 8 | 7 | 1 | 0 |
| low | 8 | 6 | 2 | 0 |
| unverified | 8 | 5 | 3 | 0 |
| rejected (should be mostly not genuine) | 8 | 3 genuine | 5 not genuine | |

## Notes

- **high** (8/8): 12:22~28:14 (the maturity verse, one added word), 43:83~70:42 (identical), 5:92~64:12,
  29:47~29:49 (الكافرون / الظالمون), 17:75~17:86 (نصيرا / وكيلا), 16:30~39:10, 37:5~44:7, 9:4~9:7.
- **medium**: the one `~` is 5:2~8:69 (the stock "واتقوا الله إن الله" ending). The rest are refrain pairs (55:32~55:51),
  "يا أيها الذين آمنوا … فمن اعتدى بعد ذلك فله عذاب أليم" (2:178~5:94), "والله عزيز ذو انتقام" (3:4~5:95),
  "وما أدراك ما …" (77:14~83:8) and the "جنات تجري من تحتها الأنهار" family.
- **low**: genuine but short, e.g. 15:40~37:74 (عبادك منهم / عباد الله المخلصين), 4:143~40:33 and 7:186~42:44
  (ومن يضلل الله …), 5:95~5:106 (ذوا عدل منكم). The two `~` are stock endings (والله عليم حكيم, وكان الله بكل شيء عليما).
- **unverified** (Waqar/srmdn only, little shared wording): genuine pairs sharing an opening or a verb with a different
  continuation (7:64~27:57, 7:72~29:15, 27:57~29:15 فأنجيناه …; 7:88~7:127 قال الملأ …; 7:160~7:168 وقطعناهم …).
  The `~` are 12:22~12:94 (only the opening "ولما"), 10:49~21:66 (same idea, different words) and 2:233~65:6 (thematic).
  None looked wrong, but they cannot be confirmed from the text alone.
- **rejected**: 5 of 8 correctly rejected (e.g. 40:62~67:1, 24:62~48:9, 44:52~69:22). **3 were arguably genuine short
  pairs that the filter lost:** 7:52~10:57 (هدى ورحمة), 26:138~44:35 (وما نحن بمعذبين / بمنشرين),
  2:222~9:108 (يحب المتطهرين / المطهرين). They share only two words, which random ayah pairs do 2% of the time, so the
  text alone cannot separate them from chance (see VERIFICATION.md section 3). Treat `data/rejected.json` as a pool
  to review for short pairs, not as junk.

## Earlier review passes (before the final matcher)

Two sampling passes on earlier builds drove two fixes, both kept in the build:

1. About 5 of 14 sampled rejects were genuine pairs lost to a leading و/ف/ب/ل/ك or one swapped word
   (e.g. 33:63~67:26 "قل إنما [علمها / العلم] عند الله"). The matcher became prefix-aware and gained a gap-tolerant chain;
   174 pairs moved out of `rejected`, and 14 of 14 sampled from those were plausible.
2. QUL phrase occurrences were being shrunk to shorter windows when a variant differed from the source phrase.
   Re-anchoring now moves a range only when a same-width window is clearly closer (8 of 3,558 occurrences move).
