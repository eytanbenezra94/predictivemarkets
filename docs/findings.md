# Live API findings

Real responses from both venues, captured on **2026-11-10**. This page records what was tested, what broke, what was fixed and what is still unknown.

## How the tests were run

- The development sandbox cannot reach either API (HTTP 403 from its network policy), so the requests went through the **Claude desktop built-in browser** running on the owner's computer.
- Polymarket: same-origin `fetch` from the API page worked.
- Kalshi: an in-page `fetch` failed (`TypeError: Failed to fetch`), so each URL was opened by navigation and the JSON was parsed from the page body.
- Samples: **100 Polymarket events** sorted by 24h volume (5,773 nested markets) and **page 1 of Kalshi events** (200 events, 1,813 nested markets, default order). One snapshot, not repeated over time.

## Not tested

| Item | Why it matters |
|---|---|
| Cross-venue scan end to end | needs both datasets in one process; the matching quality on real titles is **unmeasured** |
| Polymarket CLOB order books (`/book`) and `/fee-rate` | depth and the exact fee are unverified |
| Kalshi pagination beyond page 1 (`cursor` was present) | later pages may behave differently |
| Kalshi `mve_filter` query parameter | the request failed for network reasons, so it is neither confirmed nor ruled out |
| Behaviour over time | no measure of how long a gap lasts |

## What the live data looks like

### Polymarket (Gamma `/events`)

| Observation | Value |
|---|---|
| Markets with `feesEnabled` | **5,613 of 5,773 (97.2%)** |
| Largest fee category | `sports_fees_v3` 4,142; `politics_fees` 812; `crypto_fees_v2` 207; `finance_prices_fees` 172 |
| Closed markets inside events requested with `closed=false` | **662 (11.5%)** |
| Markets whose outcomes are not exactly Yes/No (Over/Under, team names) | 2,380 (41%) |
| `negRisk` events (of 100) | 34 (18 of them `negRiskAugmented`) |
| Open markets missing `bestBid` in big negRisk events | e.g. 15 of 57 in "Democratic Presidential Nominee 2028" |

Sum of the best asks over the open markets of each `negRisk` event:

| Group | Events | Sum of asks |
|---|---|---|
| Not augmented | 16 | **1.002 to 1.215**, none below 1 |
| Augmented | 18 | mostly 1.00 to 1.10 (one outlier at 1.949, "Next Press Secretary?"); **three below 1**: Israel PM 0.968, best AI model 2026 0.971, largest company 0.983 |

Sell-side (sum of bids above 1): only **6 events** had a bid on every open market, and all six were below 1 (0.88 to 0.999).

### Kalshi (`/events` with nested markets)

| Observation | Value |
|---|---|
| Events that are `mutually_exclusive` | 55 of 200 |
| Binary markets with both a YES ask and a NO ask | 1,512 |
| Markets with YES ask + NO ask below 1 | **0** (minimum 1.001) |
| Distribution of YES ask + NO ask | 43 below 1.005; 111 in 1.005-1.02; 154 in 1.02-1.05; 917 in 1.05-1.2; 287 above 1.2 |
| Mutually exclusive events with a bid on every market | 31, **none with a bid sum above 0.97** |

Sum of asks of some `mutually_exclusive` events: next Pope **0.315**, Xi Jinping's successor **0.773**, Goldman Sachs COO 0.64, next trillionaire 0.92, Mexico presidential winner 0.86, 2030 World Cup 0.951.

## Problems found and what changed

| # | Problem | Evidence | Fix |
|---|---|---|---|
| 1 | **Polymarket fees assumed to be zero** | 97.2% of markets carry a `feeSchedule` (for example rate 0.05, exponent 1, `takerOnly`) | `Quote.fee_schedule`, `schedule_fee`; fees are taken per market |
| 2 | **Closed markets inside active events** | 662 of 5,773, `acceptingOrders: false`, no `bestBid` | parser skips closed, inactive and non-accepting markets |
| 3 | **Default event order is stale** | the unsorted listing started with expired events | `order=volume24hr&ascending=false` |
| 4 | **Buy-side baskets on non-exhaustive events** | Kalshi sums of 0.315 and 0.773; Polymarket augmented events at 0.968 to 0.983 | buy-side is **off by default** (`--include-unverified-buys` to see it); augmented events are skipped |
| 5 | **Binary YES+NO check can never fire** | 0 of 1,512 Kalshi markets below 1; Polymarket binary is mirrored by construction | kept for completeness, documented as structurally empty |
| 6 | **Kalshi multivariate (MVE) combo markets flood `/markets`** | the first three markets returned were MVE with no quotes; two pages gave 0 usable quotes on the first live run | parser skips `mve_collection_ticker` markets and quotes now come from `/events` instead of `/markets` |
| 7 | **Kalshi volume field** | the field is `volume_fp`, not `volume`; volume was always `None` | parser reads `volume_fp` |
| 8 | **Kalshi shared titles** | every market of an event shares a title such as "GDP growth in 2036?" | the `yes_sub_title` is appended, which matters for matching |
| 9 | **Kalshi no-quote sentinels** | `"0.0000"` (no bid) and `"1.0000"` (no ask) | already mapped to `None`, now covered by a test |
| 10 | **Sell-side ROI** | found while writing the docs: it was measured against the $1 liability | measured against locked capital `N - proceeds` |

Regression tests built from real payloads live in `tests/fixtures/` (26 tests in total).

## What the snapshot says about the strategies

- **No executable arbitrage was found in this snapshot.** Kalshi binary: none. Kalshi sell-side: none. Polymarket non-augmented baskets: always above 1. The apparent buy-side gaps all come from non-exhaustive outcome sets.
- The closest cases (Kalshi "2030 U.S. House winner" at 0.99, two outcomes that are probably not exhaustive) leave about 1 cent gross, which fees remove.
- This is a single snapshot of the most liquid Polymarket events and the first Kalshi page. It says nothing about intraday windows or illiquid markets.
- **The cross-venue project remains unvalidated on live data.**

## First live run of the logger (2026-11-10)

The first run on the owner's machine printed `polymarket=3441 kalshi=0`: **no Kalshi quote was read**. Cause: the default `/markets` listing is dominated by multivariate combo markets, which the parser skips, so two full pages yielded nothing. The earlier browser test had already shown the flood (finding 6) but the fix was incomplete, and unit tests on single payloads could not reveal it. Fixed by taking Kalshi quotes from the nested markets of `/events` (verified clean on page 1), and the logger now prints a warning when a venue returns zero quotes.

Lesson: a sanity check on counts (`n_quotes > 0` per venue) catches this class of bug that payload-level tests miss.

## Still uncertain

- **Polymarket fee formula.** Public sources disagree on whether there is an extra factor `p` and how `exponent` enters. `schedule_fee` uses `rate * (p * (1 - p)) ** exponent`, which reproduces the documented $1.25 per 100 contracts at 50c for rate 0.05. Check `clob.polymarket.com/fee-rate` before relying on a fee-sensitive result.
- **Whether `bestBid` / `bestAsk` match the CLOB book.** Gamma values are a snapshot and may lag.
- **Kalshi fees.** `0.07 * p * (1 - p)` is an assumption without the round-up to the next cent.

## Next: measure how long gaps last

`scripts/log_arb.py` and `scripts/analyze_log.py` answer the open question about time dynamics. The first live run is written up in [`results.md`](results.md): one episode, a valid basket whose edge is about the size of the cost of capital.

## Reproduce locally

```bash
python scripts/scan_intra.py --pages 2                       # default: no buy-side noise
python scripts/scan_intra.py --pages 2 --include-unverified-buys   # shows the false positives
python scripts/scan_cross.py --pages 2 --threshold 0.7       # the untested part: inspect the matches by hand
```
