# Theory

## 1. Prediction markets as contingent claims

A binary contract on event `E` pays **$1 if E happens, $0 otherwise**. Its price `p` in `[0, 1]` is read as the market's probability of `E`. Holding YES and NO on the same event always pays exactly $1:

```
YES + NO = $1 at settlement, whatever happens
```

So absent frictions, `price(YES) + price(NO) = 1`. Arbitrage exists when frictions (spread, fragmented liquidity, delayed updates) let the sum of what you **pay** drop below the guaranteed payout, or the sum of what you **receive** rise above it.

## 2. Notation

| Symbol | Meaning |
|---|---|
| `a_i` | ask price (what you pay) of YES on outcome `i` |
| `b_i` | bid price (what you receive) of YES on outcome `i` |
| `N` | number of outcomes in the basket |
| `f(p)` | fee per contract at price `p` |
| `s` | slippage assumption, extra dollars paid per contract per leg |

## 3. Buy-side basket (needs exhaustive outcomes)

If the outcomes are **mutually exclusive and exhaustive**, exactly one pays $1. Buying one YES on each:

```
cost   = sum_i ( a_i + s + f(a_i) )
payout = 1                                   (certain)
profit = 1 - cost
ROI    = profit / cost
```

A **binary market** is the case `N = 2` with legs `[YES ask, NO ask]`.

**Worked example.** Asks 0.40 / 0.30 / 0.27 with no fees and `s = 0`: cost 0.97, profit **$0.03**, ROI 3.09%.

## 4. Sell-side basket (needs only mutual exclusivity)

If outcomes are mutually exclusive, **at most one** pays $1. Selling one YES on each:

```
proceeds = sum_i ( b_i - s - f(b_i) )
liability <= 1
profit (worst case) = proceeds - 1
```

Exhaustiveness is not required: if no outcome occurs you keep all the proceeds, which is better than the worst case.

Selling YES at `b` is economically the same as buying NO at `1 - b`, so the capital locked up is `sum(1 - b_i + s + f)= N - proceeds`:

```
ROI = (proceeds - 1) / (N - proceeds)
```

**Worked example.** Bids 0.40 / 0.35 / 0.30: proceeds 1.05, profit **$0.05**, capital 1.95, ROI 2.56%.

## 5. Cross-venue arbitrage

Same event `E` on venues A and B. Buy YES on A and NO on B (or the reverse):

```
cost   = a_YES(A) + s + f_A(a_YES(A))  +  a_NO(B) + s + f_B(a_NO(B))
profit = 1 - cost
```

The scanner evaluates both directions and keeps the better one.

**This is only a true arbitrage if both contracts resolve identically.** Differences in the resolution source, the exact wording, the timezone cut-off or the end date turn a "locked" profit into a bet on rule interpretation.

## 6. Why the edge is usually small or absent

- **Fees.** Kalshi-style `0.07 * p * (1 - p)` costs up to 1.75 cents per leg at p = 0.5. Polymarket now publishes a `feeSchedule` on 97% of sampled markets (for example rate 0.05, about 1.25 cents per leg at 50c). With two legs this wipes out most 2-3 cent gaps (see `examples/demo_offline.py`).
- **Mutually exclusive is not exhaustive.** Live Kalshi events list outcomes whose asks sum to 0.31 (next Pope) or 0.77: buying them all is not riskless. See `docs/findings.md`.
- **Mirrored books.** On Polymarket a binary market is one order book: a YES bid at `b` is a NO ask at `1 - b`. Then `a_YES + a_NO = 1 + spread >= 1` by construction, so the plain YES+NO check never fires there. On Kalshi's live data it never fired either (0 of 1,512 markets, minimum 1.001).
- **Depth.** Top-of-book prices have finite size. The profit per set is not the profit you can scale.
- **Capital lock-up.** A 3% edge that settles in 6 months is about 6% annualised before the opportunity cost of capital.
- **Execution risk.** The legs are not atomic across venues. A leg that fills while the other moves leaves you with a directional position.
- **Settlement risk.** Disputed or delayed resolutions, platform and counterparty risk.

## 7. Further extensions

- Walk the order book to compute the size-weighted fill price instead of top-of-book.
- Persist snapshots and measure how long opportunities last.
- Calibration analysis (Brier score, reliability diagrams) of resolved markets.
- Kelly sizing on a model probability versus the market price.
