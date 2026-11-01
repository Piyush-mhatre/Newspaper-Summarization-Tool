import pytest
from PIL import Image

from pipeline import debug
from pipeline.layout import build_articles


@pytest.mark.parametrize("size, expected", [
    (30, "big"), (16.1, "big"), (15.9, "body"),   # boundary: 1.6 x body(10) = 16
    (10, "body"), (6, "body"), (5.9, "tiny"),
])
def test_size_class(size, expected):
    assert debug.size_class(size, body_size=10) == expected


def test_article_colors_are_distinct_then_cycle():
    first_ten = [debug.article_color(i) for i in range(10)]
    assert len(set(first_ten)) == 10
    assert debug.article_color(10) == debug.article_color(0)


def test_line_roles_label_every_line(fake_page, make_line):
    stray = make_line(500, 500, 600, 510, text="caption nobody owns")
    lines = fake_page + [stray]
    arts = build_articles(lines, page=1)
    roles = debug.line_roles(lines, arts)
    assert roles[id(arts[0].headline_lines[0])] == ("headline", 0)
    assert roles[id(arts[1].body_lines[0])] == ("body", 1)
    assert roles[id(stray)] == ("ignored", None)
    assert len(roles) == len(lines)                      # nothing left unlabeled


def test_summary_counts_add_up(fake_page, make_line):
    lines = fake_page + [make_line(500, 500, 600, 510)]
    arts = build_articles(lines, page=1)
    n = debug.summary_counts(lines, arts)
    assert n["used"] + n["ignored"] == n["total"] == len(lines)
    assert n["articles"] == 2 and n["ignored"] == 1


def test_debug_run_writes_three_pictures_and_a_report(tmp_path, fixtures_dir):
    """tmp_path = a fresh empty folder pytest gives each test and cleans up afterwards."""
    info = debug.run(str(fixtures_dir / "ie_page1.pdf"), 1, tmp_path, ocr=False)
    for name in ("page1_1_lines.png", "page1_2_ownership.png", "page1_3_articles.png", "page1_report.html"):
        assert (tmp_path / name).exists(), name
    assert Image.open(tmp_path / "page1_3_articles.png").width == 1000
    assert info["path"] == "hybrid" and info["articles"] == 10
    assert info["used"] + info["ignored"] == info["total"]
