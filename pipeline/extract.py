"""I/O layer: touches PDFs and Tesseract. Keep logic out of here (it's hard to test)."""
from __future__ import annotations

from collections import defaultdict
from statistics import median

import pymupdf
import pytesseract
from PIL import Image
from pytesseract import Output

from .schema import BBox, Line


def text_layer_lines(page: pymupdf.Page, keep_text: bool) -> list[Line]:
    """Lines (box, size, font) from the PDF text layer.

    keep_text=False is used for scrambled layers: geometry is real, characters are not.
    """
    out: list[Line] = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for ln in block["lines"]:
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            biggest = max(spans, key=lambda s: s["size"])
            text = "".join(s["text"] for s in ln["spans"]).strip() if keep_text else None
            out.append(Line(tuple(ln["bbox"]), biggest["size"], text, biggest["font"].split("+")[-1]))
    return out


def render_page(page: pymupdf.Page, zoom: float = 1.0) -> Image.Image:
    """Render a whole page. zoom=1.0 equals the page's size in points.

    For a pure scan (one full-page image) zoom=1.0 reproduces the scan's own pixels.
    """
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def inset(bbox: BBox, fraction: float = 0.2) -> BBox:
    """Shrink a box top and bottom by `fraction` of its height.

    Line boxes of consecutive lines overlap a little. Shrinking the boxes we paint over
    makes sure we never erase the edge of the neighbouring line we want to keep.
    """
    x0, y0, x1, y1 = bbox
    d = (y1 - y0) * fraction
    return (x0, y0 + d, x1, y1 - d)


def render_clip(
    page: pymupdf.Page, bbox: BBox, zoom: float = 2.5, pad: float = 3.0,
    mask_boxes: list[BBox] | tuple = (),
) -> Image.Image:
    """Render just one rectangle of the page at high zoom, optionally painting boxes white.

    On vector pages this is crisp (no upscaling blur) and uses little memory.
    mask_boxes: regions (page coordinates) to blank out BEFORE OCR. We pass the lines of
    OTHER stories, so OCR can only read text that belongs to this one.
    """
    x0, y0, x1, y1 = bbox
    clip = pymupdf.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
    if clip.is_empty:
        return Image.new("L", (1, 1), 255)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, colorspace=pymupdf.csGRAY)
    for m in mask_boxes:
        r = pymupdf.Rect(m) & clip
        if r.is_empty:
            continue
        irect = pymupdf.IRect(
            int((r.x0 - clip.x0) * zoom), int((r.y0 - clip.y0) * zoom),
            int((r.x1 - clip.x0) * zoom) + 1, int((r.y1 - clip.y0) * zoom) + 1,
        ) & pymupdf.IRect(0, 0, pix.width, pix.height)
        if not irect.is_empty:
            pix.set_rect(irect, (255,))  # 255 = white in grayscale
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def split_on_gaps(spans: list[tuple[float, float]], max_gap: float) -> list[list[int]]:
    """Group word spans (left, right), sorted by left, splitting where the gap > max_gap.

    Tesseract sometimes returns one 'line' that crosses a column gutter. Splitting at
    wide gaps restores one line per column.
    """
    groups: list[list[int]] = []
    right_edge = None
    for i, (left, right) in enumerate(spans):
        if right_edge is None or left - right_edge > max_gap:
            groups.append([])
        groups[-1].append(i)
        right_edge = right if right_edge is None or groups[-1] == [i] else max(right_edge, right)
    return groups


def ocr_lines(img: Image.Image, upscale: float = 1.0) -> list[Line]:
    """Full-page OCR -> lines with boxes (in the image's own pixel coordinates)."""
    work = img if upscale == 1 else img.resize(
        (int(img.width * upscale), int(img.height * upscale)), Image.Resampling.LANCZOS
    )
    data = pytesseract.image_to_data(work, output_type=Output.DICT, config="--psm 3")
    grouped: dict[tuple, list[int]] = defaultdict(list)
    for i, word in enumerate(data["text"]):
        if word.strip() and float(data["conf"][i]) >= 0:
            grouped[(data["block_num"][i], data["par_num"][i], data["line_num"][i])].append(i)

    lines = []
    for idxs in grouped.values():
        idxs = sorted(idxs, key=lambda i: data["left"][i])
        gap = 2.5 * median(data["height"][i] for i in idxs)
        spans = [(data["left"][i], data["left"][i] + data["width"][i]) for i in idxs]
        for seg in split_on_gaps(spans, gap):
            ids = [idxs[k] for k in seg]
            x0 = min(data["left"][i] for i in ids) / upscale
            y0 = min(data["top"][i] for i in ids) / upscale
            x1 = max(data["left"][i] + data["width"][i] for i in ids) / upscale
            y1 = max(data["top"][i] + data["height"][i] for i in ids) / upscale
            size = median(data["height"][i] for i in ids) / upscale
            lines.append(Line((x0, y0, x1, y1), size, " ".join(data["text"][i] for i in ids)))
    return lines


def ocr_text(
    page: pymupdf.Page, bbox: BBox, zoom: float = 2.5, psm: int = 6,
    mask_boxes: list[BBox] | tuple = (),
) -> list[str]:
    """OCR one rectangle of a page (rendered crisply from the PDF); return its text lines."""
    img = render_clip(page, bbox, zoom, mask_boxes=mask_boxes)
    if img.width < 4 or img.height < 4:
        return []
    text = pytesseract.image_to_string(img, config=f"--psm {psm}")
    return [ln for ln in text.splitlines() if ln.strip()]
