"""Pure layout logic: lines in, articles out. No PDF, no OCR, no I/O.

Idea: a headline is a line (or stack of lines) printed much larger than body text.
Body lines belong to the closest headline above them whose horizontal span covers them.
"""
from __future__ import annotations

import re
from collections import defaultdict
from statistics import median

from .schema import Article, BBox, Line, union_bbox, x_overlap
from .textutil import join_lines


# ---------------------------------------------------------------- body size
def weighted_median_size(lines: list[Line]) -> float:
    """Typical body text size: median of line sizes, weighted by line width.

    Weighting by width makes the long body lines outvote the many short big ones.
    """
    if not lines:
        raise ValueError("no lines")
    pairs = sorted((l.size, l.width) for l in lines)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for size, width in pairs:
        acc += width
        if acc >= total / 2:
            return size
    return pairs[-1][0]


# ---------------------------------------------------------------- fonts
def font_family(font: str) -> str:
    """'Gulliver-Italic-OV-BOLDW' -> 'Gulliver'. Italic/bold variants count as the same family."""
    return re.split(r"[-_]", font)[0] if font else ""


def dominant_body_family(lines: list[Line], body_size: float, band: float = 0.25) -> str:
    """The font family that most body-sized text is set in ('' if fonts are unknown).

    Captions, kickers, bylines, teaser boxes and ads are usually set in other fonts,
    so 'is this the body font?' is a strong test for 'is this story text?'.
    """
    widths: dict[str, float] = defaultdict(float)
    for l in lines:
        if l.font and abs(l.size - body_size) <= band * body_size:
            widths[font_family(l.font)] += l.width
    return max(widths.items(), key=lambda kv: kv[1])[0] if widths else ""


# ---------------------------------------------------------------- headlines
def _group_box(group: list[Line]) -> BBox:
    return union_bbox([l.bbox for l in group])


def _group_size(group: list[Line]) -> float:
    return max(l.size for l in group)


def _same_headline(a: Line, b: Line) -> bool:
    """Are two big lines consecutive lines of one headline?"""
    top, bottom = (a, b) if a.y0 <= b.y0 else (b, a)
    size_ratio = min(a.size, b.size) / max(a.size, b.size)
    gap = bottom.y0 - top.y1
    overlap = x_overlap(a.bbox, b.bbox)
    return (
        size_ratio >= 0.8
        and gap <= 0.6 * max(a.size, b.size)
        and overlap >= 0.3 * min(a.width, b.width)
    )


def find_headline_groups(
    lines: list[Line], body_size: float, factor: float = 1.6, min_width_factor: float = 6.0
) -> list[list[Line]]:
    """Cluster lines >= factor * body_size into headline groups (stacked lines).

    Groups narrower than min_width_factor * body_size are rejected: a lone giant
    letter (drop cap, icon) is not a headline.
    """
    cands = sorted((l for l in lines if l.size >= factor * body_size), key=lambda l: (l.y0, l.x0))
    parent = list(range(len(cands)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            if _same_headline(cands[i], cands[j]):
                parent[find(j)] = find(i)

    groups: dict[int, list[Line]] = {}
    for i, line in enumerate(cands):
        groups.setdefault(find(i), []).append(line)
    result = [sorted(g, key=lambda l: (l.y0, l.x0)) for g in groups.values()]
    return [g for g in result if _group_box(g)[2] - _group_box(g)[0] >= min_width_factor * body_size]


def attach_subheads(
    groups: list[list[Line]], size_factor: float = 2.0, max_gap_factor: float = 2.0
) -> list[tuple[list[Line], list[Line]]]:
    """Merge smaller big-text groups sitting right under a larger one (sub-headlines).

    Returns [(headline_lines, subhead_lines), ...] for the groups that stay top-level.
    """
    order = sorted(range(len(groups)), key=lambda i: -_group_size(groups[i]))
    root_of: dict[int, int] = {}
    subs: dict[int, list[int]] = {}

    for i in order:
        gb, gs = _group_box(groups[i]), _group_size(groups[i])
        best, best_gap = None, None
        for j in order:
            if j == i or _group_size(groups[j]) < size_factor * gs:
                continue
            hb = _group_box(groups[j])
            gap = gb[1] - hb[3]
            if gap < -gs or gap > max_gap_factor * gs:
                continue
            if x_overlap(hb, gb) < 0.5 * (gb[2] - gb[0]):
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = j, gap
        if best is not None:
            while best in root_of:  # climb to the top-level headline
                best = root_of[best]
            root_of[i] = best
            subs.setdefault(best, []).append(i)

    result = []
    for i in range(len(groups)):
        if i in root_of:
            continue
        sub_lines = sorted((l for k in subs.get(i, []) for l in groups[k]), key=lambda l: (l.y0, l.x0))
        result.append((groups[i], sub_lines))
    return result


# ---------------------------------------------------------------- body assignment
def assign_body_lines(
    lines: list[Line],
    headlines: list[tuple[list[Line], list[Line]]],
    body_size: float,
    size_band: tuple[float, float] = (0.6, 1.5),
    body_family: str = "",
    column_width: float | None = None,
) -> list[list[Line]]:
    """For each headline, collect body lines.

    A line belongs to the CLOSEST headline above it whose horizontal span covers the
    line's COLUMN. The column is estimated as [line.x0, line.x0 + column_width], not just
    the line itself, so short lines (bylines) still count as being 'in' their column.
    Lines set in a different font than the body (captions, kickers, boxes) are skipped.
    """
    used = {id(l) for h, s in headlines for l in h + s}
    boxes = [_group_box(h) for h, _ in headlines]
    bodies: list[list[Line]] = [[] for _ in headlines]
    lo, hi = size_band[0] * body_size, size_band[1] * body_size
    col_w = column_width or body_size * 10

    for line in lines:
        if id(line) in used or not (lo <= line.size <= hi):
            continue
        if body_family and font_family(line.font) != body_family:
            continue
        slot = (line.x0, line.y0, line.x0 + max(line.width, col_w), line.y1)
        best, best_dist = None, None
        for k, hb in enumerate(boxes):
            if line.y0 < hb[3] - 0.5 * body_size:
                continue  # headline is not above this line
            if x_overlap(slot, hb) < 0.3 * (slot[2] - slot[0]):
                continue  # headline does not cover enough of this line's column
            dist = line.y0 - hb[3]
            if best_dist is None or dist < best_dist:
                best, best_dist = k, dist
        if best is not None:
            bodies[best].append(line)
    return bodies


# ---------------------------------------------------------------- reading order
def order_lines(lines: list[Line]) -> list[Line]:
    """Column-by-column reading order: left column top to bottom, then the next, ..."""
    if not lines:
        return []
    gap = 0.3 * median(l.width for l in lines)
    columns: list[list[Line]] = []
    prev_x = None
    for line in sorted(lines, key=lambda l: l.x0):
        if prev_x is None or line.x0 - prev_x > gap:
            columns.append([])
        columns[-1].append(line)
        prev_x = line.x0
    return [l for col in columns for l in sorted(col, key=lambda l: l.y0)]


def split_runs(lines: list[Line], max_gap_factor: float = 3.0) -> list[list[Line]]:
    """Split an ordered column of lines where a big vertical gap (photo, ad) interrupts it.

    Used before OCR so we don't feed photographs to the OCR engine.
    """
    runs: list[list[Line]] = []
    for line in lines:
        if runs:
            last = runs[-1][-1]
            same_column = abs(line.x0 - last.x0) <= 0.3 * max(last.width, 1)
            if same_column and 0 <= line.y0 - last.y1 <= max_gap_factor * max(last.height, 1):
                runs[-1].append(line)
                continue
        runs.append([line])
    return runs


# ---------------------------------------------------------------- putting it together
def build_articles(
    lines: list[Line], page: int, factor: float = 1.6, min_body_lines: int = 3
) -> list[Article]:
    """Lines of one page -> articles (headline + sub-headline + ordered body lines)."""
    if not lines:
        return []
    body_size = weighted_median_size(lines)
    groups = find_headline_groups(lines, body_size, factor)
    headlines = attach_subheads(groups)
    family = dominant_body_family(lines, body_size)
    in_band = [l.width for l in lines if abs(l.size - body_size) <= 0.25 * body_size]
    bodies = assign_body_lines(
        lines, headlines, body_size, body_family=family,
        column_width=median(in_band) if in_band else None,
    )

    articles = []
    for (h_lines, s_lines), body in zip(headlines, bodies, strict=True):
        if len(body) < min_body_lines:
            continue  # masthead, ad slogan, stray big text: not a story
        ordered = order_lines(body)
        art = Article(page=page, headline_lines=h_lines, subhead_lines=s_lines, body_lines=ordered)
        if all(l.text is not None for l in h_lines):
            art.headline = join_lines([l.text or "" for l in h_lines])
        if s_lines and all(l.text is not None for l in s_lines):
            art.subhead = join_lines([l.text or "" for l in s_lines])
        if all(l.text is not None for l in ordered):
            art.text = join_lines([l.text or "" for l in ordered])
        articles.append(art)
    return sorted(articles, key=lambda a: (a.bbox[1], a.bbox[0]))
