"""Summarise a log written by scripts/log_arb.py: how many opportunities, how long they last.

Usage: python scripts/analyze_log.py --interval 60 [--top 10]
`--interval` must equal the sampling interval used when logging.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pm_arb import depth, tracking  # noqa: E402


def fmt(x, pct=False, unit=""):
    if x is None:
        return "n/a"
    return f"{x:.1%}" if pct else f"{x:g}{unit}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=60)
    ap.add_argument("--opps", default="data/opportunities.csv")
    ap.add_argument("--cycles", default="data/cycles.csv")
    ap.add_argument("--depth", default="data/depth.csv")
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    rows = tracking.read_csv(a.opps)
    cycles = tracking.read_csv(a.cycles)
    if not cycles:
        sys.exit("No cycles logged yet: run scripts/log_arb.py first.")
    eps = tracking.episodes(rows, a.interval)
    s = tracking.summarize(eps, a.interval, cycles)
    t0, t1 = int(cycles[0]["ts"]), int(cycles[-1]["ts"])
    print(f"Period: {time.strftime('%Y-%m-%d %H:%M', time.localtime(t0))} -> {time.strftime('%Y-%m-%d %H:%M', time.localtime(t1))}")
    print(f"Cycles: {s['cycles']}   cycles with at least one opportunity: {fmt(s['cycles_with_opportunity_share'], pct=True)}")
    print(f"Episodes: {s['episodes']}   seen only once: {fmt(s['single_observation_share'], pct=True)}")
    print(f"Duration (lower bound, seconds): median {fmt(s['median_duration_s'])}, mean {fmt(s['mean_duration_s'])}, max {fmt(s['max_duration_s'])}")
    print(f"Best profit per set seen: {fmt(s['max_profit'])}")
    for kind in sorted({e.kind for e in eps}):
        k = [e for e in eps if e.kind == kind]
        print(f"  {kind:12s} episodes={len(k):4d} median duration={sorted(e.duration for e in k)[len(k) // 2]}s")
    print(f"\nTop {a.top} episodes by profit per set:")
    for e in eps[: a.top]:
        print(f"  ${e.max_profit:.4f}  {e.duration:6d}s  x{e.observations:<3d} {e.description[:110]}")
    drows = tracking.read_csv(a.depth)
    if drows:
        print(f"\nOrder-book depth checks ({len(drows)} checks, Polymarket legs only; Kalshi legs are not checked):")
        for d in depth.summarize_depth(drows)[: a.top]:
            bp = "n/a (mixed venues)" if d["best_book_profit"] is None else f"{d['best_book_profit']:+.4f}"
            print(f"  {d['kind']:12s} checks={d['checks']:3d} median size={d['median_min_size']:g} best live-book profit={bp} stale share={d['stale_share']:.0%}\n      {d['detail'][:150]}")
    print("\nReading guide: an episode seen once lasted less than the sampling interval, so a human or a slow bot")
    print("could not have traded it. Profits above are from top-of-book quotes; the depth section re-prices them from the live order book.")


if __name__ == "__main__":
    main()
