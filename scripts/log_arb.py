"""Project 3 - Opportunity logger: sample both venues on a schedule and record every apparent arbitrage.

Usage:
    python scripts/log_arb.py --interval 60 --pages 2            # runs until Ctrl-C
    python scripts/log_arb.py --interval 60 --cycles 1440        # about one day
Then:
    python scripts/analyze_log.py --interval 60

Output (CSV, appended): data/opportunities.csv and data/cycles.csv.
Each cycle makes a handful of public read-only requests; keep --pages small and the interval
at 30 s or more to stay well within rate limits.
"""
import argparse
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pm_arb import clients, tracking  # noqa: E402
from pm_arb.scan import run_cycle  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=60, help="seconds between cycles")
    ap.add_argument("--cycles", type=int, default=0, help="stop after N cycles (0 = until Ctrl-C)")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--slippage", type=float, default=0.005)
    ap.add_argument("--threshold", type=float, default=0.75)
    ap.add_argument("--out", default="data/opportunities.csv")
    ap.add_argument("--cycles-out", default="data/cycles.csv")
    a = ap.parse_args()

    n = 0
    try:
        while a.cycles == 0 or n < a.cycles:
            started = time.time()
            try:
                poly_events = list(clients.polymarket_events(a.pages))
                kal_events = list(clients.kalshi_events(a.pages))
                kal_markets = clients.kalshi_quotes_from_events(kal_events)
                opps, n_poly, n_kal = run_cycle(poly_events, kal_markets, kal_events, a.slippage, a.threshold)
                ts = time.time()
                tracking.append_opportunities(a.out, tracking.to_rows(opps, ts))
                tracking.append_cycle(a.cycles_out, ts, n_poly, n_kal, len(opps))
                print(f"[{time.strftime('%H:%M:%S')}] polymarket={n_poly} kalshi={n_kal} opportunities={len(opps)}", flush=True)
                if n_poly == 0 or n_kal == 0:
                    print("WARNING: a venue returned zero usable quotes: the parser or the endpoint probably changed", file=sys.stderr, flush=True)
            except (requests.RequestException, ValueError) as e:  # network error or malformed JSON: skip the cycle
                print(f"[{time.strftime('%H:%M:%S')}] cycle skipped: {e}", file=sys.stderr, flush=True)
            n += 1
            time.sleep(max(0.0, a.interval - (time.time() - started)))
    except KeyboardInterrupt:
        print(f"\nStopped after {n} cycles. Analyse with: python scripts/analyze_log.py --interval {a.interval:g}")


if __name__ == "__main__":
    main()
