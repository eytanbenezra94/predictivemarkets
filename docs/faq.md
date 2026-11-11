# FAQ

Short answers to the questions this project raises. Derivations are in [`theory.md`](theory.md), measurements in [`findings.md`](findings.md) and [`results.md`](results.md).

**Why does the binary YES + NO check never fire?**
A binary market is one mirrored order book: a YES bid at `b` is a NO ask at `1 - b`. So `ask_YES + ask_NO = 1 + spread`, never below 1. Measured on Kalshi: 0 of 1,512 markets below 1, minimum 1.001.

**Where can an intra-market gap exist, then?**
In multi-outcome events (one market per outcome), where each outcome has its own book and the prices can drift apart.

**Mutually exclusive versus exhaustive?**
Mutually exclusive: at most one outcome pays. Exhaustive: at least one pays. Buying all outcomes is riskless only if both hold. Selling all outcomes needs only exclusivity (the liability is at most $1). Live example: Kalshi's "next Pope" event has asks summing to 0.315, because it is exclusive but far from exhaustive.

**Why is the sell-side ROI divided by `N - proceeds`?**
Selling YES at `b` is economically buying NO at `1 - b`, so the capital locked is `sum(1 - b_i)` = `N - proceeds`. Profit is `proceeds - 1`.

**How are fees modelled?**
Per contract as a function of price. Polymarket: from each market's `feeSchedule`, as `rate * (p * (1 - p)) ** exponent` (formula to verify). Kalshi: `0.07 * p * (1 - p)` (assumption, no round-up). Both are parameters, see `pm_arb/fees.py`.

**Why is slippage a parameter?**
Top-of-book prices have finite size. With 8 legs, a 0.5 cent slippage per leg is 4 cents in total, which can be the whole gap. Vary it with `--slippage`.

**What does the logger measure?**
How often apparent opportunities appear and how long they last. Consecutive sightings of the same legs form an episode; an episode seen once lasted less than the sampling interval. Durations are lower bounds.

**Can an arbitrage be valid and still not worth taking?**
Yes. The Discord IPO basket was exclusive and exhaustive (a guaranteed $1 payout) but returned about 3.6% over roughly 13.7 months, close to the time value of money, and exiting early would have cost more than the gain. See [`results.md`](results.md).

**What are the cross-venue risks?**
The two markets must resolve identically (source, wording, cut-off time, end date). The legs are not atomic across venues. Title matching is heuristic and has not been measured on a long live run.

**What is not validated?**
Cross-venue matching on real titles over time, order-book depth at the quoted prices, the exact Polymarket fee formula, Kalshi pagination beyond page 1, behaviour outside the sampled hours.

**What would be the next step?**
Walk the order book to get size-weighted fills, run the logger for several days from an always-on machine, then add a calibration study (Brier score, reliability diagram) on resolved markets.
