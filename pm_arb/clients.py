"""Read-only clients for the public Polymarket (Gamma) and Kalshi market-data endpoints.

Parsing is separated from HTTP so it can be unit-tested on saved payloads
(see tests/fixtures/, excerpts of real responses captured on 2026-11-10).
See docs/findings.md for what the live APIs actually return.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterator, Optional

import requests

from .models import Quote

GAMMA = "https://gamma-api.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"

_session = requests.Session()


def get_json(url: str, params: Optional[dict] = None, retries: int = 3) -> Any:
    for attempt in range(retries):
        resp = _session.get(url, params=params, timeout=20)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def _f(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _jlist(x: Any) -> list:
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        try:
            return json.loads(x)
        except json.JSONDecodeError:
            return []
    return []


# ----------------------------------------------------------------------------- Polymarket


def parse_polymarket_market(m: dict) -> Optional[Quote]:
    """Open binary Yes/No market -> Quote. The NO side is derived from the YES book (mirrored).

    Skipped: closed or inactive markets (about 11% of the markets nested in "active" events are
    closed), markets not accepting orders, and non Yes/No outcomes (Over/Under, team names).
    """
    if m.get("closed") or m.get("active") is False:
        return None
    if m.get("acceptingOrders") is False or m.get("enableOrderBook") is False:
        return None
    outcomes = [str(o).lower() for o in _jlist(m.get("outcomes"))]
    if outcomes != ["yes", "no"]:
        return None
    yes_bid, yes_ask = _f(m.get("bestBid")), _f(m.get("bestAsk"))
    yes_bid = yes_bid if yes_bid is not None and 0.0 < yes_bid < 1.0 else None
    yes_ask = yes_ask if yes_ask is not None and 0.0 < yes_ask < 1.0 else None
    schedule = m.get("feeSchedule") if m.get("feesEnabled") else None
    fee_schedule = None
    if isinstance(schedule, dict) and _f(schedule.get("rate")) is not None:
        fee_schedule = (float(schedule["rate"]), _f(schedule.get("exponent")) or 1.0)
    return Quote(
        venue="polymarket",
        market_id=str(m.get("id") or m.get("conditionId")),
        title=m.get("question") or "",
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=None if yes_ask is None else 1.0 - yes_ask,
        no_ask=None if yes_bid is None else 1.0 - yes_bid,
        end_date=m.get("endDate"),
        volume=_f(m.get("volumeNum") or m.get("volume")),
        fee_schedule=fee_schedule,
    )


def polymarket_events(max_pages: int = 10, page_size: int = 100) -> Iterator[dict]:
    """Events carry their markets. Sorted by 24h volume: the default order lists stale events first.

    `negRisk` events: exactly one outcome is meant to resolve YES. `negRiskAugmented` events can
    receive new outcomes later, so their listed outcomes are NOT exhaustive.
    """
    for page in range(max_pages):
        data = get_json(
            f"{GAMMA}/events",
            {
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
                "limit": page_size,
                "offset": page * page_size,
            },
        )
        if not data:
            return
        yield from data


def polymarket_markets(max_pages: int = 10, page_size: int = 100) -> Iterator[Quote]:
    """Open binary markets, flattened from the (volume sorted) events endpoint."""
    for ev in polymarket_events(max_pages, page_size):
        for m in ev.get("markets", []):
            q = parse_polymarket_market(m)
            if q:
                yield q


# ----------------------------------------------------------------------------- Kalshi


def _kalshi_px(m: dict, name: str) -> Optional[float]:
    """Kalshi quotes in dollars as strings (`yes_ask_dollars: "0.4600"`); cents fields are a fallback.

    "0.0000" means no bid and "1.0000" means no ask on the other side: both map to None.
    """
    v = _f(m.get(f"{name}_dollars"))
    if v is None:
        c = _f(m.get(name))
        v = None if c is None else c / 100.0
    return v if v is not None and 0.0 < v < 1.0 else None


def parse_kalshi_market(m: dict) -> Optional[Quote]:
    """Active, non-multivariate Kalshi market -> Quote.

    Multivariate (MVE) combo markets are skipped: they dominate the default listing and carry
    no quotes. The title is combined with `yes_sub_title` because event-level titles such as
    "GDP growth in 2036?" are shared by every market of the event.
    """
    if m.get("mve_collection_ticker"):
        return None
    if m.get("status") not in (None, "active"):
        return None
    title = m.get("title") or ""
    sub = m.get("yes_sub_title") or ""
    if sub and sub.lower() not in title.lower():
        title = f"{title} [{sub}]" if title else sub
    return Quote(
        venue="kalshi",
        market_id=m.get("ticker", ""),
        title=title,
        yes_bid=_kalshi_px(m, "yes_bid"),
        yes_ask=_kalshi_px(m, "yes_ask"),
        no_bid=_kalshi_px(m, "no_bid"),
        no_ask=_kalshi_px(m, "no_ask"),
        end_date=m.get("close_time") or m.get("expiration_time"),
        volume=_f(m.get("volume_fp") if m.get("volume_fp") is not None else m.get("volume")),
    )


def kalshi_events(max_pages: int = 10, page_size: int = 200) -> Iterator[dict]:
    cursor = None
    for _ in range(max_pages):
        params = {"status": "open", "with_nested_markets": "true", "limit": page_size}
        if cursor:
            params["cursor"] = cursor
        data = get_json(f"{KALSHI}/events", params)
        yield from data.get("events", [])
        cursor = data.get("cursor")
        if not cursor:
            return


def kalshi_quotes_from_events(events: list[dict]) -> list[Quote]:
    """Flatten the markets nested in events into quotes (active, non-multivariate only)."""
    return [q for ev in events for m in ev.get("markets", []) if (q := parse_kalshi_market(m))]


def kalshi_markets(
    max_pages: int = 2,
    page_size: int = 1000,
    horizon_days: float = 90,
    now: Optional[float] = None,
    min_days: float = 0,
) -> Iterator[Quote]:
    """Kalshi markets closing between `min_days` and `horizon_days` from now, for the cross-venue scan.

    Two filters were verified on live data (2026-11-11): `mve_filter=exclude` removes the
    multivariate combos that flood the default listing, and `max_close_ts` keeps markets closing
    within `horizon_days` and `min_close_ts` (also verified) lets you target a later window, for
    example `min_days=700, horizon_days=760` for the 2028 US election markets. Without the horizon, the default order is dominated by markets
    closing in 2031 or later, which cannot overlap with Polymarket's most traded (near-term)
    events: a first diagnostic then found 0 matched pairs at any threshold.
    """
    now = int(now if now is not None else time.time())
    cursor = None
    for _ in range(max_pages):
        params = {
            "status": "open",
            "limit": page_size,
            "mve_filter": "exclude",
            "max_close_ts": now + int(horizon_days * 86400),
        }
        if min_days > 0:
            params["min_close_ts"] = now + int(min_days * 86400)
        if cursor:
            params["cursor"] = cursor
        data = get_json(f"{KALSHI}/markets", params)
        for m in data.get("markets", []):
            q = parse_kalshi_market(m)
            if q:
                yield q
        cursor = data.get("cursor")
        if not cursor:
            return
