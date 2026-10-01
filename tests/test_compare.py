from mutashabihat.compare import compare, gap_chain, lexical_evidence, relation, words_match


def cmp(a: str, b: str) -> dict:
    return compare(a.split(), b.split())


def test_identical_sequences():
    c = cmp("a b c d", "a b c d")
    assert (c["run"], c["ratio"], c["diffs"]) == (4, 1.0, [])
    assert relation("a b c d".split(), "a b c d".split(), c) == "identical"


def test_contained_when_the_shorter_ayah_appears_verbatim():
    a, b = "x a b c y".split(), "a b c".split()
    assert relation(a, b, compare(a, b)) == "contained"


def test_diff_marks_the_swapped_word_with_one_based_positions():
    c = cmp("a b c d e", "a b X d e")
    assert c["diffs"] == [{"a": [3, 3], "b": [3, 3]}]
    assert {"a": [1, 2], "b": [1, 2], "n": 2} in c["shared"]


def test_pure_insertion_has_an_empty_side():
    assert cmp("a b c", "a c")["diffs"] == [{"a": [2, 2], "b": []}]


def test_words_match_handles_prefixes_and_spelling_variants():
    assert words_match("ولا", "لا")
    assert words_match("كالذين", "الذين")
    assert words_match("دارهم", "ديارهم")
    assert not words_match("من", "في")
    assert not words_match("ربك", "ربهم")  # short words must match exactly


def test_gap_chain_bridges_one_swapped_word():
    a, b = "قل انما علمها عند الله".split(), "قل انما العلم عند الله".split()
    assert gap_chain(a, b) == 4
    assert compare(a, b)["fuzzy_run"] == 2


def test_gap_chain_does_not_bridge_two_skipped_words():
    assert gap_chain("a b x y c d".split(), "a b c d".split()) == 2


def test_evidence_thresholds():
    base = {"fuzzy_run": 0, "fuzzy_cover": 0.0, "ratio": 0.0, "chain": 0}
    assert lexical_evidence({**base, "fuzzy_run": 4}) == "strong"
    assert lexical_evidence({**base, "fuzzy_run": 3, "fuzzy_cover": 0.6}) == "strong"
    assert lexical_evidence({**base, "fuzzy_run": 3, "fuzzy_cover": 0.3}) == "moderate"
    assert lexical_evidence({**base, "chain": 6}) == "strong"
    assert lexical_evidence({**base, "chain": 4}) == "moderate"
    assert lexical_evidence({**base, "fuzzy_run": 2, "fuzzy_cover": 1.0}) == "moderate"
    assert lexical_evidence({**base, "fuzzy_run": 2, "fuzzy_cover": 0.5}) == "weak"
    assert lexical_evidence({**base, "ratio": 0.7}) == "strong"
    assert lexical_evidence(base) == "weak"
