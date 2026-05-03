"""Text tokenizer: lowercase, strip punctuation, remove stopwords."""

from __future__ import annotations

import re

# Compact English stopword list — common words that carry no search signal
_STOPWORDS: frozenset[str] = frozenset(
    """
    a about above after again against all also am an and any are aren't as at be
    because been before being below between both but by can't cannot could couldn't
    did didn't do does doesn't doing don't down during each few for from further
    get got had hadn't has hasn't have haven't having he he'd he'll he's her here
    here's hers herself him himself his how how's i i'd i'll i'm i've if in into
    is isn't it it's its itself let's me more most mustn't my myself no nor not of
    off on once only or other ought our ours ourselves out over own same shan't she
    she'd she'll she's should shouldn't so some such than that that's the their
    theirs them themselves then there there's these they they'd they'll they're
    they've this those through to too under until up very was wasn't we we'd we'll
    we're we've were weren't what what's when when's where where's which while who
    who's whom why why's will with won't would wouldn't you you'd you'll you're
    you've your yours yourself yourselves
    """.split()
)

_NON_ALPHA = re.compile(r"[^a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Return a list of normalised, non-stopword tokens from *text*."""
    lowered = text.lower()
    tokens = _NON_ALPHA.split(lowered)
    return [t for t in tokens if t and t not in _STOPWORDS and len(t) > 1]


def tokenize_with_positions(text: str) -> dict[str, tuple[int, list[int]]]:
    """Return {term: (frequency, [position, ...])} for each token."""
    result: dict[str, tuple[int, list[int]]] = {}
    lowered = text.lower()
    tokens = _NON_ALPHA.split(lowered)
    for pos, tok in enumerate(tokens):
        if not tok or tok in _STOPWORDS or len(tok) <= 1:
            continue
        if tok in result:
            freq, positions = result[tok]
            positions.append(pos)
            result[tok] = (freq + 1, positions)
        else:
            result[tok] = (1, [pos])
    return result
