import pytest

from pipeline.layout import (
    attach_subheads,
    build_articles,
    find_headline_groups,
    order_lines,
    split_runs,
    weighted_median_size,
)


# ------------------------------------------------------------ body size
def test_weighted_median_prefers_long_lines(make_line):
    short_big = [make_line(0, i * 50, 20, i * 50 + 40, size=40) for i in range(5)]  # many, but tiny width
    long_body = [make_line(0, 300 + i * 12, 500, 310 + i * 12, size=10) for i in range(3)]
    assert weighted_median_size(short_big + long_body) == 10


def test_weighted_median_needs_lines():
    with pytest.raises(ValueError):
        weighted_median_size([])


# ------------------------------------------------------------ headline groups
def test_two_stacked_big_lines_form_one_headline(make_line):
    lines = [make_line(0, 0, 200, 30, size=30), make_line(0, 32, 180, 62, size=30)]
    groups = find_headline_groups(lines, body_size=10)
    assert len(groups) == 1 and len(groups[0]) == 2


def test_far_apart_big_lines_are_separate_headlines(make_line):
    lines = [make_line(0, 0, 200, 30, size=30), make_line(0, 500, 200, 530, size=30)]
    assert len(find_headline_groups(lines, body_size=10)) == 2


def test_side_by_side_headlines_do_not_merge(make_line):
    lines = [make_line(0, 0, 100, 30, size=30), make_line(110, 0, 210, 30, size=30)]
    assert len(find_headline_groups(lines, body_size=10)) == 2


def test_giant_drop_cap_is_not_a_headline(make_line):
    """Regression: the huge 'E' of an 'EXPLAINED' graphic was detected as a headline."""
    drop_cap = [make_line(215, 1400, 267, 1515, size=112)]   # tall and narrow
    assert find_headline_groups(drop_cap, body_size=12.8) == []


# ------------------------------------------------------------ subheads
def test_small_big_text_under_huge_headline_becomes_subhead(make_line):
    headline = [make_line(0, 0, 400, 85, size=85)]
    sub = [make_line(0, 90, 300, 112, size=22)]
    result = attach_subheads([headline, sub])
    assert len(result) == 1
    assert result[0][1] == sub


def test_similar_size_headlines_are_not_subheads(make_line):
    """Regression: a 78pt page header swallowed the 45pt story headline right under it."""
    header = [make_line(900, 0, 1400, 80, size=78)]
    story = [make_line(900, 90, 1400, 140, size=45)]
    assert len(attach_subheads([header, story])) == 2


# ------------------------------------------------------------ assignment + order
def test_body_goes_to_closest_headline_above(fake_page):
    arts = build_articles(fake_page, page=1, min_body_lines=3)
    big, left = arts
    assert len(big.body_lines) == 10          # both columns under the wide headline
    assert len(left.body_lines) == 4          # lines below the left headline belong to it
    assert all(l.x1 <= 100 for l in left.body_lines)


def test_articles_come_out_in_page_order(fake_page):
    arts = build_articles(fake_page, page=1)
    assert [a.headline for a in arts] == ["Big story headline", "Left story"]


def test_reading_order_is_column_by_column(fake_page):
    big = build_articles(fake_page, page=1)[0]
    assert big.text.startswith("A0 words in left column A1")
    assert big.text.index("A4") < big.text.index("B0")     # finish left column, then right


def test_big_text_without_body_is_not_an_article(make_line):
    """A masthead with no body text under its columns is furniture, not a story."""
    masthead = [make_line(0, 0, 500, 100, size=60, text="THE DAILY NEWS")]
    body_elsewhere = [make_line(600, 400 + i * 12, 800, 410 + i * 12, text="x") for i in range(30)]
    assert build_articles(masthead + body_elsewhere, page=1) == []


def test_no_lines_gives_no_articles():
    assert build_articles([], page=1) == []


def test_scrambled_layer_leaves_text_unset(make_line):
    """Hybrid path: geometry only (text=None). OCR fills the text later."""
    lines = [make_line(0, 0, 210, 30, size=30)] + [
        make_line(0, 40 + i * 12, 200, 50 + i * 12) for i in range(10)
    ]
    art = build_articles(lines, page=1)[0]
    assert art.headline is None and art.text == ""
    assert len(art.body_lines) == 10


# ------------------------------------------------------------ helpers
def test_order_lines_two_columns(make_line):
    lines = [
        make_line(110, 0, 200, 10, text="B0"), make_line(0, 12, 100, 22, text="A1"),
        make_line(0, 0, 100, 10, text="A0"), make_line(110, 12, 200, 22, text="B1"),
    ]
    assert [l.text for l in order_lines(lines)] == ["A0", "A1", "B0", "B1"]


def test_split_runs_breaks_on_big_gap(make_line):
    near = [make_line(0, 0, 100, 10), make_line(0, 12, 100, 22)]
    far = [make_line(0, 400, 100, 410)]          # a photo sits in between
    runs = split_runs(near + far)
    assert [len(r) for r in runs] == [2, 1]
