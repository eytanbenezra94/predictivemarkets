"""Scanners that combine clients and arbitrage logic."""
from __future__ import annotations

from typing import Iterable, Optional

from .arb import basket_buy, basket_sell, binary_buy, cross_venue
from .clients import parse_kalshi_market, parse_polymarket_market
from .fees import FeeFn, kalshi_taker_fee, no_fee, schedule_fee
from .matching import match_markets
from .models import Leg, Opportunity, Quote


def _fee(q: Quote, default: FeeFn) -> FeeFn:
    """Per-market fee from the venue's published schedule when there is one."""
    return schedule_fee(*q.fee_schedule) if q.fee_schedule else default


def event_basket(
    quotes: list[Quote],
    fee_fn: FeeFn,
    slippage: float,
    exhaustive: bool,
    buy_side: bool = True,
) -> list[Opportunity]:
    """Buy-all (needs exhaustive outcomes) and sell-all (needs mutual exclusivity) baskets."""
    out: list[Opportunity] = []
    if len(quotes) < 2:
        return out
    if buy_side and all(q.yes_ask is not None for q in quotes):
        legs = tuple(Leg(q.venue, q.market_id, q.title, "BUY_YES", q.yes_ask, _fee(q, fee_fn)) for q in quotes)
        opp = basket_buy(legs, slippage, exhaustive=exhaustive)
        if opp:
            out.append(opp)
    if all(q.yes_bid is not None for q in quotes):
        opp = basket_sell(
            [(q.market_id, q.title, q.yes_bid, _fee(q, fee_fn)) for q in quotes],
            fee_fn, slippage, quotes[0].venue,
        )
        if opp:
            out.append(opp)
    return out


def scan_intra_kalshi(
    markets: Iterable[Quote],
    events: Iterable[dict],
    fee_fn: FeeFn = kalshi_taker_fee,
    slippage: float = 0.0,
    include_unverified_buys: bool = False,
) -> list[Opportunity]:
    """Binary YES+NO checks plus mutually-exclusive event baskets.

    `mutually_exclusive` does NOT mean exhaustive: live events such as "next Pope" list outcomes
    whose asks sum to 0.31. Buy-side baskets are therefore off unless `include_unverified_buys`.
    """
    out = [o for q in markets if (o := binary_buy(q, fee_fn, slippage))]
    for ev in events:
        if not ev.get("mutually_exclusive"):
            continue
        quotes = [q for m in ev.get("markets", []) if (q := parse_kalshi_market(m))]
        out += event_basket(quotes, fee_fn, slippage, exhaustive=False, buy_side=include_unverified_buys)
    return sorted(out, key=lambda o: o.profit_per_set, reverse=True)


def scan_intra_polymarket(
    events: Iterable[dict],
    fee_fn: FeeFn = no_fee,
    slippage: float = 0.0,
    include_unverified_buys: bool = False,
) -> list[Opportunity]:
    """negRisk event baskets, with fees taken from each market's own `feeSchedule`.

    `negRiskAugmented` events can gain outcomes later: their listed asks often sum to 0.97-0.98
    without any arbitrage. Buy-side is skipped for them unless `include_unverified_buys`.
    """
    out: list[Opportunity] = []
    for ev in events:
        if not ev.get("negRisk"):
            continue
        augmented = bool(ev.get("negRiskAugmented"))
        quotes = [q for m in ev.get("markets", []) if (q := parse_polymarket_market(m))]
        out += event_basket(
            quotes, fee_fn, slippage, exhaustive=not augmented,
            buy_side=(not augmented) or include_unverified_buys,
        )
    return sorted(out, key=lambda o: o.profit_per_set, reverse=True)


def scan_cross(
    poly: list[Quote],
    kalshi: list[Quote],
    threshold: float = 0.75,
    poly_fee: Optional[FeeFn] = None,
    kalshi_fee: FeeFn = kalshi_taker_fee,
    slippage: float = 0.0,
) -> list[tuple[Opportunity, float]]:
    """Returns (opportunity, title match score) sorted by locked profit.

    `poly_fee=None` uses each Polymarket market's own fee schedule (zero if none is published).
    """
    out = []
    for p, k, score in match_markets(poly, kalshi, threshold):
        opp = cross_venue(p, k, poly_fee or _fee(p, no_fee), kalshi_fee, slippage)
        if opp:
            out.append((opp, score))
    return sorted(out, key=lambda t: t[0].profit_per_set, reverse=True)
