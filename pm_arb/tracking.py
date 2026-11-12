"""Opportunity logging and duration analysis.

The question this answers: when an apparent arbitrage shows up, how long does it last?
An opportunity is identified by its legs (venue, market, side), so the same gap seen in
consecutive snapshots forms one *episode*.
"""
from __future__ import annotations

import csv
import hashlib
import os
import statistics
from dataclasses import dataclass
from typing import Iterable, Optional

from .models import Opportunity

OPP_FIELDS = ["ts", "key", "kind", "profit", "roi", "n_legs", "description", "caveat"]
CYCLE_FIELDS = ["ts", "n_polymarket", "n_kalshi", "n_opportunities"]
DEPTH_FIELDS = ["ts", "key", "kind", "profit", "book_profit", "min_size", "poly_legs", "legs", "stale_legs", "detail"]


def opp_key(opp: Opportunity) -> str:
    raw = "|".join(sorted(f"{l.venue}:{l.market_id}:{l.side}" for l in opp.legs))
    return f"{opp.kind}:{hashlib.sha1(raw.encode()).hexdigest()[:12]}"


def to_rows(opps: Iterable[Opportunity], ts: float) -> list[dict]:
    return [
        {
            "ts": int(ts),
            "key": opp_key(o),
            "kind": o.kind,
            "profit": round(o.profit_per_set, 6),
            "roi": round(o.roi, 6),
            "n_legs": len(o.legs),
            "description": o.description + " | " + "; ".join(f"{l.side}@{l.price:.3f} {l.label[:60]}" for l in o.legs),
            "caveat": o.caveat,
        }
        for o in opps
    ]


def _append(path: str, fields: list[str], rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)


def append_opportunities(path: str, rows: list[dict]) -> None:
    _append(path, OPP_FIELDS, rows)


def append_depth(path: str, ts: float, key: str, report: dict) -> None:
    row = {"ts": int(ts), "key": key, **{k: report[k] for k in DEPTH_FIELDS if k in report}}
    for k in ("profit", "book_profit"):
        row[k] = "" if row.get(k) is None else round(row[k], 6)
    _append(path, DEPTH_FIELDS, [row])


def append_cycle(path: str, ts: float, n_poly: int, n_kalshi: int, n_opps: int) -> None:
    _append(path, CYCLE_FIELDS, [{"ts": int(ts), "n_polymarket": n_poly, "n_kalshi": n_kalshi, "n_opportunities": n_opps}])


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


@dataclass(frozen=True)
class Episode:
    key: str
    kind: str
    start: int
    end: int
    duration: int  # seconds, end - start + one sampling interval (lower bound on the real duration)
    observations: int
    max_profit: float
    description: str


def episodes(rows: list[dict], interval: float, gap_factor: float = 2.5) -> list[Episode]:
    """Group snapshots of the same opportunity into episodes.

    Two sightings belong to one episode if they are at most `gap_factor * interval` apart.
    One sighting lasts at least one interval, so a single observation has duration = interval.
    """
    by_key: dict[str, list[dict]] = {}
    for r in rows:
        by_key.setdefault(r["key"], []).append(r)
    out: list[Episode] = []
    for key, rs in by_key.items():
        rs = sorted(rs, key=lambda r: int(r["ts"]))
        start = prev = int(rs[0]["ts"])
        group = [rs[0]]

        def close(group, start, end):
            out.append(
                Episode(
                    key, group[0]["kind"], start, end, int(end - start + interval), len(group),
                    max(float(g["profit"]) for g in group), group[0]["description"],
                )
            )

        for r in rs[1:]:
            t = int(r["ts"])
            if t - prev > gap_factor * interval:
                close(group, start, prev)
                start, group = t, []
            group.append(r)
            prev = t
        close(group, start, prev)
    return sorted(out, key=lambda e: e.max_profit, reverse=True)


def summarize(eps: list[Episode], interval: float, cycles: Optional[list[dict]] = None) -> dict:
    d = [e.duration for e in eps]
    res = {
        "episodes": len(eps),
        "single_observation_share": (sum(1 for e in eps if e.observations == 1) / len(eps)) if eps else None,
        "median_duration_s": statistics.median(d) if d else None,
        "mean_duration_s": statistics.mean(d) if d else None,
        "max_duration_s": max(d) if d else None,
        "max_profit": max((e.max_profit for e in eps), default=None),
    }
    if cycles:
        busy = sum(1 for c in cycles if int(c["n_opportunities"]) > 0)
        res["cycles"] = len(cycles)
        res["cycles_with_opportunity_share"] = busy / len(cycles)
    return res
