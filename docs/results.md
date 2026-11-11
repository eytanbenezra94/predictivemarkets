# Results of the first live run

Interim results, updated 2026-11-11 16:43: the logger was still running when this was written.

| | |
|---|---|
| Window | 2026-11-10 16:49 to 2026-11-11 16:43 (New York time), interval 60 s, 2 pages per endpoint |
| Cycles recorded | **261**, about 4.4 hours of sampling in a 24 hour window (the laptop slept or was offline in between) |
| Cycles with at least one apparent opportunity | 15.3% (40 of 261), all of them from the single episode below: **0 opportunities in the other 221 cycles** |
| Episodes | **1**, kind `basket_buy`, none cross-venue |
| Duration | at least 2,399 s (40 consecutive sightings) |
| Best profit per set | $0.0041 after 0.5 cent slippage per leg and fees |
| Skipped cycles | several per hour seen in the console, not stored in the CSV: DNS resolution failures and connection resets on the local network, and read timeouts |

**Correction on the cross-venue scan.** The "0 cross-venue opportunities" above carries no information. A diagnostic run on 2026-11-11 (`scripts/diagnose_matching.py`, 4,386 Polymarket and 2,412 Kalshi quotes) found **0 matched pairs at every threshold from 0.60 to 0.95**, so no pair was ever compared during the logging run. The cause is a sampling bias, described in [`findings.md`](findings.md): the Kalshi sample was dominated by markets closing in 2031 or later, while the Polymarket sample is the most traded, near-term events. The sampling was then changed (near-term Kalshi markets only); the logging run has to be repeated with the corrected code before any statement about cross-venue gaps.

## The only episode: "Discord IPO Closing Market Cap" (Polymarket)

Checked on Polymarket's API right after the run (prices moved slightly since the logged cycles).

| Outcome | Best ask | Best bid |
|---|---|---|
| Market cap below $5B | 0.005 | 0.001 |
| $5B to $8B | 0.010 | 0.002 |
| $8B to $11B | 0.007 | 0.002 |
| $11B to $14B | 0.015 | 0.003 |
| $14B to $17B | 0.006 | 0.002 |
| $17B to $20B | 0.014 | 0.003 |
| $20B or more | 0.019 | 0.002 |
| **No IPO by Dec 31, 2027** | **0.882** | **0.859** |
| **Sum** | **0.958** | **0.874** |

**Is it a false positive? No.** The seven brackets are contiguous and the last outcome covers the case where no IPO happens, so the set is mutually exclusive and exhaustive: buying one YES on each pays exactly $1. All eight markets were open and the event is not `negRiskAugmented`.

**Why it can still last 40 minutes:**

| Item | Value (approximate) |
|---|---|
| Gross gap | 1 - 0.958 = 4.2 cents per set |
| Taker fees (schedule rate 0.04, formula assumed) | about 0.7 cent |
| Net, with zero slippage | about 3.5 cents on about 96.5 cents of capital, so **about 3.6%** |
| Horizon | event end date 2028-01-01, about 13.7 months from now (earlier if an IPO happens) |
| Annualised, simple | **about 3%**, to compare with the current risk-free rate (not looked up here) |
| Selling back early | sum of bids 0.874 versus sum of asks 0.958: an **8.4 cent** round-trip loss, more than the gain |

So the gap is real but about the size of the time value of money: capital is tied up until resolution, and nobody competes it away. Order-book depth at these asks was not measured, and the 0.5 cent slippage assumed by the logger across eight legs (4 cents in total) is what turned most of the raw gap into $0.0041.

One more detail: the event's rules text refers to a different label and date than the market question for the "no IPO" outcome. That is a small resolution-wording risk on the largest leg.

## Takeaways

- An apparent arbitrage that lasts long is not necessarily a mis-specified one: it can be structurally valid and economically uninteresting. The checks that matter are the exhaustiveness of the outcomes, the cost of capital until resolution, and the exit cost.
- With 8 legs, the slippage assumption dominates the result. It is a parameter to vary (`--slippage`), not a constant.
- Open questions: depth at the quoted asks, behaviour of the cross-venue matcher on a longer run, how the picture changes outside overnight hours.
- To check that the cross-venue scan sees anything, run `python scripts/diagnose_matching.py`: it prints how many Polymarket and Kalshi markets the matcher pairs at each similarity threshold, lists the best pairs with their end dates and prices so they can be checked by hand, and saves them to `data/matches.csv`. If it pairs almost nothing, the empty result says little about market efficiency.
