import pytest

from pipeline.bylines import strip_byline
from pipeline.summarize import split_sentences, summarize

ARTICLE = (
    "The GST Council kept the 28% tax on online gaming and casinos on Wednesday. "
    "Several states differed on how gaming should be valued for tax. "
    "The Council will review the rate after six months. "
    "Ministers also discussed an unrelated matter about fertiliser. "
    "The finance minister said the gaming tax decision was taken after long debate. "
    "Industry groups warned that the gaming tax could hurt the sector."
)


def test_empty_text_gives_empty_summary():
    assert summarize("") == ""


def test_short_text_is_returned_whole():
    assert summarize("One sentence only here.") == "One sentence only here."


def test_summary_has_at_most_n_sentences():
    assert len(split_sentences(summarize(ARTICLE, max_sentences=2))) <= 2


def test_summary_keeps_original_sentence_order():
    s = summarize(ARTICLE, max_sentences=3)
    positions = [ARTICLE.index(sent) for sent in split_sentences(s)]
    assert positions == sorted(positions)


def test_summary_only_uses_sentences_from_the_source():
    """Extractive means no invented facts."""
    for sent in split_sentences(summarize(ARTICLE)):
        assert sent in ARTICLE


@pytest.mark.parametrize("text, expected", [
    ("Hello there. How are you? Fine!", 3),
    ("Dr. smith went home. It was late.", 2),   # lowercase after '.' is not a sentence start
    ("", 0),
])
def test_split_sentences(text, expected):
    assert len(split_sentences(text)) == expected


@pytest.mark.parametrize("text, expected_start", [
    ("AANCHAL MAGAZINE NEW DELHI, AUGUST 2 ALTHOUGH some states differed", "ALTHOUGH some"),
    ("SUKRITA BARUAH & AMRITA NAYAK DUTTA IMPHAL, NEW DELHI, AUG 2 THE 65-YEAR-OLD", "THE 65-YEAR-OLD"),
    ("Mumbai: Heavy rain continued", "Mumbai: Heavy rain"),     # no byline pattern: unchanged
    ("", ""),
])
def test_strip_byline(text, expected_start):
    assert strip_byline(text).startswith(expected_start)
