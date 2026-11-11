"""Project 2 - Cross-venue arbitrage: same event priced differently on Polymarket and Kalshi.

Usage: python scripts/scan_cross.py [--threshold 0.75] [--slippage 0.005] [--pages 5]
Always check resolution rules by hand before acting on a match.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pm_arb import clients  # noqa: E402
from pm_arb.scan import scan_cross  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.75, help="title similarity cutoff")
    ap.add_argument("--slippage", type=float, default=0.005)
    ap.add_argument("--min-profit", type=float, default=0.0)
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--horizon-days", type=float, default=90, help="Kalshi markets closing within N days")
    ap.add_argument("--min-days", type=float, default=0, help="only Kalshi markets closing after N days (target a later window)")
    a = ap.parse_args()

    poly = list(clients.polymarket_markets(a.pages))
    kal = list(clients.kalshi_markets(a.pages, horizon_days=a.horizon_days, min_days=a.min_days))
    print(f"Polymarket: {len(poly)} binary markets | Kalshi: {len(kal)} markets")

    results = [(o, s) for o, s in scan_cross(poly, kal, a.threshold, slippage=a.slippage) if o.profit_per_set >= a.min_profit]
    print(f"{len(results)} candidate arbitrages")
    for opp, score in results[:20]:
        print(f"\nprofit/set ${opp.profit_per_set:.4f}  ROI {opp.roi:6.2%}  match {score:.2f}  {opp.description}")
        for leg in opp.legs:
            print(f"    {leg.side:8s} {leg.price:.3f}  [{leg.venue}] {leg.label[:80]}")
        print(f"    ! {opp.caveat}")


if __name__ == "__main__":
    main()
