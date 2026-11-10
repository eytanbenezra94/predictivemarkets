"""Fee models. A fee function maps a contract price p in (0, 1) to a fee per contract in dollars.

Fee schedules change: treat the defaults as assumptions and check each venue's current schedule.
"""
from __future__ import annotations

from typing import Callable

FeeFn = Callable[[float], float]


def no_fee(p: float) -> float:
    return 0.0


def kalshi_taker_fee(p: float, rate: float = 0.07) -> float:
    """Kalshi-style taker fee: rate * p * (1 - p) per contract (rounding up to the cent ignored)."""
    return rate * p * (1.0 - p)


def schedule_fee(rate: float, exponent: float = 1.0) -> FeeFn:
    """Taker fee from a Polymarket-style `feeSchedule`: rate * (p * (1 - p)) ** exponent per contract.

    ASSUMPTION: published formulas differ between sources (some include an extra factor p).
    This form matches the documented peak of $1.25 per 100 contracts at 50c for rate 0.05.
    Verify with `GET https://clob.polymarket.com/fee-rate?token_id=...` before relying on it.
    """
    return lambda p: rate * (p * (1.0 - p)) ** exponent


def flat_fee(rate: float) -> FeeFn:
    """Fee proportional to the notional: rate * p."""
    return lambda p: rate * p
