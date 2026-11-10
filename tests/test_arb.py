import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pm_arb.arb import basket_buy, basket_sell, binary_buy, cross_venue  # noqa: E402
from pm_arb.clients import parse_kalshi_market, parse_polymarket_market  # noqa: E402
from pm_arb.fees import kalshi_taker_fee  # noqa: E402
from pm_arb.matching import match_markets, similarity  # noqa: E402
from pm_arb.models import Leg, Quote  # noqa: E402
from pm_arb.scan import scan_cross, scan_intra_kalshi, scan_intra_polymarket  # noqa: E402


def q(venue="k", mid="m", title="t", **kw):
    return Quote(venue, mid, title, **kw)


def test_binary_buy_locks_profit():
    opp = binary_buy(q(yes_ask=0.45, no_ask=0.50))
    assert opp.profit_per_set == pytest.approx(0.05)
    assert opp.roi == pytest.approx(0.05 / 0.95)


def test_binary_buy_none_when_asks_sum_over_one():
    assert binary_buy(q(yes_ask=0.52, no_ask=0.50)) is None


def test_slippage_and_fees_remove_edge():
    quote = q(yes_ask=0.48, no_ask=0.50)  # raw edge 0.02
    assert binary_buy(quote) is not None
    assert binary_buy(quote, slippage=0.01) is None  # 0.02 edge - 0.02 slippage = 0
    assert binary_buy(quote, fee_fn=kalshi_taker_fee) is None  # ~0.0175 per leg


def test_basket_buy_three_outcomes():
    legs = [Leg("k", str(i), "o", "BUY_YES", p) for i, p in enumerate([0.30, 0.30, 0.35])]
    assert basket_buy(legs).profit_per_set == pytest.approx(0.05)


def test_basket_buy_caveat_when_not_exhaustive():
    legs = [Leg("k", str(i), "o", "BUY_YES", p) for i, p in enumerate([0.30, 0.30, 0.35])]
    assert "exhaustive" in basket_buy(legs, exhaustive=False).caveat


def test_basket_sell():
    opp = basket_sell([("a", "A", 0.40), ("b", "B", 0.35), ("c", "C", 0.30)])
    assert opp.profit_per_set == pytest.approx(0.05)
    # capital locked = N - proceeds = 3 - 1.05 (selling YES at b == buying NO at 1 - b)
    assert opp.roi == pytest.approx(0.05 / 1.95)
    assert basket_sell([("a", "A", 0.40), ("b", "B", 0.30)]) is None


def test_cross_venue_picks_best_direction():
    a = q("poly", "a", "x", yes_ask=0.40, no_ask=0.62)
    b = q("kalshi", "b", "x", yes_ask=0.65, no_ask=0.55)
    opp = cross_venue(a, b)  # YES@poly 0.40 + NO@kalshi 0.55 = 0.95
    assert opp.profit_per_set == pytest.approx(0.05)
    assert [l.side for l in opp.legs] == ["BUY_YES", "BUY_NO"]
    assert opp.legs[0].venue == "poly" and opp.legs[1].venue == "kalshi"


def test_cross_venue_none_when_efficient():
    a = q("poly", "a", "x", yes_ask=0.52, no_ask=0.49)
    b = q("kalshi", "b", "x", yes_ask=0.51, no_ask=0.50)
    assert cross_venue(a, b) is None


def test_parse_kalshi_cents_and_dollars():
    m = {"ticker": "T", "title": "Will X?", "yes_bid": 44, "yes_ask": 46, "no_bid": 54, "no_ask": 56}
    p = parse_kalshi_market(m)
    assert (p.yes_bid, p.yes_ask, p.no_ask) == (0.44, 0.46, 0.56)
    d = parse_kalshi_market({"ticker": "T", "yes_ask_dollars": "0.4650", "no_ask": 0})
    assert d.yes_ask == pytest.approx(0.465) and d.no_ask is None


def test_parse_polymarket_binary_only():
    m = {"id": "1", "question": "Q?", "outcomes": '["Yes","No"]', "bestBid": 0.40, "bestAsk": 0.42}
    p = parse_polymarket_market(m)
    assert p.no_ask == pytest.approx(0.60) and p.no_bid == pytest.approx(0.58)
    assert parse_polymarket_market({**m, "outcomes": '["Trump","Biden"]'}) is None
    assert parse_polymarket_market({**m, "closed": True}) is None


def test_polymarket_binary_mirrored_never_arbs():
    p = parse_polymarket_market(
        {"id": "1", "question": "Q?", "outcomes": '["Yes","No"]', "bestBid": 0.40, "bestAsk": 0.42}
    )
    assert binary_buy(p) is None  # yes_ask + no_ask = 1 + spread


def test_scan_polymarket_negrisk_event():
    mk = lambda i, bid, ask: {  # noqa: E731
        "id": str(i), "question": f"Cand {i}", "outcomes": '["Yes","No"]', "bestBid": bid, "bestAsk": ask,
    }
    event = {"negRisk": True, "markets": [mk(1, 0.38, 0.40), mk(2, 0.28, 0.30), mk(3, 0.25, 0.27)]}
    opps = scan_intra_polymarket([event])
    assert len(opps) == 1 and opps[0].kind == "basket_buy"
    assert opps[0].profit_per_set == pytest.approx(0.03)
    assert scan_intra_polymarket([{**event, "negRisk": False}]) == []


def test_scan_kalshi_exclusive_event_sell_side():
    mk = lambda t, bid, ask: {"ticker": t, "title": t, "yes_bid": bid, "yes_ask": ask, "no_bid": 100 - ask, "no_ask": 100 - bid}  # noqa: E731
    event = {"mutually_exclusive": True, "markets": [mk("A", 40, 42), mk("B", 35, 37), mk("C", 30, 32)]}
    opps = scan_intra_kalshi([], [event], fee_fn=lambda p: 0.0)
    assert [o.kind for o in opps] == ["basket_sell"]
    assert opps[0].profit_per_set == pytest.approx(0.05)


def test_matching_and_cross_scan():
    poly = [q("polymarket", "p1", "Will the Fed cut rates in December 2026?", yes_ask=0.40, end_date="2026-12-10T00:00:00Z")]
    kal = [
        q("kalshi", "k1", "Fed cuts rates in December 2026", yes_ask=0.60, no_ask=0.55, end_date="2026-12-10T12:00:00Z"),
        q("kalshi", "k2", "Bitcoin above 100k on Dec 31", yes_ask=0.5, no_ask=0.5),
    ]
    assert similarity(poly[0].title, kal[0].title) > similarity(poly[0].title, kal[1].title)
    matches = match_markets(poly, kal, 0.6)
    assert len(matches) == 1 and matches[0][1].market_id == "k1"
    res = scan_cross(poly, kal, 0.6, kalshi_fee=lambda p: 0.0)
    assert res and res[0][0].profit_per_set == pytest.approx(0.05)


def test_matching_rejects_far_dates():
    a = [q("polymarket", "p", "Fed cuts rates in December", end_date="2026-12-10T00:00:00Z")]
    b = [q("kalshi", "k", "Fed cuts rates in December", end_date="2027-12-10T00:00:00Z")]
    assert match_markets(a, b, 0.6) == []


# ----------------------------------------------------------------------------- real-data regressions
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from pm_arb.fees import schedule_fee  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIX / name).read_text())


def test_real_polymarket_closed_market_in_active_event_is_skipped():
    assert parse_polymarket_market(fixture("polymarket_closed_market.json")) is None


def test_real_polymarket_fee_schedule_is_parsed():
    q = parse_polymarket_market(fixture("polymarket_fee_market.json"))
    assert q.fee_schedule == (0.05, 1.0)
    # documented peak: $1.25 per 100 contracts at 50c for rate 0.05
    assert schedule_fee(0.05, 1.0)(0.5) == pytest.approx(0.0125)


def test_missing_best_bid_is_none_not_crash():
    m = {**fixture("polymarket_fee_market.json")}
    m.pop("bestBid")
    q = parse_polymarket_market(m)
    assert q.yes_bid is None and q.no_ask is None and q.yes_ask == pytest.approx(0.05)


def test_real_kalshi_multivariate_market_is_skipped():
    assert parse_kalshi_market(fixture("kalshi_mve_market.json")) is None


def test_real_kalshi_market_title_volume_and_mirror():
    q = parse_kalshi_market(fixture("kalshi_event_market.json"))
    assert q.title == "Will Klaus Iohannis be the next Secretary General of NATO?"  # sub-title already inside
    assert q.volume == pytest.approx(383.36)
    assert (q.yes_bid, q.yes_ask, q.no_ask) == (0.02, 0.04, 0.98)
    # live finding: no_ask == 1 - yes_bid, so YES ask + NO ask = 1 + spread, never below 1
    assert q.yes_ask + q.no_ask == pytest.approx(1.02)
    assert binary_buy(q) is None


def test_kalshi_zero_and_one_dollar_quotes_mean_no_quote():
    q = parse_kalshi_market({"ticker": "T", "yes_ask_dollars": "0.0000", "no_ask_dollars": "1.0000"})
    assert q.yes_ask is None and q.no_ask is None


def _kalshi_mk(t, bid, ask):
    return {"ticker": t, "title": t, "yes_bid_dollars": f"{bid:.4f}", "yes_ask_dollars": f"{ask:.4f}"}


def test_kalshi_exclusive_but_not_exhaustive_event_is_not_reported_by_default():
    # shaped like the live "next Pope" event: asks sum to 0.31, which is NOT an arbitrage
    ev = {"mutually_exclusive": True, "markets": [_kalshi_mk("A", 0.10, 0.12), _kalshi_mk("B", 0.08, 0.10), _kalshi_mk("C", 0.08, 0.09)]}
    assert scan_intra_kalshi([], [ev], fee_fn=lambda p: 0.0) == []
    flagged = scan_intra_kalshi([], [ev], fee_fn=lambda p: 0.0, include_unverified_buys=True)
    assert flagged and "exhaustive" in flagged[0].caveat


def _pm_mk(i, bid, ask):
    return {"id": str(i), "question": f"Cand {i}", "outcomes": '["Yes","No"]', "bestBid": bid, "bestAsk": ask,
            "active": True, "closed": False, "acceptingOrders": True}


def test_polymarket_augmented_negrisk_buy_side_is_skipped_by_default():
    # shaped like the live "Prime Minister of Israel" event: open asks sum to 0.968
    ev = {"negRisk": True, "negRiskAugmented": True, "markets": [_pm_mk(1, 0.38, 0.40), _pm_mk(2, 0.28, 0.30), _pm_mk(3, 0.25, 0.27)]}
    assert scan_intra_polymarket([ev]) == []
    assert len(scan_intra_polymarket([ev], include_unverified_buys=True)) == 1


def test_polymarket_fees_use_each_markets_schedule():
    fee = {"feesEnabled": True, "feeSchedule": {"rate": 0.05, "exponent": 1}}
    ev = {"negRisk": True, "markets": [{**_pm_mk(i, a - 0.02, a), **fee} for i, a in enumerate([0.40, 0.30, 0.27])]}
    # raw edge 0.03, fees ~ 0.05 * p * (1 - p) per leg ~ 0.0120 + 0.0105 + 0.0099 -> no profit left
    assert scan_intra_polymarket([ev]) == []


def test_closed_markets_are_excluded_from_event_baskets():
    ev = {"negRisk": True, "markets": [_pm_mk(1, 0.38, 0.40), _pm_mk(2, 0.28, 0.30), _pm_mk(3, 0.25, 0.27),
                                       {**_pm_mk(4, 0.0, 0.002), "closed": True, "acceptingOrders": False}]}
    opps = scan_intra_polymarket([ev])
    assert len(opps) == 1 and len(opps[0].legs) == 3


def test_kalshi_event_level_title_gets_the_outcome_appended():
    # real shape: every market of the event shares the title "GDP growth in 2036?"
    q = parse_kalshi_market({"ticker": "KXGDPYEAR-36-B0.3", "title": "GDP growth in 2036?", "yes_sub_title": "0.1% to 0.5%",
                             "status": "active", "yes_bid_dollars": "0.0100", "yes_ask_dollars": "0.0300"})
    assert q.title == "GDP growth in 2036? [0.1% to 0.5%]"
