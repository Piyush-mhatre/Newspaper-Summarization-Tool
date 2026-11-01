"""Baseline extractive summariser (offline, instant, no downloads).

Improvements over the old frequency scorer:
- length-normalised scores, so long sentences don't win automatically
- sentences are returned in their ORIGINAL order, so the summary reads naturally
- tiny built-in stopword list, so no NLTK downloads at import time
"""
from __future__ import annotations

import re
from collections import Counter

STOPWORDS = frozenset(
    ["a", "an", "the", "and", "or", "but", "if", "then", "of", "to", "in", "on", "at", "by", "for", "with", "from", "as", "is", "are", "was", "were", "be", "been", "being", "it", "its", "this", "that", "these", "those", "he", "she", "they", "them", "his", "her", "their", "we", "you", "i", "not", "no", "so", "than", "also", "has", "have", "had", "will", "would", "can", "could", "should", "may", "might", "do", "does", "did", "said", "says", "after", "before", "over", "into", "out", "up", "about", "which", "who", "whom", "what", "when", "where", "while"]
)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘'])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _tokens(sentence: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", sentence.lower()) if w not in STOPWORDS]


def summarize(text: str, max_sentences: int = 3) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return ""
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    freq = Counter(t for s in sentences for t in _tokens(s))
    top = max(freq.values(), default=1)
    scored = []
    for i, sent in enumerate(sentences):
        toks = _tokens(sent)
        n_words = len(sent.split())
        if n_words < 5 or n_words > 60 or not toks:
            continue
        score = sum(freq[t] / top for t in set(toks)) / (len(toks) + 5)
        if i == 0:
            score *= 1.25  # news leads with the key facts
        scored.append((score, i))

    chosen = sorted(i for _, i in sorted(scored, reverse=True)[:max_sentences])
    return " ".join(sentences[i] for i in chosen)
