"""Heuristic matching of the same event across venues (title similarity + end date)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from .models import Quote

_STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "be", "will", "is", "by", "for", "and", "or"}


def _tokens(title: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", title.lower()) if t not in _STOP]


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
    left: list[Quote], right: list[Quote], threshold: float = 0.75
) -> list[tuple[Quote, Quote, float]]:
    """Greedy one-to-one matching, best scores first. Returns (left, right, score)."""
    scored = []
    for i, l in enumerate(left):
        for j, r in enumerate(right):
            if not dates_compatible(l.end_date, r.end_date):
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
