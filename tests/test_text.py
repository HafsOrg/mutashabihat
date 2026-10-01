from mutashabihat.quran import ayah_words, skeleton


def test_dagger_alef_becomes_alef():
    assert skeleton("ٱلۡكِتَٰبُ") == "الكتاب"


def test_hamza_carriers_collapse_to_the_same_skeleton():
    assert skeleton("ءَامَنُواْ") == skeleton("آمنوا") == "امنوا"


def test_vowel_marks_and_quranic_signs_are_removed():
    assert skeleton("قُلۡ") == "قل"
    assert skeleton("ٱللَّهِۖ") == "الله"


def test_ayah_words_drops_verse_number_and_hizb_sign():
    assert ayah_words("۞ قُلۡ هُوَ\xa0١٢٣") == ["قُلۡ", "هُوَ"]


def test_ayah_words_keeps_text_without_a_verse_number():
    assert ayah_words("قُلۡ هُوَ") == ["قُلۡ", "هُوَ"]
