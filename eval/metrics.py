"""Measurement tools. 'Super accurate' only means something if we can compute it."""
from __future__ import annotations

import re


def levenshtein(a: str, b: str) -> int:
    """Minimum single-character edits (insert/delete/replace) to turn a into b."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate: edits / reference length. 0.0 = perfect. Can exceed 1.0."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return levenshtein(reference, hypothesis) / len(reference)


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse spaces, so tiny OCR differences don't count."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", text.lower())).strip()


def headline_similarity(reference: str, hypothesis: str) -> float:
    """1.0 = identical after normalising, 0.0 = completely different."""
    a, b = normalize(reference), normalize(hypothesis)
    if not a and not b:
        return 1.0
    return max(0.0, 1 - levenshtein(a, b) / max(len(a), len(b)))


def iou(a: tuple, b: tuple) -> float:
    """Intersection-over-union of two boxes (x0, y0, x1, y1). Used to score article boundaries."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
