"""Tests on the real sample PDFs.

Layout-only tests are fast. Tests marked `slow` run real OCR:  pytest -m slow
"""
import pymupdf
import pytest

from eval.metrics import headline_similarity
from pipeline import extract
from pipeline.layout import build_articles
from pipeline.run import process_pdf


def test_ie_front_page_uses_hybrid_path_and_finds_the_stories(fixtures_dir):
    result = process_pdf(str(fixtures_dir / "ie_page1.pdf"), ocr=False)
    page = result["pages"][0]
    assert page["path"] == "hybrid"
    assert 9 <= len(page["articles"]) <= 12          # about 10 real stories on this page


def test_ie_page5_finds_three_stories_and_ignores_ads_and_header(fixtures_dir):
    """Regression: the 'MAHARASHTRA' header used to absorb the ISIS story's headline."""
    page = pymupdf.open(str(fixtures_dir / "ie_page5.pdf"))[0]
    arts = build_articles(extract.text_layer_lines(page, keep_text=False), page=5)
    assert len(arts) == 3                               # Desai, ISIS, 'His quest...'; ads excluded
    right_column = [a for a in arts if a.headline_lines[0].x0 > 700]
    assert len(right_column) == 1                       # the ISIS story, as its own article


def test_times_city_is_detected_as_a_pure_scan(fixtures_dir):
    page = pymupdf.open(str(fixtures_dir / "times_city.pdf"))[0]
    assert page.get_text().strip() == ""


@pytest.mark.slow
def test_ie_front_page_headlines_match_the_printed_ones(fixtures_dir):
    """Golden test: headlines read by a human from the page image."""
    printed = [
        "28% GST stays on online gaming and casinos but review after six months",
        "Opposition meets President, presses demand for PM statement on Manipur",
        "Another cheetah dies at Kuno, ninth since March",
        "No one believed us, God made video go viral: Kargil veteran whose wife in video",
    ]
    result = process_pdf(str(fixtures_dir / "ie_page1.pdf"))
    found = [a["headline"] or "" for a in result["pages"][0]["articles"]]
    for want in printed:
        best = max(headline_similarity(want, got) for got in found)
        assert best >= 0.9, f"no close match for: {want}"


@pytest.mark.slow
def test_times_city_ocr_path_finds_some_known_headlines(fixtures_dir):
    result = process_pdf(str(fixtures_dir / "times_city.pdf"))
    page = result["pages"][0]
    assert page["path"] == "ocr"
    found = [a["headline"] or "" for a in page["articles"]]
    want = "22-yr-old dies due to pothole: Road contractor booked"
    assert max(headline_similarity(want, got) for got in found) >= 0.9
