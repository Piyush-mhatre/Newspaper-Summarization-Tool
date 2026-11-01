"""Core data types. Everything else in the pipeline passes these around."""
from __future__ import annotations

from dataclasses import dataclass, field

BBox = tuple[float, float, float, float]  # x0, y0, x1, y1 (y grows downward)


def union_bbox(boxes: list[BBox]) -> BBox:
    """Smallest box containing all the given boxes."""
    if not boxes:
        raise ValueError("union_bbox needs at least one box")
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def x_overlap(a: BBox, b: BBox) -> float:
    """Horizontal overlap length of two boxes (0 if they don't overlap)."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))


@dataclass(frozen=True)
class Line:
    """One printed line of text.

    `size` is the font size (text-layer path) or line height in pixels (OCR path).
    Only ratios between sizes matter, so the two are interchangeable.
    `text` is None when the text layer exists but its characters are unreadable.
    """

    bbox: BBox
    size: float
    text: str | None = None
    font: str = ""

    @property
    def x0(self) -> float: return self.bbox[0]
    @property
    def y0(self) -> float: return self.bbox[1]
    @property
    def x1(self) -> float: return self.bbox[2]
    @property
    def y1(self) -> float: return self.bbox[3]
    @property
    def width(self) -> float: return self.bbox[2] - self.bbox[0]
    @property
    def height(self) -> float: return self.bbox[3] - self.bbox[1]
    @property
    def cx(self) -> float: return (self.bbox[0] + self.bbox[2]) / 2


@dataclass
class Article:
    page: int
    headline_lines: list[Line]
    subhead_lines: list[Line] = field(default_factory=list)
    body_lines: list[Line] = field(default_factory=list)
    headline: str | None = None
    subhead: str | None = None
    text: str = ""
    summary: str = ""
    continues_on_page: int | None = None
    method: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def bbox(self) -> BBox:
        return union_bbox([l.bbox for l in self.headline_lines + self.subhead_lines + self.body_lines])

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "type": "news",  # classifier arrives in milestone 4; everything is "news" for now
            "headline": self.headline,
            "subhead": self.subhead,
            "text": self.text,
            "summary": self.summary,
            "continues_on_page": self.continues_on_page,
            "bbox": [round(v, 1) for v in self.bbox],
            "method": self.method,
            "warnings": self.warnings,
        }
