# predictivemarkets

Quant projects on prediction markets (Polymarket, Kalshi). Pure Python, public read-only APIs, no API keys, no trading.

Every binary contract settles at **$1 or $0**, so prices behave like probabilities and a few mispricings lock in a profit whatever the outcome. This repo detects them and, just as importantly, shows why they are usually small or absent once fees and frictions are included.

## Projects

| # | Project | Question | Entry point |
|---|---|---|---|
| 1 | **Intra-market arbitrage** | Do the outcome prices of one market or event add up to $1? | `scripts/scan_intra.py` |
| 2 | **Cross-venue arbitrage** | Is the same event priced differently on Polymarket and Kalshi? | `scripts/scan_cross.py` |
| 3 | **Opportunity logger** | How often do apparent arbitrages appear and **how long do they last**? | `scripts/log_arb.py`, `scripts/analyze_log.py` |

## Quick start

```bash
git clone https://github.com/eytanbenezra94/predictivemarkets
cd predictivemarkets
pip install -r requirements.txt

python examples/demo_offline.py        # no network: hand-checkable examples
pytest -q                              # 32 unit tests, no network

python scripts/scan_intra.py --slippage 0.005 --min-profit 0.002
python scripts/scan_cross.py --threshold 0.75 --slippage 0.005

# project 3: sample every minute, then measure how long gaps last
python scripts/log_arb.py --interval 60 --pages 2          # Ctrl-C to stop
python scripts/analyze_log.py --interval 60
```

Requires Python 3.9+ (tested on 3.13).

## The idea in 30 seconds

For mutually exclusive and exhaustive outcomes with ask prices `a_i`, buying one YES on each pays exactly $1:

```
profit = 1 - sum_i ( a_i + slippage + fee(a_i) )
```

| Strategy | Condition | Needs |
|---|---|---|
| **Buy-side basket** (binary = 2 outcomes) | `sum(asks) < 1` | exhaustive outcomes |
| **Sell-side basket** | `sum(bids) > 1` | mutual exclusivity only |
| **Cross-venue** | `YES ask on A + NO ask on B < 1` | identical resolution rules |

Full derivations, worked examples and ROI definitions: [`docs/theory.md`](docs/theory.md).

## Example output (`examples/demo_offline.py`)

```
--- 1. Binary YES+NO < 1 (no fees)
basket_buy: profit/set $0.0500, ROI 5.26%
  BUY_YES  @ 0.45 [kalshi] Will it rain tomorrow?
  BUY_NO   @ 0.50 [kalshi] Will it rain tomorrow?

--- 2. Same market, Kalshi fee model
basket_buy: profit/set $0.0152, ROI 1.54%

--- 5. Cross-venue (no fees)
cross_venue: profit/set $0.0500, ROI 5.26%
  BUY_YES  @ 0.40 [polymarket] Fed cuts in December
  BUY_NO   @ 0.55 [kalshi] Fed cuts in December

--- 6. Cross-venue with 0.5c slippage per leg and Kalshi fees
cross_venue: profit/set $0.0227, ROI 2.32%
```

A 5 cent gap shrinks to about 1.5 cents after fees on a single market, which is the typical order of magnitude of these edges.

## Opportunity logger

A gap that exists for two seconds cannot be traded by hand. The logger samples both venues every `--interval` seconds, runs every scanner (intra-market on both venues plus cross-venue) and appends to two CSV files in `data/` (git-ignored):

| File | Content |
|---|---|
| `data/opportunities.csv` | one row per opportunity per cycle: timestamp, stable key (hash of the legs), kind, profit per set, ROI, legs |
| `data/cycles.csv` | one row per cycle: number of quotes per venue and number of opportunities (the denominator) |

`analyze_log.py` groups consecutive sightings of the same legs into **episodes** (a gap of more than 2.5 intervals ends an episode) and reports the share of cycles with an opportunity, episode durations (a lower bound: one sighting counts as one interval), the share seen only once, and the best episodes. An episode seen once lasted less than the interval.

A failed request skips the cycle instead of stopping the logger. Keep the interval at 30 s or more: each cycle makes a handful of public requests per venue.

## Use it as a library

```python
from pm_arb.arb import binary_buy, cross_venue
from pm_arb.fees import kalshi_taker_fee
from pm_arb.models import Quote

q = Quote("kalshi", "TICKER", "Will X happen?", yes_ask=0.45, no_ask=0.50)
opp = binary_buy(q, fee_fn=kalshi_taker_fee, slippage=0.005)
print(opp.profit_per_set if opp else "no arbitrage")
```

`Opportunity` fields: `kind`, `description`, `legs` (side, price, venue, label), `profit_per_set`, `roi`, `caveat`.

## Scanner options

| Flag | Script | Default | Meaning |
|---|---|---|---|
| `--slippage` | both | 0.005 | extra dollars paid per contract per leg |
| `--min-profit` | both | 0.002 / 0.0 | hide opportunities below this profit per set |
| `--pages` | both | 5 | pages fetched per endpoint (more pages, more markets, slower) |
| `--threshold` | cross | 0.75 | title similarity cutoff for matching markets |
| `--include-unverified-buys` | intra | off | also show buy-all baskets on non-exhaustive events (mostly false positives) |

## Repository layout

```
pm_arb/
  models.py     Quote, Leg, Opportunity
  fees.py       fee models (assumptions)
  arb.py        pure arbitrage logic, no network
  matching.py   title + end-date matching across venues
  clients.py    Polymarket Gamma and Kalshi public endpoints + parsers
  scan.py       scanners combining clients and logic, plus `run_cycle`
  tracking.py   CSV logging, episodes and duration statistics
scripts/        command-line scanners, logger and log analysis
examples/       offline demo on synthetic quotes
tests/          unit tests + fixtures from real API responses
docs/           theory, architecture, data sources
```

## Documentation

| Document | Content |
|---|---|
| [`docs/theory.md`](docs/theory.md) | contingent-claim view, formulas, ROI, why edges are small |
| [`docs/architecture.md`](docs/architecture.md) | modules, data model, matching algorithm, how to add a venue |
| [`docs/apis.md`](docs/apis.md) | endpoints, fields used, fee assumptions, rate limits |
| [`docs/results.md`](docs/results.md) | **first live run of the logger**: counts, the one episode found, why it is not exploitable |
| [`docs/findings.md`](docs/findings.md) | **live test results**: what the real APIs return, bugs found and fixed, what is still untested |

## Limitations (read before trusting any output)

- **Partly validated on live data (2026-11-10).** Both parsers were run against real responses and fixed accordingly, but the cross-venue scan, order-book depth and time dynamics are **untested**. Details in [`docs/findings.md`](docs/findings.md).
- **No executable arbitrage was found in the live snapshot.** Apparent gaps came from non-exhaustive outcome sets, so buy-side baskets are off by default.
- **Polymarket binary markets are one mirrored book**, so YES+NO arbitrage essentially never appears there. Real edges show up in **multi-outcome (negRisk) events** and **across venues**.
- **Buy-side baskets assume exhaustive outcomes.** Venues do not always say so, so those results carry a warning.
- **Cross-venue matching is heuristic** (title similarity + end date). A locked profit requires **identical resolution rules**: read both before acting.
- **Top-of-book only.** No order-book depth, no latency, no atomic execution across venues, no cost of capital lock-up.
- **Fees matter.** 97% of the sampled Polymarket markets carry a taker fee; the formula is an assumption to verify (see findings). Kalshi's is also an assumption.
- Educational code, not financial advice.

## Roadmap

- [ ] Order-book depth and size-weighted fills
- [x] Snapshot logging and opportunity duration (`log_arb.py`, `analyze_log.py`): written and tested on simulated data, **not yet run on live data**
- [ ] Calibration analysis (Brier score, reliability diagram) on resolved markets
- [ ] Kelly sizing against a model probability

## License

MIT
