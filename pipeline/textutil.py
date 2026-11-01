"""Small, pure text helpers."""
from __future__ import annotations

import html
import re


def join_lines(lines: list[str]) -> str:
    """Join printed lines into prose, repairing end-of-line hyphenation.

    'govern-' + 'ment' -> 'government'. But 'twenty-' + 'One' keeps its hyphen,
    because the next word is capitalised (probably a real compound).
    """
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not out:
            out = line
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha() and (
            line[:1].islower() or re.match(r"[Il]\s+[a-z]", line)
        ):
            # hyphenated word split across lines; a lone 'I' or 'l' first is the column rule
            out = out[:-1] + re.sub(r"^[Il]\s+(?=[a-z])", "", line)
        else:
            out += " " + line
    return re.sub(r"\s+", " ", out).strip()


def clean_ocr_line(line: str) -> str:
    """Remove OCR artefacts from one line.

    - HTML entities (&amp; -> &)
    - '|' characters: the thin rule between newspaper columns, read as a letter
    - a capital 'I' left dangling after a hyphen (also the rule): 'govern- I' -> 'govern-'
    """
    line = html.unescape(line).replace("|", " ")
    line = re.sub(r"(?<=-)\s+[Il]\s*$", "", line)
    return re.sub(r"\s+", " ", line).strip()


_CONTINUED = re.compile(r"\s*CONTINUED\s+ON\s+PAGE\s+(\d+)\s*", re.IGNORECASE)


def extract_continued(text: str) -> tuple[str, int | None]:
    """Remove a 'CONTINUED ON PAGE N' marker; return (clean text, N or None)."""
    match = _CONTINUED.search(text)
    if not match:
        return text, None
    cleaned = (text[: match.start()] + " " + text[match.end():]).strip()
    return re.sub(r"\s+", " ", cleaned), int(match.group(1))
