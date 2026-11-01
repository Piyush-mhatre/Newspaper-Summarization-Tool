"""Draw what the pipeline sees, so you can check it with your own eyes.

    python -m pipeline.debug paper.pdf --page 1 --out debug_out
    python -m pipeline.debug paper.pdf --page 1 --out debug_out --no-ocr    # much faster

Writes three pictures and an HTML report:
    page1_1_lines.png      every text line found, coloured by SIZE   (what the program sees)
    page1_2_ownership.png  who owns each line                         (what the program decided)
    page1_3_articles.png   the final article boxes                    (the result)
    page1_report.html     the pictures plus a table of headlines, text and summaries
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from . import extract
from .layout import weighted_median_size
from .run import analyze_page, finish_articles
from .schema import Article, Line

PALETTE = [
    (230, 25, 75), (0, 130, 200), (60, 180, 75), (245, 130, 48), (145, 30, 180),
    (0, 150, 150), (240, 50, 230), (170, 110, 40), (128, 128, 0), (0, 0, 128),
]
GREY = (150, 150, 150)
RED, GREEN, ORANGE = (220, 30, 30), (40, 160, 70), (240, 140, 30)


# ---------------------------------------------------------------- pure helpers (unit-tested)
def article_color(i: int) -> tuple[int, int, int]:
    """Same article number -> same colour in every picture. Cycles after 10 articles."""
    return PALETTE[i % len(PALETTE)]


def size_class(size: float, body_size: float, big_factor: float = 1.6) -> str:
    """'big' (headline-sized), 'body' (normal text) or 'tiny' (smaller than body)."""
    if size >= big_factor * body_size:
        return "big"
    return "body" if size >= 0.6 * body_size else "tiny"


def line_roles(lines: list[Line], articles: list[Article]) -> dict[int, tuple[str, int | None]]:
    """For every line: ('headline'|'subhead'|'body'|'ignored', article number or None)."""
    roles: dict[int, tuple[str, int | None]] = {id(l): ("ignored", None) for l in lines}
    for i, art in enumerate(articles):
        for role, group in (("headline", art.headline_lines), ("subhead", art.subhead_lines), ("body", art.body_lines)):
            for l in group:
                roles[id(l)] = (role, i)
    return roles


def summary_counts(lines: list[Line], articles: list[Article]) -> dict[str, int]:
    roles = line_roles(lines, articles)
    used = sum(1 for r, _ in roles.values() if r != "ignored")
    return {"total": len(lines), "used": used, "ignored": len(lines) - used, "articles": len(articles)}


# ---------------------------------------------------------------- drawing
def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _base_image(page: pymupdf.Page, width: int = 1000) -> tuple[Image.Image, float]:
    """The page, faded to 40% so coloured boxes stand out."""
    scale = width / page.rect.width
    gray = extract.render_page(page, zoom=scale).convert("RGB")
    return Image.blend(gray, Image.new("RGB", gray.size, "white"), 0.6), scale


def _with_banner(img: Image.Image, title: str, legend: str = "") -> Image.Image:
    """Dark strip on top: a title line and (optionally) a smaller legend line."""
    banner = 70 if legend else 46
    out = Image.new("RGB", (img.width, img.height + banner), (25, 25, 25))
    out.paste(img, (0, banner))
    draw = ImageDraw.Draw(out)
    draw.text((12, 8), title, fill="white", font=_font(24))
    if legend:
        draw.text((12, 42), legend, fill=(210, 210, 210), font=_font(16))
    return out


def _box(b, s):  # page coordinates -> picture coordinates
    return [b[0] * s, b[1] * s, b[2] * s, b[3] * s]


def draw_lines_by_size(base, scale, lines, body_size):
    img, d = base.copy(), None
    d = ImageDraw.Draw(img)
    counts = {"big": 0, "body": 0, "tiny": 0}
    colors = {"big": RED, "body": GREEN, "tiny": GREY}
    for l in lines:
        c = size_class(l.size, body_size)
        counts[c] += 1
        d.rectangle(_box(l.bbox, scale), outline=colors[c], width=2 if c == "big" else 1)
    return _with_banner(
        img, f"1. LINES FOUND: {len(lines)}",
        f"red = big text ({counts['big']})   green = body-sized ({counts['body']})   grey = tiny ({counts['tiny']})")


def draw_ownership(base, scale, lines, articles):
    img = base.copy()
    d = ImageDraw.Draw(img)
    roles = line_roles(lines, articles)
    for l in lines:                               # ignored lines first, so they sit underneath
        if roles[id(l)][0] == "ignored":
            d.rectangle(_box(l.bbox, scale), outline=GREY, width=1)
    for i, art in enumerate(articles):
        c = article_color(i)
        for l in art.body_lines:
            d.rectangle(_box(l.bbox, scale), outline=c, width=1)
        for l in art.subhead_lines:
            d.rectangle(_box(l.bbox, scale), outline=c, width=3)
        for l in art.headline_lines:
            d.rectangle(_box(l.bbox, scale), outline=c, width=5)
    n = summary_counts(lines, articles)
    return _with_banner(
        img, f"2. OWNERSHIP: {n['used']} lines used by {n['articles']} articles, {n['ignored']} ignored",
        "one colour per article   thick box = headline   medium = sub-headline   thin = body   grey = ignored")


def draw_articles(base, scale, articles):
    img = base.convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, art in enumerate(articles):
        c = article_color(i)
        b = _box(art.bbox, scale)
        d.rectangle(b, fill=c + (60,), outline=c + (255,), width=4)
        d.rectangle([b[0], b[1], b[0] + 44, b[1] + 34], fill=c + (255,))
        d.text((b[0] + 8, b[1] + 3), str(i + 1), fill="white", font=_font(26))
    out = Image.alpha_composite(img, layer).convert("RGB")
    return _with_banner(out, f"3. RESULT: {len(articles)} articles (numbers match the report table)")


# ---------------------------------------------------------------- report
def write_report(path: Path, stem: str, info: dict, articles: list[Article]) -> None:
    rows = []
    for i, a in enumerate(articles):
        r, g, b = article_color(i)
        rows.append(
            f"<tr><td style='background:rgb({r},{g},{b});color:white;font-weight:bold'>{i + 1}</td>"
            f"<td><b>{html.escape(a.headline or '(not read: --no-ocr)')}</b></td>"
            f"<td>{len(a.headline_lines)}h / {len(a.subhead_lines)}s / {len(a.body_lines)}b</td>"
            f"<td>{len(a.text.split())}</td><td>{a.continues_on_page or ''}</td>"
            f"<td>{html.escape('; '.join(a.warnings))}</td>"
            f"<td>{html.escape(a.summary or '')}</td></tr>"
        )
    path.write_text(f"""<!doctype html><meta charset="utf-8"><title>{stem} report</title>
<style>body{{font-family:sans-serif;margin:20px}} img{{max-width:100%;border:1px solid #ccc;margin:8px 0}}
table{{border-collapse:collapse}} td,th{{border:1px solid #bbb;padding:6px;vertical-align:top;font-size:14px}}</style>
<h1>{stem}</h1>
<p>Path chosen: <b>{info['path']}</b> &middot; lines found: <b>{info['total']}</b> &middot;
used: <b>{info['used']}</b> &middot; ignored: <b>{info['ignored']}</b> &middot; articles: <b>{info['articles']}</b></p>
<h2>1. What the program sees</h2><img src="{stem}_1_lines.png">
<h2>2. What it decided</h2><img src="{stem}_2_ownership.png">
<h2>3. The result</h2><img src="{stem}_3_articles.png">
<h2>Article table</h2>
<table><tr><th>#</th><th>Headline</th><th>lines (headline/sub/body)</th><th>words</th>
<th>continues on page</th><th>warnings</th><th>summary</th></tr>{''.join(rows)}</table>""", encoding="utf-8")


def run(pdf_path: str, page_no: int, out_dir: str | Path, ocr: bool = True) -> dict:
    """Make the pictures and report; return the counts. Page numbers are 1-based."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"page{page_no}"
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_no - 1]
        path, lines, articles = analyze_page(page, page_no, ocr=True)
        body_size = weighted_median_size(lines) if lines else 1.0
        base, scale = _base_image(page)
        draw_lines_by_size(base, scale, lines, body_size).save(out / f"{stem}_1_lines.png")
        draw_ownership(base, scale, lines, articles).save(out / f"{stem}_2_ownership.png")
        draw_articles(base, scale, articles).save(out / f"{stem}_3_articles.png")
        finish_articles(path, articles, page, lines, ocr=ocr)
    info = {"path": path, "body_size": round(body_size, 1), **summary_counts(lines, articles)}
    write_report(out / f"{stem}_report.html", stem, info, articles)
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description="Draw what the pipeline detected on one page")
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, default=1, help="1-based page number")
    ap.add_argument("--out", default="debug_out")
    ap.add_argument("--no-ocr", action="store_true", help="hybrid pages: skip reading letters (fast). Scans still need OCR to find lines")
    a = ap.parse_args()
    info = run(a.pdf, a.page, a.out, ocr=not a.no_ocr)
    print(f"path={info['path']}  body size={info['body_size']}  lines={info['total']}  "
          f"used={info['used']}  ignored={info['ignored']}  articles={info['articles']}")
    print(f"open {Path(a.out) / f'page{a.page}_report.html'}")


if __name__ == "__main__":
    main()
