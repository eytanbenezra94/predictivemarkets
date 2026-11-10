"""Read-only clients for the public Polymarket (Gamma) and Kalshi market-data endpoints.

Parsing is separated from HTTP so it can be unit-tested on saved payloads.
Endpoint paths and field names follow each venue's public docs at the time of writing:
check them if a call fails, schemas evolve.
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
    """Binary Yes/No market -> Quote. The NO side is derived from the YES book (mirrored)."""
    if m.get("closed") or m.get("active") is False:
        return None
    outcomes = [str(o).lower() for o in _jlist(m.get("outcomes"))]
    if outcomes != ["yes", "no"]:
        return None
    yes_bid, yes_ask = _f(m.get("bestBid")), _f(m.get("bestAsk"))
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
    )


def polymarket_markets(max_pages: int = 10, page_size: int = 100) -> Iterator[Quote]:
    for page in range(max_pages):
        data = get_json(
            f"{GAMMA}/markets",
            {"active": "true", "closed": "false", "limit": page_size, "offset": page * page_size},
        )
        if not data:
            return
        for m in data:
            q = parse_polymarket_market(m)
            if q:
                yield q


def polymarket_events(max_pages: int = 10, page_size: int = 100) -> Iterator[dict]:
    """Events carry their markets. `negRisk` events: exactly one outcome resolves YES."""
    for page in range(max_pages):
        data = get_json(
            f"{GAMMA}/events",
            {"active": "true", "closed": "false", "limit": page_size, "offset": page * page_size},
        )
        if not data:
            return
        yield from data


# ----------------------------------------------------------------------------- Kalshi


def _kalshi_px(m: dict, name: str) -> Optional[float]:
    """Kalshi quotes either in cents (`yes_ask`) or dollars (`yes_ask_dollars`)."""
    v = _f(m.get(f"{name}_dollars"))
    if v is None:
        c = _f(m.get(name))
        v = None if c is None else c / 100.0
    return v if v is not None and 0.0 < v < 1.0 else None


def parse_kalshi_market(m: dict) -> Quote:
    return Quote(
        venue="kalshi",
        market_id=m.get("ticker", ""),
        title=m.get("title") or m.get("yes_sub_title") or "",
        yes_bid=_kalshi_px(m, "yes_bid"),
        yes_ask=_kalshi_px(m, "yes_ask"),
        no_bid=_kalshi_px(m, "no_bid"),
        no_ask=_kalshi_px(m, "no_ask"),
        end_date=m.get("close_time") or m.get("expiration_time"),
        volume=_f(m.get("volume")),
    )


def kalshi_markets(max_pages: int = 10, page_size: int = 1000) -> Iterator[Quote]:
    cursor = None
    for _ in range(max_pages):
        params = {"status": "open", "limit": page_size}
        if cursor:
            params["cursor"] = cursor
        data = get_json(f"{KALSHI}/markets", params)
        for m in data.get("markets", []):
            yield parse_kalshi_market(m)
        cursor = data.get("cursor")
        if not cursor:
            return


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
