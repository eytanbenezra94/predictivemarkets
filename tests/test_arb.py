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


# ----------------------------------------------------------------------------- logger / tracking
from pm_arb import tracking  # noqa: E402
from pm_arb.scan import run_cycle  # noqa: E402


def _opp(profit=0.03, venue="k", mid="m1"):
    return binary_buy(q(venue, mid, "Will X?", yes_ask=0.5 - profit / 2, no_ask=0.5 - profit / 2))


def test_opp_key_is_stable_and_leg_based():
    assert tracking.opp_key(_opp(0.03)) == tracking.opp_key(_opp(0.05))  # same legs, different prices
    assert tracking.opp_key(_opp(mid="m1")) != tracking.opp_key(_opp(mid="m2"))


def test_episodes_split_on_gaps_and_measure_duration():
    key_rows = lambda ts, p=0.03: tracking.to_rows([_opp(p)], ts)  # noqa: E731
    rows = key_rows(0) + key_rows(60) + key_rows(120, 0.05) + key_rows(1000)  # 3 sightings, a gap, 1 sighting
    eps = tracking.episodes(rows, interval=60)
    assert len(eps) == 2
    long_ep = max(eps, key=lambda e: e.observations)
    assert long_ep.observations == 3 and long_ep.start == 0 and long_ep.end == 120
    assert long_ep.duration == 180  # 120 + one interval
    assert long_ep.max_profit == pytest.approx(0.05)
    short_ep = min(eps, key=lambda e: e.observations)
    assert short_ep.duration == 60 and short_ep.observations == 1


def test_summarize_with_cycles():
    rows = tracking.to_rows([_opp()], 0) + tracking.to_rows([_opp()], 60)
    cycles = [{"ts": 0, "n_opportunities": 1}, {"ts": 60, "n_opportunities": 1}, {"ts": 120, "n_opportunities": 0}]
    s = tracking.summarize(tracking.episodes(rows, 60), 60, cycles)
    assert s["episodes"] == 1 and s["cycles"] == 3
    assert s["cycles_with_opportunity_share"] == pytest.approx(2 / 3)
    assert tracking.summarize([], 60)["median_duration_s"] is None


def test_csv_roundtrip(tmp_path):
    path = str(tmp_path / "sub" / "opps.csv")
    tracking.append_opportunities(path, tracking.to_rows([_opp()], 100))
    tracking.append_opportunities(path, tracking.to_rows([_opp()], 160))  # header written once
    rows = tracking.read_csv(path)
    assert [r["ts"] for r in rows] == ["100", "160"]
    assert tracking.read_csv(str(tmp_path / "missing.csv")) == []


def test_run_cycle_end_to_end_on_synthetic_data():
    pm_event = {"negRisk": True, "markets": [_pm_mk(1, 0.38, 0.40), _pm_mk(2, 0.28, 0.30), _pm_mk(3, 0.25, 0.27)]}
    kal_a = parse_kalshi_market({"ticker": "K1", "title": "Fed cuts rates in December 2026", "status": "active",
                                 "yes_bid_dollars": "0.5900", "yes_ask_dollars": "0.6000", "no_bid_dollars": "0.4000", "no_ask_dollars": "0.4100"})
    pm_cross = {"id": "p1", "question": "Will the Fed cut rates in December 2026?", "outcomes": '["Yes","No"]',
                "bestBid": 0.20, "bestAsk": 0.30, "active": True, "closed": False, "acceptingOrders": True}
    opps, n_poly, n_kal = run_cycle([pm_event, {"markets": [pm_cross]}], [kal_a], [], slippage=0.0, threshold=0.6)
    assert n_poly == 4 and n_kal == 1
    kinds = sorted(o.kind for o in opps)
    assert "cross_venue" in kinds  # YES@poly 0.30 + NO@kalshi 0.41 = 0.71 -> large synthetic gap
    assert "basket_buy" in kinds   # the non-augmented negRisk basket (sum 0.97)


def test_kalshi_quotes_from_events_skips_combo_and_inactive_markets():
    from pm_arb.clients import kalshi_quotes_from_events

    events = [
        {"markets": [fixture("kalshi_event_market.json"), fixture("kalshi_mve_market.json"),
                     {**fixture("kalshi_event_market.json"), "ticker": "X", "status": "finalized"}]},
        {"markets": [{"ticker": "Y", "title": "Will Y?", "status": "active", "yes_ask_dollars": "0.4000", "no_ask_dollars": "0.6200"}]},
    ]
    assert [q.market_id for q in kalshi_quotes_from_events(events)] == ["KXNEXTNATOSECGEN-99-KIOH", "Y"]


# ----------------------------------------------------------------------------- matcher diagnostics
from pm_arb.diagnose import match_stats, raw_cross_sum  # noqa: E402


def test_raw_cross_sum_picks_cheapest_direction_or_none():
    p = q("polymarket", "p", "x", yes_ask=0.40, no_ask=0.62)
    k = q("kalshi", "k", "x", yes_ask=0.65, no_ask=0.55)
    assert raw_cross_sum(p, k) == (pytest.approx(0.95), "YES@polymarket + NO@kalshi")
    assert raw_cross_sum(q("polymarket", "p", "x"), q("kalshi", "k", "x")) is None


def test_match_stats_counts_pairs_per_threshold():
    poly = [q("polymarket", "p1", "Will the Fed cut rates in December 2026?"), q("polymarket", "p2", "Bitcoin above 100k on Dec 31")]
    kal = [q("kalshi", "k1", "Fed cuts rates in December 2026"), q("kalshi", "k2", "Totally unrelated question about tennis")]
    stats = match_stats(poly, kal, (0.5, 0.99))
    assert stats[0.5] == 1 and stats[0.99] == 0


# ----------------------------------------------------------------------------- near-term Kalshi markets
def test_kalshi_markets_sends_verified_filters_and_follows_cursor(monkeypatch):
    from pm_arb import clients as c

    calls = []
    pages = [
        {"markets": [fixture("kalshi_event_market.json"), fixture("kalshi_mve_market.json")], "cursor": "abc"},
        {"markets": [{"ticker": "Z", "title": "Will Z?", "status": "active", "yes_ask_dollars": "0.4000", "no_ask_dollars": "0.6200"}], "cursor": ""},
    ]

    def fake_get(url, params=None, retries=3):
        calls.append((url, dict(params)))
        return pages[len(calls) - 1]

    monkeypatch.setattr(c, "get_json", fake_get)
    out = list(c.kalshi_markets(max_pages=5, horizon_days=10, now=1_000_000, min_days=2))
    assert [x.market_id for x in out] == ["KXNEXTNATOSECGEN-99-KIOH", "Z"]  # combo market dropped
    assert calls[0][1]["mve_filter"] == "exclude" and calls[0][1]["max_close_ts"] == 1_000_000 + 10 * 86400
    assert calls[0][1]["min_close_ts"] == 1_000_000 + 2 * 86400
    assert calls[1][1]["cursor"] == "abc" and len(calls) == 2


def test_match_markets_date_window_can_be_disabled():
    a = [q("polymarket", "p", "Will Troy qualify for the Sun Belt Championship Game?", end_date="2026-12-01T00:00:00Z")]
    b = [q("kalshi", "k", "Will Troy qualify for the College Football Sun Belt Championship Game?", end_date="2027-01-10T00:00:00Z")]
    assert match_markets(a, b, 0.6) == []                       # 40 days apart, rejected by the 2-day window
    assert len(match_markets(a, b, 0.6, max_days=None)) == 1    # accepted when end dates are ignored


# --- matcher precision on real titles (from a live diagnostic run) ---
_SAME = [
    ("Will Mark Kelly win the 2028 Democratic presidential nomination?", "Will Mark Kelly be the Democratic Presidential nominee in 2028?"),
    ("Will J.B. Pritzker win the 2028 Democratic presidential nomination?", "Will J.B. Pritzker be the Democratic Presidential nominee in 2028?"),
]
_DIFFERENT = [
    ("Will Marco Rubio win the 2028 Republican presidential nomination?", "Will Marco Rubio and JD Vance be the 2028 Republican Presidential ticket?"),
    ("Will J.D. Vance win the 2028 Republican presidential nomination?", "Will J.D. Vance win the 2028 Ohio Republican primary?"),
    ("Will Ted Cruz win the 2028 Republican presidential nomination?", "Will Ted Cruz win the 2028 Iowa Republican caucus?"),
]


def test_similarity_separates_nominee_from_ticket_primary_caucus():
    assert min(similarity(a, b) for a, b in _SAME) >= 0.9
    assert max(similarity(a, b) for a, b in _DIFFERENT) < 0.75


def test_default_threshold_keeps_same_event_and_drops_others():
    def q(v, i, title):
        return Quote(v, i, title, 0.5, 0.5, 0.5, 0.5, "2028-11-07T00:00:00Z")
    left = [q("polymarket", f"p{i}", a) for i, (a, _) in enumerate(_SAME + _DIFFERENT)]
    right = [q("kalshi", f"k{i}", b) for i, (_, b) in enumerate(_SAME + _DIFFERENT)]
    pairs = match_markets(left, right)
    assert {(p.market_id, k.market_id) for p, k, _ in pairs} == {("p0", "k0"), ("p1", "k1")}


def test_annualized_yield():
    from datetime import datetime, timezone
    from pm_arb.diagnose import annualized_yield
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    y = annualized_yield(0.99, "2028-01-01T00:00:00Z", now)
    assert 0.005 < y < 0.006
    assert annualized_yield(0.99, "2025-01-01T00:00:00Z", now) is None
    assert annualized_yield(0.99, None, now) is None


# --- depth check ---
import json  # noqa: E402

from pm_arb import depth  # noqa: E402
from pm_arb.models import Opportunity  # noqa: E402


def _fixture(name):
    with open(os.path.join(os.path.dirname(__file__), "fixtures", name)) as f:
        return json.load(f)


def test_parse_book_ignores_level_order():
    b = depth.parse_book(_fixture("polymarket_book.json"))
    # real book: asks are listed descending, the best ask is the last element
    assert b["ask"] == 0.002 and b["ask_size"] == 157782.02
    assert b["bid"] == 0.001 and b["bid_size"] == 2295397.22


def test_parse_book_empty_side():
    b = depth.parse_book({"bids": [], "asks": [{"price": "0.5", "size": "10"}, {"price": "0.5", "size": "5"}]})
    assert b["bid"] is None and b["bid_size"] == 0.0
    assert b["ask"] == 0.5 and b["ask_size"] == 15.0


def test_poly_tokens_reads_json_string():
    ev = {"markets": [
        {"id": "7", "outcomes": '["Yes", "No"]', "clobTokenIds": '["111", "222"]'},
        {"id": "8", "outcomes": '["Over", "Under"]', "clobTokenIds": '["333", "444"]'},
    ]}
    assert depth.poly_tokens([ev]) == {"7": "111"}


def _sell_basket():
    bids = [("a", "A wins", 0.31), ("b", "Draw", 0.27), ("c", "C wins", 0.64)]
    from pm_arb.arb import basket_sell
    return basket_sell(bids, slippage=0.0, venue="polymarket")


def test_depth_confirms_thin_but_real_book():
    opp = _sell_basket()
    tokens = {"a": "ta", "b": "tb", "c": "tc"}
    books = {
        "ta": {"bid": 0.31, "bid_size": 12.0, "ask": 0.33, "ask_size": 5.0},
        "tb": {"bid": 0.27, "bid_size": 40.0, "ask": 0.29, "ask_size": 5.0},
        "tc": {"bid": 0.64, "bid_size": 3.0, "ask": 0.66, "ask_size": 5.0},
    }
    rep = depth.check(opp, tokens, books)
    assert rep["min_size"] == 3.0 and rep["stale_legs"] == 0
    assert rep["book_profit"] == pytest.approx(0.22)


def test_depth_flags_stale_quotes():
    opp = _sell_basket()
    tokens = {"a": "ta", "b": "tb", "c": "tc"}
    books = {  # the live book has moved: the logged bids no longer exist
        "ta": {"bid": 0.20, "bid_size": 12.0, "ask": 0.22, "ask_size": 5.0},
        "tb": {"bid": 0.25, "bid_size": 40.0, "ask": 0.27, "ask_size": 5.0},
        "tc": {"bid": None, "bid_size": 0.0, "ask": 0.60, "ask_size": 5.0},
    }
    rep = depth.check(opp, tokens, books)
    assert rep["stale_legs"] == 3 and rep["min_size"] == 0.0
    assert rep["book_profit"] is None  # one leg has no bid at all


def test_depth_skips_non_polymarket_and_mixed_profit():
    leg = Leg("kalshi", "k1", "K", "BUY_NO", 0.4)
    opp = Opportunity("cross_venue", "x", (leg, Leg("polymarket", "p1", "P", "BUY_YES", 0.5)), 0.05, 0.05)
    assert depth.check(opp, {}, {}) is None
    rep = depth.check(opp, {"p1": "tp"}, {"tp": {"bid": 0.48, "bid_size": 9.0, "ask": 0.5, "ask_size": 9.0}})
    assert rep["poly_legs"] == 1 and rep["legs"] == 2 and rep["book_profit"] is None


def test_check_all_survives_fetch_errors():
    import requests
    opp = _sell_basket()
    def boom(tok):
        raise requests.ConnectionError("down")
    assert depth.check_all([opp], {"a": "ta", "b": "tb", "c": "tc"}, fetch=boom) == []


def test_summarize_depth():
    rows = [
        {"key": "k", "kind": "basket_sell", "book_profit": "0.2", "min_size": "5", "stale_legs": "0", "detail": "d"},
        {"key": "k", "kind": "basket_sell", "book_profit": "", "min_size": "1", "stale_legs": "2", "detail": "d"},
    ]
    s = depth.summarize_depth(rows)[0]
    assert s["checks"] == 2 and s["best_book_profit"] == 0.2 and s["stale_share"] == 0.5


# --- network retries ---
def test_get_json_retries_connection_reset(monkeypatch):
    import requests
    from pm_arb import clients

    calls = {"n": 0}

    class Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"ok": True}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("Connection reset by peer")
        return Resp()

    monkeypatch.setattr(clients._session, "get", fake_get)
    monkeypatch.setattr(clients.time, "sleep", lambda s: None)
    assert clients.get_json("http://x") == {"ok": True}
    assert calls["n"] == 3


def test_get_json_raises_after_last_retry(monkeypatch):
    import requests
    from pm_arb import clients

    def always_timeout(url, params=None, timeout=None):
        raise requests.Timeout("read timed out")

    monkeypatch.setattr(clients._session, "get", always_timeout)
    monkeypatch.setattr(clients.time, "sleep", lambda s: None)
    with pytest.raises(requests.Timeout):
        clients.get_json("http://x")
