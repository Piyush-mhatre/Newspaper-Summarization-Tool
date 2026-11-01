"""Strip 'BYLINE NAME CITY, MONTH D' openings so they don't pollute summaries."""
from __future__ import annotations

import re

_BYLINE = re.compile(
    r"^[A-Z][A-Z .&'\-,]{2,100}?\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\s+\d{1,2}\s+"
)


def strip_byline(text: str) -> str:
    """Remove a leading ALL-CAPS byline + dateline, if present. Otherwise return text unchanged."""
    return _BYLINE.sub("", text, count=1)
