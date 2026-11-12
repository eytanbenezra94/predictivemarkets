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

from pm_arb import clients, depth, tracking  # noqa: E402
from pm_arb.scan import run_cycle  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=60, help="seconds between cycles")
    ap.add_argument("--cycles", type=int, default=0, help="stop after N cycles (0 = until Ctrl-C)")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--slippage", type=float, default=0.005)
    ap.add_argument("--horizon-days", type=float, default=90, help="Kalshi markets closing within N days (cross-venue)")
    ap.add_argument("--market-pages", type=int, default=2, help="pages of 1000 near-term Kalshi markets")
    ap.add_argument("--min-days", type=float, default=0, help="only Kalshi markets closing after N days")
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--out", default="data/opportunities.csv")
    ap.add_argument("--cycles-out", default="data/cycles.csv")
    ap.add_argument("--depth-out", default="data/depth.csv")
    ap.add_argument("--no-depth", action="store_true", help="skip the order-book depth check of flagged opportunities")
    a = ap.parse_args()

    n = 0
    try:
        while a.cycles == 0 or n < a.cycles:
            started = time.time()
            try:
                poly_events = list(clients.polymarket_events(a.pages))
                kal_events = list(clients.kalshi_events(a.pages))
                kal_markets = list(clients.kalshi_markets(a.market_pages, horizon_days=a.horizon_days, min_days=a.min_days))
                opps, n_poly, n_kal = run_cycle(poly_events, kal_markets, kal_events, a.slippage, a.threshold)
                ts = time.time()
                tracking.append_opportunities(a.out, tracking.to_rows(opps, ts))
                tracking.append_cycle(a.cycles_out, ts, n_poly, n_kal, len(opps))
                if opps and not a.no_depth:
                    for o, rep in depth.check_all(opps, depth.poly_tokens(poly_events), a.slippage):
                        tracking.append_depth(a.depth_out, ts, tracking.opp_key(o), rep)
                        bp = "n/a" if rep["book_profit"] is None else f"{rep['book_profit']:.4f}"
                        print(f"    depth: {o.kind} logged {o.profit_per_set:.4f} -> live-book {bp}, min size {rep['min_size']:g}, stale legs {rep['stale_legs']}/{rep['poly_legs']}", flush=True)
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
