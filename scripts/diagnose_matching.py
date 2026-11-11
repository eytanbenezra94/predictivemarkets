"""Diagnose the cross-venue matcher on live data: how many pairs does it find, and are they the same event?

Usage: python scripts/diagnose_matching.py [--pages 2] [--top 20] [--out data/matches.csv]

Read the printed pairs by hand. A matcher that finds nothing makes "0 cross-venue opportunities"
meaningless; a matcher that finds wrong pairs makes any opportunity suspicious.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pm_arb import clients  # noqa: E402
from pm_arb.diagnose import match_stats, raw_cross_sum  # noqa: E402
from pm_arb.matching import match_markets  # noqa: E402


def fmt(x):
    return "  -  " if x is None else f"{x:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-score", type=float, default=0.6, help="lowest similarity kept in the CSV and the lists")
    ap.add_argument("--out", default="data/matches.csv")
    ap.add_argument("--horizon-days", type=float, default=90, help="Kalshi markets closing within N days")
    ap.add_argument("--max-days", type=float, default=2.0, help="max end-date difference for a pair")
    a = ap.parse_args()

    poly = list(clients.polymarket_markets(a.pages))
    kal = list(clients.kalshi_markets(a.pages, horizon_days=a.horizon_days))
    print(f"Polymarket binary quotes: {len(poly)} | Kalshi quotes: {len(kal)}")
    if not poly or not kal:
        sys.exit("A venue returned no quotes: check the parsers before reading anything else.")

    print(f"\nMatched pairs by similarity threshold (end dates within {a.max_days:g} days | end dates ignored):")
    with_dates = match_stats(poly, kal, max_days=a.max_days)
    no_dates = match_stats(poly, kal, max_days=None)
    for t in with_dates:
        print(f"  >= {t:.2f}: {with_dates[t]:5d} | {no_dates[t]:5d}")

    pairs = match_markets(poly, kal, a.min_score, max_days=a.max_days)
    rows = []
    for p, k, score in pairs:
        rc = raw_cross_sum(p, k)
        rows.append({
            "score": round(score, 3), "polymarket_title": p.title, "kalshi_title": k.title,
            "polymarket_end": p.end_date, "kalshi_end": k.end_date,
            "poly_yes_ask": p.yes_ask, "poly_no_ask": p.no_ask, "kalshi_yes_ask": k.yes_ask, "kalshi_no_ask": k.no_ask,
            "raw_cost": None if rc is None else round(rc[0], 4), "direction": None if rc is None else rc[1],
        })
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    if rows:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n{len(rows)} pairs with score >= {a.min_score} saved to {a.out}")

    priced = [r for r in rows if r["raw_cost"] is not None]
    print(f"Pairs with both asks available: {len(priced)} of {len(rows)}")

    print(f"\nTop {a.top} pairs by similarity (are these the SAME event?):")
    for r in sorted(rows, key=lambda r: -r["score"])[: a.top]:
        print(f"  {r['score']:.2f} | P: {r['polymarket_title'][:70]}\n       | K: {r['kalshi_title'][:70]}\n       | ends {str(r['polymarket_end'])[:10]} / {str(r['kalshi_end'])[:10]}  raw cost {fmt(r['raw_cost'])}")

    print(f"\nLowest raw cost among priced pairs (before fees; below 1.000 = a gap worth checking by hand):")
    for r in sorted(priced, key=lambda r: r["raw_cost"])[: a.top]:
        print(f"  cost {r['raw_cost']:.3f} score {r['score']:.2f} {r['direction']} | {r['polymarket_title'][:60]} || {r['kalshi_title'][:60]}")


if __name__ == "__main__":
    main()
