"""Heuristic matching of the same event across venues (title similarity + end date)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from .models import Quote

_STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "be", "will", "is", "by", "for", "and", "or"}
# Wording that differs across venues for the same question ("win the nomination" vs "be the nominee").
_STOP |= {"win", "wins", "become", "becomes", "become", "elected"}
_SYNONYMS = {"nomination": "nominee", "nominate": "nominee", "nominated": "nominee", "nominees": "nominee"}


def _tokens(title: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", title.lower())
    return [_SYNONYMS.get(t, t) for t in toks if t not in _STOP]


def similarity(t1: str, t2: str) -> float:
    a, b = _tokens(t1), _tokens(t2)
    if not a or not b:
        return 0.0
    jaccard = len(set(a) & set(b)) / len(set(a) | set(b))
    seq = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    return 0.5 * jaccard + 0.5 * seq


def _parse(d: Optional[str]) -> Optional[datetime]:
    if not d:
        return None
    try:
        dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def dates_compatible(d1: Optional[str], d2: Optional[str], max_days: float = 2.0) -> bool:
    a, b = _parse(d1), _parse(d2)
    if a is None or b is None:
        return True  # unknown: do not reject, the caveat tells the user to check
    return abs((a - b).total_seconds()) <= max_days * 86400


def match_markets(
    left: list[Quote],
    right: list[Quote],
    threshold: float = 0.85,
    min_shared: int = 2,
    max_df: int = 300,
    max_days: Optional[float] = 2.0,
) -> list[tuple[Quote, Quote, float]]:
    """Greedy one-to-one matching, best scores first. Returns (left, right, score).

    Candidate pairs come from an inverted index on title tokens (at least `min_shared` shared
    tokens, ignoring tokens present in more than `max_df` right titles), so the cost stays
    far below comparing every pair.
    """
    rtoks = [set(_tokens(r.title)) for r in right]
    index: dict[str, list[int]] = defaultdict(list)
    for j, toks in enumerate(rtoks):
        for t in toks:
            index[t].append(j)
    scored = []
    for i, l in enumerate(left):
        ltoks = set(_tokens(l.title))
        shared: Counter = Counter()
        for t in ltoks:
            postings = index.get(t, ())
            if len(postings) > max_df:
                continue
            shared.update(postings)
        for j, c in shared.items():
            if c < min(min_shared, len(ltoks), len(rtoks[j])):
                continue
            r = right[j]
            if max_days is not None and not dates_compatible(l.end_date, r.end_date, max_days):
                continue
            s = similarity(l.title, r.title)
            if s >= threshold:
                scored.append((s, i, j))
    scored.sort(reverse=True)
    used_l: set[int] = set()
    used_r: set[int] = set()
    out = []
    for s, i, j in scored:
        if i in used_l or j in used_r:
            continue
        used_l.add(i)
        used_r.add(j)
        out.append((left[i], right[j], s))
    return out
