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

## The cross-venue scan was blind (2026-11-11)

`scripts/diagnose_matching.py` on live data printed **0 matched pairs at every threshold from 0.60 to 0.95**. The matcher had never been given overlapping markets.

| Observation | Value |
|---|---|
| Kalshi `/events` page 1 (default order), markets by close year | 2026: 16, 2027: 38, 2028-30: 458, **2031 or later: 1,275** (of 1,787) |
| Typical events there | "visit Mars", "next NATO Secretary General", "next Pope" (some close in 2099) |
| Polymarket sample | events sorted by 24h volume, i.e. near-term |

The two samples barely overlap by construction, and the 2-day end-date window rejects the rest.

**Fix.** Kalshi cross-venue quotes now come from `/markets` with two filters verified on live data: `mve_filter=exclude` (0 combo markets left) and `max_close_ts` (a 1,000-market page, all closing in 2027, cursor present; 883 with a YES ask, 342 with both asks; dominated by college football and sports props). Intra-market baskets still use `/events`. The date window is configurable (`--max-days`) and the diagnostic prints pair counts with and without end dates, to show how much the date rule removes.

**Second diagnostic, after the fix (live):** still **0 pairs at every threshold, even with end dates ignored** (4,379 Polymarket quotes, 2,000 Kalshi quotes closing within 90 days). So the empty result is not only a date-window effect: the two samples simply contain no title the matcher considers close.

What the real titles look like:

| | Examples |
|---|---|
| Polymarket top events by volume | NBA games with 300 to 475 markets each (moneyline and spreads have team names as outcomes, player props are Over/Under, only part are Yes/No), crypto price ladders ("Will Bitcoin reach $81,000 on November 11?"), Fed decision ("Will the Fed decrease interest rates by 25 bps after the December 2026 meeting?"), 2028 election ("Will JD Vance win the 2028 US Presidential Election?") |
| Kalshi, closing within 90 days (first 2,000) | dominated by college football series and props; no overlap with the above in this sample |
| Kalshi, closing in Nov 2028 (`min_close_ts` + `max_close_ts`, 1,000 markets, cursor present) | "Will the 2028 presidential election occur?", Republican ticket combinations, vice-presidency nominee markets: related topic, **different market definitions** from Polymarket's "win the election" markets in the 6 titles inspected |

Only 57% of the sampled Polymarket markets are Yes/No (4,046 of 7,138 in the top 100 events): moneylines (team names) and totals (Over/Under) are not parsed, and those are the sports markets where Kalshi also lists contracts. Sampling by close-date windows is now possible (`--min-days`, `--horizon-days`).

## Third diagnostic: the matcher finds pairs, most of the cheap ones are false (2026-11-11)

Run with `--pages 3 --min-days 700 --horizon-days 760` (Kalshi markets closing in roughly 2028): **55 pairs at score >= 0.60** (0 before the window was moved).

| What the pairs are | Score | Raw cost (YES one venue + NO other) |
|---|---|---|
| **Same event**: "win the 2028 Democratic presidential nomination" (Polymarket) vs "be the Democratic Presidential nominee in 2028" (Kalshi) | 0.71 to 0.75 | **0.988 to 1.003** |
| **Different events**: nomination vs "Republican Presidential ticket" (two names), vs "Ohio primary", vs "Iowa caucus" | 0.60 to 0.68 | **0.861 to 0.95** (the "big gaps") |

Two conclusions:

1. **Every apparent gap above 5 cents was a false match.** Different events can legitimately sum to less than 1; that is not arbitrage. Reading the pairs by hand is what exposed it.
2. **The correct pairs show at most 1.2 cents gross before fees and slippage, for about 24 months of locked capital**: roughly 0.5% per year at best, below what the capital earns elsewhere. Not exploitable.

**Matcher fix.** The correct pairs scored barely above the false ones (0.71 to 0.75 against 0.60 to 0.68), so no threshold separated them; the default 0.75 would have kept a single pair. Cause: wording that differs across venues for the same question ("win" / "be", "nomination" / "nominee"). `matching._tokens` now drops `win/wins/become/becomes/elected` and maps `nomination/nominate/nominated` to `nominee`. On the same titles, correct pairs now score **0.95 to 0.96** and false ones **0.57 to 0.69**; the default threshold is **0.85**. This is tuned on a handful of political titles: other categories (sports, crypto, macro) may need their own normalisation, so the diagnostic must be re-run on them. The diagnostic also prints the annualised gross yield of each pair (`annualized_yield`) so a few cents over two years is not mistaken for a gap.

**Not yet verified:** the new threshold on categories other than politics, and whether any pair beats the fees on a short horizon. The 2028 window is the only one that has produced correct pairs so far.

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
