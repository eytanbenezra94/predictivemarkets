"""Scanners that combine clients and arbitrage logic."""
from __future__ import annotations

from typing import Iterable

from .arb import basket_buy, basket_sell, binary_buy, cross_venue
from .clients import parse_kalshi_market, parse_polymarket_market
from .fees import FeeFn, kalshi_taker_fee, no_fee
from .matching import match_markets
from .models import Leg, Opportunity, Quote


def event_basket(
    quotes: list[Quote], fee_fn: FeeFn, slippage: float, exhaustive: bool
) -> list[Opportunity]:
    """Buy-all (needs exhaustive outcomes) and sell-all (needs mutual exclusivity) baskets."""
    out: list[Opportunity] = []
    if len(quotes) < 2:
        return out
    asks = [q for q in quotes if q.yes_ask is not None]
    if len(asks) == len(quotes):
        legs = tuple(Leg(q.venue, q.market_id, q.title, "BUY_YES", q.yes_ask, fee_fn) for q in quotes)
        opp = basket_buy(legs, slippage, exhaustive=exhaustive)
        if opp:
            out.append(opp)
    bids = [q for q in quotes if q.yes_bid is not None]
    if len(bids) == len(quotes):
        opp = basket_sell(
            [(q.market_id, q.title, q.yes_bid) for q in quotes], fee_fn, slippage, quotes[0].venue
        )
        if opp:
            out.append(opp)
    return out


def scan_intra_kalshi(
    markets: Iterable[Quote], events: Iterable[dict], fee_fn: FeeFn = kalshi_taker_fee, slippage: float = 0.0
) -> list[Opportunity]:
    out = [o for q in markets if (o := binary_buy(q, fee_fn, slippage))]
    for ev in events:
        if not ev.get("mutually_exclusive"):
            continue
        quotes = [parse_kalshi_market(m) for m in ev.get("markets", [])]
        # Kalshi does not flag exhaustiveness, so buy-side results always carry a caveat.
        out += event_basket(quotes, fee_fn, slippage, exhaustive=False)
    return sorted(out, key=lambda o: o.profit_per_set, reverse=True)


def scan_intra_polymarket(
    events: Iterable[dict], fee_fn: FeeFn = no_fee, slippage: float = 0.0
) -> list[Opportunity]:
    out: list[Opportunity] = []
    for ev in events:
        if not ev.get("negRisk"):
            continue
        quotes = [q for m in ev.get("markets", []) if (q := parse_polymarket_market(m))]
        # negRisk events can hold placeholder outcomes: keep the exhaustiveness caveat.
        out += event_basket(quotes, fee_fn, slippage, exhaustive=False)
    return sorted(out, key=lambda o: o.profit_per_set, reverse=True)


def scan_cross(
    poly: list[Quote],
    kalshi: list[Quote],
    threshold: float = 0.75,
    poly_fee: FeeFn = no_fee,
    kalshi_fee: FeeFn = kalshi_taker_fee,
    slippage: float = 0.0,
) -> list[tuple[Opportunity, float]]:
    """Returns (opportunity, title match score) sorted by locked profit."""
    out = []
    for p, k, score in match_markets(poly, kalshi, threshold):
        opp = cross_venue(p, k, poly_fee, kalshi_fee, slippage)
        if opp:
            out.append((opp, score))
    return sorted(out, key=lambda t: t[0].profit_per_set, reverse=True)
