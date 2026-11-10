from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .fees import FeeFn, no_fee


@dataclass(frozen=True)
class Quote:
    """Top-of-book quotes of a binary market, all prices in dollars (0..1)."""

    venue: str
    market_id: str
    title: str
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    no_bid: Optional[float] = None
    no_ask: Optional[float] = None
    end_date: Optional[str] = None  # ISO 8601
    volume: Optional[float] = None


@dataclass(frozen=True)
class Leg:
    venue: str
    market_id: str
    label: str
    side: str  # "BUY_YES", "BUY_NO", "SELL_YES"
    price: float
    fee_fn: FeeFn = field(default=no_fee, repr=False, compare=False)


@dataclass(frozen=True)
class Opportunity:
    kind: str  # "basket_buy", "basket_sell", "cross_venue"
    description: str
    legs: tuple[Leg, ...]
    profit_per_set: float  # locked-in profit per $1 payout set, net of fees and slippage
    roi: float  # profit / capital at risk
    caveat: str = ""
