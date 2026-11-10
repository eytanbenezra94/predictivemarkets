"""Project 1 - Intra-market arbitrage: outcome prices that do not add up to $1.

Usage: python scripts/scan_intra.py [--slippage 0.005] [--min-profit 0.002] [--pages 5]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pm_arb import clients  # noqa: E402
from pm_arb.scan import scan_intra_kalshi, scan_intra_polymarket  # noqa: E402


def show(title, opps, min_profit):
    opps = [o for o in opps if o.profit_per_set >= min_profit]
    print(f"\n== {title}: {len(opps)} opportunities ==")
    for o in opps[:20]:
        print(f"{o.kind:12s} profit/set ${o.profit_per_set:.4f}  ROI {o.roi:6.2%}  {o.description}")
        for leg in o.legs[:4]:
            print(f"    {leg.side:8s} {leg.price:.3f}  {leg.label[:70]}")
        if len(o.legs) > 4:
            print(f"    ... {len(o.legs) - 4} more legs")
        if o.caveat:
            print(f"    ! {o.caveat}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slippage", type=float, default=0.005, help="extra $ per contract per leg")
    ap.add_argument("--min-profit", type=float, default=0.002)
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument(
        "--include-unverified-buys", action="store_true",
        help="also report buy-all baskets whose outcomes may not be exhaustive (mostly false positives)",
    )
    a = ap.parse_args()

    kal = scan_intra_kalshi(
        clients.kalshi_markets(a.pages), clients.kalshi_events(a.pages),
        slippage=a.slippage, include_unverified_buys=a.include_unverified_buys,
    )
    show("Kalshi", kal, a.min_profit)
    poly = scan_intra_polymarket(
        clients.polymarket_events(a.pages), slippage=a.slippage,
        include_unverified_buys=a.include_unverified_buys,
    )
    show("Polymarket (negRisk events)", poly, a.min_profit)


if __name__ == "__main__":
    main()
