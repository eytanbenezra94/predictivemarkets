"""Diagnostics for the cross-venue matcher: does it find pairs on real data, and are they right?"""
from __future__ import annotations

from typing import Optional, Sequence

from .matching import match_markets
from .models import Quote


def match_stats(
    poly: list[Quote],
    kalshi: list[Quote],
    thresholds: Sequence[float] = (0.6, 0.7, 0.75, 0.85, 0.95),
    max_days: Optional[float] = 2.0,
) -> dict:
    """Number of one-to-one matched pairs at each similarity threshold (`max_days=None`: ignore end dates)."""
    return {t: len(match_markets(poly, kalshi, t, max_days=max_days)) for t in thresholds}


def raw_cross_sum(p: Quote, k: Quote) -> Optional[tuple[float, str]]:
    """Cheapest way to hold both outcomes across the two venues, before fees and slippage.

    Returns (cost, direction) or None when neither direction has both asks. A cost below 1
    would be a gap before frictions.
    """
    options = []
    if p.yes_ask is not None and k.no_ask is not None:
        options.append((p.yes_ask + k.no_ask, "YES@polymarket + NO@kalshi"))
    if k.yes_ask is not None and p.no_ask is not None:
        options.append((k.yes_ask + p.no_ask, "YES@kalshi + NO@polymarket"))
    return min(options) if options else None
