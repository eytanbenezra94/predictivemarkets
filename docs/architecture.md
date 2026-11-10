# Architecture

```
            +-----------------+          +--------------------+
HTTP  --->  |  clients.py     |  Quote   |  scan.py           |  Opportunity
(Polymarket |  fetch + parse  | -------> |  scanners          | ------------> scripts/*.py (CLI output)
 Gamma,     +-----------------+          +----------+---------+
 Kalshi)                                            |
                                         +----------v---------+
                                         |  arb.py            |  pure functions,
                                         |  matching.py       |  no network
                                         |  fees.py           |
                                         +--------------------+
```

The core rule: **everything that decides "is this an arbitrage" is pure and offline**. HTTP lives only in `clients.py`. This is what makes the logic unit-testable on synthetic data.

## Modules

| File | Role |
|---|---|
| `pm_arb/models.py` | `Quote` (top-of-book of a binary market), `Leg` (one trade with its fee function), `Opportunity` (result: profit per set, ROI, caveat) |
| `pm_arb/fees.py` | Fee functions `f(price) -> dollars per contract`: `no_fee`, `kalshi_taker_fee`, `flat_fee` |
| `pm_arb/arb.py` | `binary_buy`, `basket_buy`, `basket_sell`, `cross_venue` |
| `pm_arb/matching.py` | `similarity` (token Jaccard + sequence ratio), `dates_compatible`, `match_markets` (greedy one-to-one) |
| `pm_arb/clients.py` | `get_json` with retry, parsers (`parse_polymarket_market`, `parse_kalshi_market`; both return `None` for closed, inactive, multivariate or non-binary markets), page iterators |
| `pm_arb/scan.py` | `scan_intra_kalshi`, `scan_intra_polymarket`, `scan_cross`, `event_basket`, `run_cycle` (one full scan on fetched data) |
| `pm_arb/tracking.py` | `to_rows`, CSV append/read, `episodes` (group sightings by legs), `summarize` |
| `scripts/` | CLI entry points that print a ranked report |
| `examples/demo_offline.py` | Runnable walkthrough on synthetic quotes |
| `tests/test_arb.py` | Unit tests for logic, parsers, matching and scanners |

## Data model

All prices are **dollars in [0, 1]**. Kalshi quotes in cents (or dollars in newer payloads), so `clients.py` normalises. A price of `0` or `>= 1` is treated as "no quote" (`None`).

`Quote.no_bid` and `Quote.no_ask` for Polymarket are **derived** from the YES book (`1 - yes_ask`, `1 - yes_bid`) because a binary market there is a single mirrored book.

## Matching algorithm (cross-venue)

1. Lowercase titles, strip punctuation and stop words.
2. `score = 0.5 * Jaccard(tokens) + 0.5 * SequenceMatcher ratio`.
3. Discard pairs whose end dates differ by more than 2 days (unknown dates are kept).
4. Keep pairs with `score >= threshold` (default 0.75), then match greedily best score first, one-to-one.

Candidates come from an inverted index on tokens (at least 2 shared tokens, tokens present in more than 300 right titles ignored): 5,000 x 1,500 synthetic titles match in under 0.1 s, which is what makes one cycle per minute possible.

It is deliberately simple. False matches (same words, different event, for example a different threshold or year) are possible, which is why every result carries a caveat to verify the rules.

## Scanner semantics

| Scanner | Input | Checks |
|---|---|---|
| `scan_intra_kalshi` | all open markets + events | binary YES+NO; for `mutually_exclusive` events: sell-all, and buy-all only with `include_unverified_buys` |
| `scan_intra_polymarket` | events | only `negRisk` events: sell-all; buy-all only for non-augmented events (or with `include_unverified_buys`); fees per market |
| `scan_cross` | Polymarket quotes + Kalshi quotes | both directions on each matched pair |

## Adding a venue

1. Write `parse_<venue>_market(raw) -> Quote` and an iterator in `clients.py`.
2. Add a fee function in `fees.py`.
3. Reuse `cross_venue` and `match_markets` unchanged.
4. Add a parser test with a saved payload.

## Testing

```bash
pytest -q
```

Tests include regression cases built from real API payloads (`tests/fixtures/`). They cover: locked profit, no-arbitrage cases, slippage and fee erosion, 3-outcome baskets, sell-side ROI, direction choice in cross-venue, Kalshi cents/dollars parsing, Polymarket binary-only filtering, mirrored-book behaviour, negRisk and mutually-exclusive event scans, matching and date rejection.
