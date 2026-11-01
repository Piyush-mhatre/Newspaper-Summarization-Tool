"""Regression tests for TEXT LEAKING between stories.

Every test here pins a real bug seen on the Indian Express front page.
Fast ones check geometry only (no OCR). The slow ones run OCR and check final text.
"""
import re

import pymupdf
import pytest

from pipeline import extract
from pipeline.layout import build_articles, font_family
from pipeline.run import process_pdf
from pipeline.textutil import clean_ocr_line, extract_continued


# ------------------------------------------------------------------ pure, tiny tests
@pytest.mark.parametrize("font, family", [
    ("Gulliver-OV-BOLDUZ", "Gulliver"),
    ("Gulliver-Italic-OV-BOLDW", "Gulliver"),     # italic body text is still body text
    ("Scout-Bold", "Scout"),
    ("", ""),
])
def test_font_family(font, family):
    assert font_family(font) == family


@pytest.mark.parametrize("text, expected_text, page", [
    ("Story text. CONTINUED ON PAGE 2", "Story text.", 2),
    ("Story text. Continued on Page 11 more", "Story text. more", 11),
    ("No marker here.", "No marker here.", None),
    ("", "", None),
])
def test_extract_continued(text, expected_text, page):
    assert extract_continued(text) == (expected_text, page)


@pytest.mark.parametrize("raw, expected", [
    ("J&amp;K was meant", "J&K was meant"),            # HTML entity
    ("in- |", "in-"),                                  # column rule drawn as | after a hyphen
    ("seen by | the court", "seen by the court"),
    ("govern- I", "govern-"),                          # column rule misread as capital I
    ("I went home", "I went home"),                    # a real 'I' must survive
    ("  spaced   out  ", "spaced out"),
])
def test_clean_ocr_line(raw, expected):
    assert clean_ocr_line(raw) == expected


def test_line_in_next_column_slot_belongs_to_the_headline_above(make_line):
    """The 'Judge' bug: a headline starts further right than its own left column.

    Lines in that left column have centres LEFT of the headline's x-range, but the
    column is mostly under the headline, so they still belong to it.
    """
    upper = make_line(5, 0, 363, 40, size=30, text="Upper story")             # narrow, left
    lower = make_line(100, 400, 1481, 440, size=30, text="Lower story")       # wide, starts at x=100
    body = []
    for i in range(5):  # upper story body
        body.append(make_line(5, 50 + i * 12, 175, 60 + i * 12, text="u"))
    for i in range(5):  # lower story, left column starts at x=5 (left of its headline)
        body.append(make_line(5, 450 + i * 12, 175, 460 + i * 12, text="l"))
        body.append(make_line(190, 450 + i * 12, 360, 460 + i * 12, text="m"))
    arts = build_articles([upper, lower] + body, page=1)
    lower_art = next(a for a in arts if a.headline == "Lower story")
    assert len(lower_art.body_lines) == 10          # BOTH columns, including the one at x=5


def test_lines_in_a_different_font_are_not_body_text(make_line):
    """Captions, kickers and boxes use other fonts. They must not become story text."""
    lines = [make_line(0, 0, 210, 30, size=30, text="Headline", font="Poynter")]
    for i in range(10):
        lines.append(make_line(0, 40 + i * 12, 200, 50 + i * 12, text=f"body{i}", font="Gulliver-Bold"))
    for i in range(3):
        lines.append(make_line(0, 200 + i * 12, 200, 210 + i * 12, text=f"CAPTION{i}", font="Scout-Bold"))
    art = build_articles(lines, page=1)[0]
    assert len(art.body_lines) == 10
    assert "CAPTION" not in art.text


# ------------------------------------------------------------------ fast, real page (no OCR)
@pytest.fixture(scope="module")
def ie1_articles(fixtures_dir):
    page = pymupdf.open(str(fixtures_dir / "ie_page1.pdf"))[0]
    return build_articles(extract.text_layer_lines(page, keep_text=False), page=1)


def test_no_story_claims_lines_below_a_wider_headline_in_its_own_columns(ie1_articles):
    """Regression: 'Adopt WHO' took the 'Judge' story's byline from below the Judge headline."""
    judge = next(a for a in ie1_articles if a.headline_lines[0].y0 > 1900)
    who = next(a for a in ie1_articles if a.headline_lines[0].x0 < 10 and 1200 < a.headline_lines[0].y0 < 1260)
    assert all(l.y0 < judge.headline_lines[0].y0 for l in who.body_lines)


def test_every_body_line_uses_the_pages_body_font(ie1_articles):
    families = {font_family(l.font) for a in ie1_articles for l in a.body_lines}
    assert families == {"Gulliver"}


# ------------------------------------------------------------------ slow: real OCR, final text
@pytest.fixture(scope="module")
def ie1_result(fixtures_dir):
    """OCR runs ONCE for the whole module (scope='module'), then every test reuses it."""
    return process_pdf(str(fixtures_dir / "ie_page1.pdf"))["pages"][0]["articles"]


def story(articles, start):
    return next(a for a in articles if (a["headline"] or "").startswith(start))


@pytest.mark.slow
@pytest.mark.parametrize("headline_start, forbidden", [
    ("No one believed us", ["SPORTS", "TRAIN KILLINGS", "DRDO ESPIONAGE", "HOCKEY"]),   # neighbours' boxes
    ("Opposition meets", ["EDITORIAL PAGE", "Rashtrapati Bhavan on Wednesday"]),         # promo + photo caption
    ("Adopt WHO", ["AISWARYARAJ", "until they were rescued"]),                           # another story's byline
])
def test_no_foreign_text_inside_story(ie1_result, headline_start, forbidden):
    text = story(ie1_result, headline_start)["text"]
    for bad in forbidden:
        assert bad not in text, f"leaked: {bad!r}"


@pytest.mark.slow
def test_continued_marker_is_metadata_not_text(ie1_result):
    assert all("CONTINUED ON PAGE" not in a["text"].upper() for a in ie1_result)
    assert story(ie1_result, "Opposition meets")["continues_on_page"] == 2


@pytest.mark.slow
def test_no_html_entities_or_column_rule_characters(ie1_result):
    for a in ie1_result:
        assert not re.search(r"&amp;|&lt;|&gt;", a["text"])
        assert " | " not in a["text"]


@pytest.mark.slow
def test_judge_story_keeps_its_own_first_paragraph(ie1_result):
    assert story(ie1_result, "Judge, her 3-yr-old").get("text", "").startswith("AMONG THE 41")
