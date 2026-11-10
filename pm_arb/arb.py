"""Pure arbitrage logic (no network). Prices in dollars, every contract settles at $1 or $0."""
from __future__ import annotations

from typing import Optional, Sequence

from .fees import FeeFn, no_fee
from .models import Leg, Opportunity, Quote


def _cost(leg: Leg, slippage: float) -> float:
    """All-in cost of buying one contract on a leg."""
    return leg.price + slippage + leg.fee_fn(leg.price)


def _valid_ask(p: Optional[float]) -> bool:
    return p is not None and 0.0 < p < 1.0


def basket_buy(
    legs: Sequence[Leg], slippage: float = 0.0, exhaustive: bool = True
) -> Optional[Opportunity]:
    """Buy one YES on every outcome of a mutually exclusive AND exhaustive set.

    Exactly one leg pays $1, so the payout is $1 for sure. Profit = 1 - sum(all-in costs).
    A binary market is the special case [YES ask, NO ask].
    """
    if len(legs) < 2:
        return None
    cost = sum(_cost(leg, slippage) for leg in legs)
    profit = 1.0 - cost
    if profit <= 0:
        return None
    caveat = "" if exhaustive else "Outcomes may not be exhaustive: verify before trading."
    return Opportunity("basket_buy", f"Buy all {len(legs)} outcomes", tuple(legs), profit, profit / cost, caveat)


def basket_sell(
    bids: Sequence[tuple[str, str, float]],
    fee_fn: FeeFn = no_fee,
    slippage: float = 0.0,
    venue: str = "",
) -> Optional[Opportunity]:
    """Sell one YES on every outcome of a mutually exclusive set (exhaustiveness not required).

    At most one leg pays $1, so the liability is at most $1 per set.
    Profit (worst case) = proceeds - 1, where proceeds = sum(bid - slippage - fee).

    Selling YES at bid b is economically buying NO at 1 - b, so the capital locked is
    sum(1 - b_i + slippage + fee_i) = N - proceeds. ROI is reported against that capital
    (venues that net collateral across a basket may require less).
    """
    if len(bids) < 2:
        return None
    legs = tuple(Leg(venue, mid, label, "SELL_YES", p, fee_fn) for mid, label, p in bids)
    proceeds = sum(leg.price - slippage - leg.fee_fn(leg.price) for leg in legs)
    profit = proceeds - 1.0
    if profit <= 0:
        return None
    capital = len(legs) - proceeds
    return Opportunity("basket_sell", f"Sell all {len(legs)} outcomes", legs, profit, profit / capital)


def binary_buy(q: Quote, fee_fn: FeeFn = no_fee, slippage: float = 0.0) -> Optional[Opportunity]:
    """Buy YES and NO on the same binary market when the two asks sum to less than $1."""
    if not (_valid_ask(q.yes_ask) and _valid_ask(q.no_ask)):
        return None
    legs = (
        Leg(q.venue, q.market_id, q.title, "BUY_YES", q.yes_ask, fee_fn),
        Leg(q.venue, q.market_id, q.title, "BUY_NO", q.no_ask, fee_fn),
    )
    return basket_buy(legs, slippage)


def cross_venue(
    a: Quote, b: Quote, fee_a: FeeFn = no_fee, fee_b: FeeFn = no_fee, slippage: float = 0.0
) -> Optional[Opportunity]:
    """Same event on two venues: buy YES on one and NO on the other, in the best direction.

    Locked profit only if both markets resolve identically: check the resolution rules by hand.
    """
    best: Optional[Opportunity] = None
    for yes_q, yes_fee, no_q, no_fee_fn in ((a, fee_a, b, fee_b), (b, fee_b, a, fee_a)):
        if not (_valid_ask(yes_q.yes_ask) and _valid_ask(no_q.no_ask)):
            continue
        legs = (
            Leg(yes_q.venue, yes_q.market_id, yes_q.title, "BUY_YES", yes_q.yes_ask, yes_fee),
            Leg(no_q.venue, no_q.market_id, no_q.title, "BUY_NO", no_q.no_ask, no_fee_fn),
        )
        opp = basket_buy(legs, slippage)
        if opp is None:
            continue
        opp = Opportunity(
            "cross_venue",
            f"YES@{yes_q.venue} + NO@{no_q.venue}",
            opp.legs,
            opp.profit_per_set,
            opp.roi,
            "Verify both markets share the same resolution rules and end date.",
        )
        if best is None or opp.profit_per_set > best.profit_per_set:
            best = opp
    return best
