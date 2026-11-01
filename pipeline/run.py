"""Glue: PDF path in, JSON-ready dict out. Also the command-line entry point.

    python -m pipeline.run paper.pdf --pages 1 --out result.json
"""
from __future__ import annotations

import argparse
import json
import time

import pymupdf

from . import extract
from .bylines import strip_byline
from .layout import build_articles, split_runs
from .quality import choose_path
from .schema import Article, Line, union_bbox, x_overlap
from .summarize import summarize
from .textutil import clean_ocr_line, extract_continued, join_lines


def find_continued_marker(art: Article, page: pymupdf.Page, all_lines: list[Line], own: set) -> int | None:
    """Look just below the last line of each column for a 'CONTINUED ON PAGE N' line.

    That marker is set in a different font than the body, so it is not in the story text.
    We only OCR the few small lines sitting right under a column's end.
    """
    found = ""
    for run in split_runs(art.body_lines):
        last = run[-1]
        for l in all_lines:
            if id(l) in own or l.size > 1.5 * last.size:
                continue
            gap = l.y0 - last.y1
            overlap = x_overlap(l.bbox, last.bbox)
            if -2 <= gap <= 2.5 * last.height and overlap >= 0.5 * min(l.width, last.width):
                found += " " + " ".join(extract.ocr_text(page, l.bbox, psm=7))
    return extract_continued(found)[1]


def fill_text_by_ocr(articles: list[Article], page: pymupdf.Page, all_lines: list[Line]) -> None:
    """Hybrid path: layout came from the unreadable text layer, so OCR just the regions.

    For each region we paint over every line that belongs to a DIFFERENT story (or to no
    story at all: captions, boxes, ads), so their text cannot leak into this one.
    """
    for art in articles:
        own = {id(l) for l in art.headline_lines + art.subhead_lines + art.body_lines}
        foreign = [extract.inset(l.bbox) for l in all_lines if id(l) not in own]

        def read(lines: list[Line], foreign: list = foreign) -> list[str]:
            box = union_bbox([l.bbox for l in lines])
            return [clean_ocr_line(t) for t in extract.ocr_text(page, box, mask_boxes=foreign)]

        art.headline = join_lines(read(art.headline_lines)) or None
        if art.subhead_lines:
            art.subhead = join_lines(read(art.subhead_lines)) or None
        body: list[str] = []
        for run in split_runs(art.body_lines):
            body += read(run)
        art.text = join_lines(body)
        art.continues_on_page = find_continued_marker(art, page, all_lines, own)


def analyze_page(page: pymupdf.Page, page_no: int, ocr: bool = True, ocr_upscale: float = 1.5):
    """Stage A (no reading of letters in the hybrid case): which path, which lines, which articles.

    Returns (path, lines, articles). The debug overlay calls this on its own.
    """
    geometry = extract.text_layer_lines(page, keep_text=True)
    path = choose_path(page.get_text(), len(geometry))

    if path == "text_layer":
        lines = geometry
    elif path == "hybrid":
        lines = extract.text_layer_lines(page, keep_text=False)
    elif ocr:
        lines = extract.ocr_lines(extract.render_page(page, 1.0), upscale=ocr_upscale)
    else:
        lines = []

    # OCR line heights are noisier than real font sizes, so demand a bigger size jump.
    articles = build_articles(lines, page_no, factor=2.2 if path == "ocr" else 1.6)
    return path, lines, articles


def finish_articles(path: str, articles: list[Article], page: pymupdf.Page, lines: list[Line], ocr: bool = True) -> None:
    """Stage B: read the letters (hybrid), clean the text, find 'continued', summarise."""
    if path == "hybrid" and ocr and articles:
        fill_text_by_ocr(articles, page, lines)

    for art in articles:
        art.text, found = extract_continued(art.text)
        art.continues_on_page = found or art.continues_on_page
        art.method = {"path": path, "summary": "extractive"}
        art.summary = summarize(strip_byline(art.text))
        if not art.headline:
            art.warnings.append("headline missing")
        if len(art.text.split()) < 20:
            art.warnings.append("very little body text")


def process_page(page: pymupdf.Page, page_no: int, ocr: bool = True, ocr_upscale: float = 1.5) -> dict:
    t0 = time.time()
    path, lines, articles = analyze_page(page, page_no, ocr, ocr_upscale)
    finish_articles(path, articles, page, lines, ocr)
    return {"page": page_no, "path": path, "seconds": round(time.time() - t0, 1),
            "articles": [a.to_dict() for a in articles]}


def process_pdf(pdf_path: str, pages: list[int] | None = None, ocr: bool = True) -> dict:
    """Process 1-based `pages` (default: all) one at a time to keep memory low."""
    with pymupdf.open(pdf_path) as doc:
        wanted = pages or list(range(1, doc.page_count + 1))
        results = [process_page(doc[n - 1], n, ocr=ocr) for n in wanted if 1 <= n <= doc.page_count]
    return {"file": pdf_path, "pages": results}


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract articles from a newspaper PDF")
    ap.add_argument("pdf")
    ap.add_argument("--pages", type=int, nargs="*", help="1-based page numbers (default: all)")
    ap.add_argument("--no-ocr", action="store_true", help="layout only, skip OCR")
    ap.add_argument("--out", help="write JSON here instead of printing")
    args = ap.parse_args()
    result = process_pdf(args.pdf, args.pages, ocr=not args.no_ocr)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
