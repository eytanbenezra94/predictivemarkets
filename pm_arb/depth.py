"""Order-book depth check for Polymarket legs.

Top-of-book prices from Gamma (`bestBid` / `bestAsk`) say nothing about size, and can be stale.
For a flagged opportunity this module reads the CLOB book of each Polymarket leg and reports
the size available at the best price, the live price, and the profit recomputed from live books.

Kalshi legs are not checked (no verified size field): an opportunity that mixes venues gets
`book_profit = None` and a size for its Polymarket legs only.
"""
from __future__ import annotations

import statistics
from typing import Any, Callable, Iterable, Optional

import requests

from . import clients
from .models import Leg, Opportunity

CLOB = "https://clob.polymarket.com"
STALE_TOLERANCE = 0.01  # a live price this much worse than the logged one counts as stale


def poly_tokens(events: Iterable[dict]) -> dict[str, str]:
    """market id -> YES token id (Gamma `clobTokenIds` is a JSON string, same order as `outcomes`)."""
    out: dict[str, str] = {}
    for ev in events:
        for m in ev.get("markets", []):
            ids = clients._jlist(m.get("clobTokenIds"))
            outcomes = [str(o).lower() for o in clients._jlist(m.get("outcomes"))]
            if len(ids) == 2 and outcomes == ["yes", "no"]:
                out[str(m.get("id") or m.get("conditionId"))] = str(ids[0])
    return out


def parse_book(book: dict) -> dict:
    """Best bid / ask and the size at that level. Never relies on the order of the levels:
    the live API lists bids ascending and asks descending."""
    def best(levels: list, pick: Callable) -> tuple[Optional[float], float]:
        prices = [(clients._f(l.get("price")), clients._f(l.get("size")) or 0.0) for l in levels]
        prices = [(p, s) for p, s in prices if p is not None]
        if not prices:
            return None, 0.0
        p = pick(p for p, _ in prices)
        return p, sum(s for q, s in prices if q == p)

    bid, bid_size = best(book.get("bids") or [], max)
    ask, ask_size = best(book.get("asks") or [], min)
    return {"bid": bid, "bid_size": bid_size, "ask": ask, "ask_size": ask_size}


def fetch_book(token_id: str) -> dict:
    return parse_book(clients.get_json(f"{CLOB}/book", {"token_id": token_id}))


def _leg_view(leg: Leg, book: dict) -> tuple[Optional[float], float]:
    """(live price paid or received per contract, size at that price) for a Polymarket leg.
    NO is the mirror of the YES book, so buying NO means hitting the YES bid."""
    if leg.side == "BUY_YES":
        return book["ask"], book["ask_size"]
    if leg.side == "SELL_YES":
        return book["bid"], book["bid_size"]
    if leg.side == "BUY_NO":
        return (None if book["bid"] is None else 1.0 - book["bid"]), book["bid_size"]
    return None, 0.0


def _stale(leg: Leg, live: Optional[float]) -> bool:
    if live is None:
        return True
    worse = live - leg.price if leg.side in ("BUY_YES", "BUY_NO") else leg.price - live
    return worse > STALE_TOLERANCE


def check(opp: Opportunity, tokens: dict[str, str], books: dict[str, dict], slippage: float = 0.0) -> Optional[dict]:
    """Depth report for one opportunity, from already-fetched books (token id -> parse_book result).

    Returns None when no leg is a Polymarket leg with a known token.
    """
    views = []
    for leg in opp.legs:
        tok = tokens.get(leg.market_id) if leg.venue == "polymarket" else None
        book = books.get(tok) if tok else None
        views.append((leg, None if book is None else _leg_view(leg, book)))
    checked = [(l, v) for l, v in views if v is not None]
    if not checked:
        return None
    sizes = [v[1] for _, v in checked]
    stale = sum(1 for l, v in checked if _stale(l, v[0]))
    book_profit = None
    if len(checked) == len(opp.legs) and all(v[0] is not None for _, v in checked):
        if opp.kind == "basket_buy":
            book_profit = 1.0 - sum(v[0] + slippage + l.fee_fn(v[0]) for l, v in checked)
        elif opp.kind == "basket_sell":
            book_profit = sum(v[0] - slippage - l.fee_fn(v[0]) for l, v in checked) - 1.0
    detail = "; ".join(
        f"{l.side} logged {l.price:.3f} live {'-' if v[0] is None else format(v[0], '.3f')} size {v[1]:g}" for l, v in checked
    )
    return {
        "kind": opp.kind,
        "profit": opp.profit_per_set,
        "book_profit": book_profit,
        "min_size": min(sizes),
        "poly_legs": len(checked),
        "legs": len(opp.legs),
        "stale_legs": stale,
        "detail": detail,
    }


def check_all(
    opps: Iterable[Opportunity],
    tokens: dict[str, str],
    slippage: float = 0.0,
    fetch: Callable[[str], dict] = fetch_book,
    max_books: int = 30,
) -> list[tuple[Opportunity, dict]]:
    """Fetch the books needed by `opps` (at most `max_books` requests, failures skipped) and check each."""
    books: dict[str, dict] = {}
    out = []
    for o in opps:
        for leg in o.legs:
            tok = tokens.get(leg.market_id) if leg.venue == "polymarket" else None
            if tok and tok not in books and len(books) < max_books:
                try:
                    books[tok] = fetch(tok)
                except (requests.RequestException, ValueError):
                    pass
        rep = check(o, tokens, books, slippage)
        if rep:
            out.append((o, rep))
    return out


def summarize_depth(rows: list[dict]) -> list[dict]:
    """Per opportunity key: number of checks, median size, best live-book profit, share of stale checks."""
    by_key: dict[str, list[dict]] = {}
    for r in rows:
        by_key.setdefault(r["key"], []).append(r)
    out = []
    for key, rs in by_key.items():
        bp = [float(r["book_profit"]) for r in rs if r["book_profit"] not in ("", None)]
        out.append(
            {
                "key": key,
                "kind": rs[0]["kind"],
                "checks": len(rs),
                "median_min_size": statistics.median(float(r["min_size"]) for r in rs),
                "best_book_profit": max(bp) if bp else None,
                "stale_share": sum(1 for r in rs if int(r["stale_legs"]) > 0) / len(rs),
                "detail": rs[-1]["detail"],
            }
        )
    return sorted(out, key=lambda d: -(d["best_book_profit"] or -1))
