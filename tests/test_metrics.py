import pytest

from eval.metrics import cer, headline_similarity, iou, levenshtein, normalize
from pipeline.extract import split_on_gaps


@pytest.mark.parametrize("a, b, d", [
    ("", "", 0), ("abc", "abc", 0), ("kitten", "sitting", 3), ("", "abc", 3), ("abc", "", 3),
])
def test_levenshtein(a, b, d):
    assert levenshtein(a, b) == d


def test_cer_is_zero_for_perfect_ocr_and_grows_with_errors():
    assert cer("hello", "hello") == 0.0
    assert cer("hello", "hallo") == pytest.approx(0.2)


def test_cer_with_empty_reference():
    assert cer("", "") == 0.0 and cer("", "x") == 1.0


def test_normalize_ignores_case_and_punctuation():
    assert normalize("  Hello,   WORLD! ") == "hello world"


def test_headline_similarity_forgives_small_ocr_noise():
    ref = "Opposition meets President, presses demand for PM statement on Manipur"
    ocr = "Opposition meets President, presses demand for PM statement on Manipur."
    bad = "Completely different headline text here for testing purposes ok"
    assert headline_similarity(ref, ocr) == 1.0
    assert headline_similarity(ref, bad) < 0.5


def test_iou():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)


def test_split_on_gaps_separates_columns():
    spans = [(0, 40), (45, 90), (200, 240), (245, 300)]    # big gutter between 2nd and 3rd word
    assert split_on_gaps(spans, max_gap=30) == [[0, 1], [2, 3]]


def test_split_on_gaps_empty():
    assert split_on_gaps([], max_gap=10) == []
