import pytest

from pipeline.quality import choose_path, common_word_ratio, is_text_usable, readable_ratio

REAL = ("The government said on Wednesday that the council will review the decision after "
        "six months and that the states have been asked to give their views on the matter. " * 3)
SCRAMBLED = "".join(chr(i % 31 + 1) for i in range(600))  # control characters, like our IE sample


@pytest.mark.parametrize("text, expected", [
    ("", 0.0),                 # edge case: nothing at all
    ("   \n\t ", 0.0),         # only whitespace
    ("Hello, world!", 1.0),
    (SCRAMBLED, 0.0),
])
def test_readable_ratio(text, expected):
    assert readable_ratio(text) == pytest.approx(expected)


def test_common_word_ratio_is_high_for_english_and_zero_for_nothing():
    assert common_word_ratio(REAL) > 0.2
    assert common_word_ratio("") == 0.0


def test_real_prose_is_usable():
    assert is_text_usable(REAL)


def test_scrambled_text_is_not_usable():
    assert not is_text_usable(SCRAMBLED)


def test_too_little_text_is_not_trusted():
    assert not is_text_usable("The cat sat.")


def test_letters_that_are_not_words_are_rejected():
    """Garbage can still be printable letters; the common-word check catches it."""
    gibberish = " ".join("xqzv" * 3 for _ in range(60))
    assert readable_ratio(gibberish) > 0.85       # looks printable...
    assert not is_text_usable(gibberish)          # ...but isn't English


@pytest.mark.parametrize("text, n_lines, expected", [
    (REAL, 100, "text_layer"),
    (SCRAMBLED, 500, "hybrid"),   # unreadable text but plenty of geometry
    ("", 0, "ocr"),               # pure scan: nothing at all
    (SCRAMBLED, 5, "ocr"),        # too little geometry to rely on
])
def test_choose_path(text, n_lines, expected):
    assert choose_path(text, n_lines) == expected
