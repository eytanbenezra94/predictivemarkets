# predictivemarkets

Quant projects on prediction markets (Polymarket, Kalshi). Pure Python, public read-only APIs, no API keys.

Every contract settles at **$1 or $0**, so prices behave like probabilities and some mispricings lock in a profit regardless of the outcome.

## Projects

| # | Project | Idea | Entry point |
|---|---|---|---|
| 1 | **Intra-market arbitrage** | Outcome prices that do not add up to $1 (binary YES+NO, multi-outcome baskets) | `scripts/scan_intra.py` |
| 2 | **Cross-venue arbitrage** | Same event priced differently on Polymarket and Kalshi | `scripts/scan_cross.py` |

### Math

For a set of mutually exclusive and exhaustive outcomes with ask prices `p_i`, buying one YES of each pays exactly $1:

```
profit = 1 - sum_i ( p_i + slippage + fee(p_i) )      # buy-side, needs exhaustive outcomes
profit = sum_i ( b_i - slippage - fee(b_i) ) - 1      # sell-side, needs mutual exclusivity only
```

A binary market is the 2-outcome case `[YES ask, NO ask]`. Cross-venue: buy YES on venue A and NO on venue B, cost `yes_ask_A + no_ask_B`.

## Layout

```
pm_arb/
  arb.py        pure arbitrage logic (no network)
  fees.py       fee models (assumptions, check current schedules)
  matching.py   title + end-date matching across venues
  clients.py    Polymarket Gamma and Kalshi public endpoints + parsers
  scan.py       scanners combining clients and logic
scripts/        command-line scanners
tests/          unit tests on synthetic quotes
```

## Usage

```bash
pip install -r requirements.txt
pytest -q
python scripts/scan_intra.py --slippage 0.005
python scripts/scan_cross.py --threshold 0.75
```

## Caveats

- On Polymarket a binary market is a single mirrored book, so YES+NO arbitrage essentially never appears there. Real edges show up in **multi-outcome (negRisk) events** and **across venues**.
- Buy-side baskets assume the outcomes are **exhaustive**. Venues do not always say so, so these results carry a warning: verify by hand.
- Cross-venue matches are **heuristic** (title similarity + end date). A locked profit requires **identical resolution rules**: read both before trading.
- Top-of-book quotes only: no depth, no latency, no capital lockup cost. Edges after fees are usually tiny.
- Fee models are assumptions. API schemas can change: the parsers are unit-tested on synthetic payloads, so check them against live responses first.
- Educational code, not financial advice.

## License

MIT
