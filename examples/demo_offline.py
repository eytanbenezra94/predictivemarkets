"""Offline demo on synthetic quotes: no network, no API. Run: python examples/demo_offline.py

Shows the four situations the scanners detect, with hand-checkable numbers.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pm_arb.arb import basket_buy, basket_sell, binary_buy, cross_venue  # noqa: E402
from pm_arb.fees import kalshi_taker_fee  # noqa: E402
from pm_arb.models import Leg, Quote  # noqa: E402


def show(title, opp):
    print(f"\n--- {title}")
    if opp is None:
        print("no arbitrage")
        return
    print(f"{opp.kind}: profit/set ${opp.profit_per_set:.4f}, ROI {opp.roi:.2%}")
    for leg in opp.legs:
        print(f"  {leg.side:8s} @ {leg.price:.2f} [{leg.venue}] {leg.label}")


# 1. Binary market with a gap: YES ask 0.45 + NO ask 0.50 = 0.95 -> $0.05 locked per $1 payout.
q = Quote("kalshi", "DEMO-1", "Will it rain tomorrow?", yes_ask=0.45, no_ask=0.50)
show("1. Binary YES+NO < 1 (no fees)", binary_buy(q))

# 2. Same quotes, but with a Kalshi-style fee 0.07 * p * (1 - p) per leg: the edge shrinks from $0.05 to about $0.015.
show("2. Same market, Kalshi fee model", binary_buy(q, fee_fn=kalshi_taker_fee))

# 3. Three-candidate election: asks 0.40 + 0.30 + 0.27 = 0.97 -> buy all, one pays $1.
legs = [Leg("polymarket", str(i), f"Candidate {c}", "BUY_YES", p) for i, (c, p) in enumerate(zip("ABC", (0.40, 0.30, 0.27)))]
show("3. Multi-outcome basket (buy-side, exhaustive)", basket_buy(legs))

# 4. Bids add up to more than 1: sell every outcome, at most one can pay out.
show(
    "4. Multi-outcome basket (sell-side)",
    basket_sell([("a", "Candidate A", 0.40), ("b", "Candidate B", 0.35), ("c", "Candidate C", 0.30)], venue="polymarket"),
)

# 5. Cross-venue: YES 0.40 on Polymarket + NO 0.55 on Kalshi = 0.95.
poly = Quote("polymarket", "P-1", "Fed cuts in December", yes_ask=0.40, no_ask=0.62)
kal = Quote("kalshi", "K-1", "Fed cuts in December", yes_ask=0.65, no_ask=0.55)
show("5. Cross-venue (no fees)", cross_venue(poly, kal))
show("6. Cross-venue with 0.5c slippage per leg and Kalshi fees", cross_venue(poly, kal, fee_b=kalshi_taker_fee, slippage=0.005))
