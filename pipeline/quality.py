"""Decide whether a page's text layer can be trusted.

Some PDFs (including our Indian Express sample) carry a text layer whose
characters are glyph IDs, not letters. The geometry is still valid, the text is not.
"""
from __future__ import annotations

import re

_PUNCT = set(".,;:!?'\"()-%&/$₹“”‘’–—@")

# Very common English words. Real English text is full of them; garbage is not.
COMMON_WORDS = frozenset(
    ["the", "of", "and", "to", "in", "a", "is", "that", "for", "it", "as", "was", "with", "be", "by", "on", "not", "he", "this", "are", "or", "his", "from", "at", "which", "but", "have", "an", "had", "they", "you", "were", "their", "one", "all", "we", "can", "her", "has", "there", "been", "if", "more", "when", "will", "would", "who", "so", "no", "said", "its", "after", "also", "over", "than", "into", "out", "up", "about", "says"]
)


def readable_ratio(text: str) -> float:
    """Share of non-whitespace characters that are letters, digits or normal punctuation."""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    ok = sum(1 for c in chars if c.isalnum() or c in _PUNCT)
    return ok / len(chars)


def common_word_ratio(text: str) -> float:
    """Share of word tokens that are very common English words."""
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    if not tokens:
        return 0.0
    return sum(t in COMMON_WORDS for t in tokens) / len(tokens)


def is_text_usable(text: str, min_tokens: int = 30) -> bool:
    """True if the text looks like real English prose, not scrambled glyph IDs."""
    if len(re.findall(r"[A-Za-z']+", text)) < min_tokens:
        return False
    return readable_ratio(text) >= 0.85 and common_word_ratio(text) >= 0.10


def choose_path(text: str, n_geometry_lines: int) -> str:
    """Pick how to extract a page: 'text_layer', 'hybrid' or 'ocr'."""
    if is_text_usable(text):
        return "text_layer"
    if n_geometry_lines >= 20:  # unreadable text, but real line boxes we can still use
        return "hybrid"
    return "ocr"
