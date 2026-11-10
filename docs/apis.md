# Data sources

Both sources are **public and read-only**. No API key, no trading.

> **Status.** Both parsers were run against live responses on 2026-11-10 and corrected (see [`findings.md`](findings.md)). Regression fixtures are in `tests/fixtures/`. Schemas evolve: update `clients.py` if a field is renamed.

## Polymarket (Gamma API)

Base URL: `https://gamma-api.polymarket.com`

| Endpoint | Used for | Notes |
|---|---|---|
| `GET /events?active=true&closed=false&order=volume24hr&ascending=false&limit=&offset=` | multi-outcome baskets, and binary markets (flattened) | paginated by `offset`; without `order` the first page is stale; each event has `markets`, `negRisk` and `negRiskAugmented` |

Fields used per market:

| Field | Meaning |
|---|---|
| `id` / `conditionId` | market identifier |
| `question` | title |
| `outcomes` | JSON-encoded string, for example `'["Yes","No"]'`. Only exactly Yes/No markets are kept |
| `bestBid`, `bestAsk` | top of book for the YES token |
| `endDate` | ISO 8601 end date |
| `volume` / `volumeNum` | traded volume |
| `closed`, `active`, `acceptingOrders`, `enableOrderBook` | closed, inactive or non-accepting markets are skipped (11.5% of nested markets are closed) |
| `feesEnabled`, `feeSchedule` | `{rate, exponent, rebateRate, takerOnly}`; used for the taker fee |

`negRisk` events: exactly one outcome is meant to resolve YES. `negRiskAugmented` events can receive new outcomes later, so their listed asks can sum to 0.97 with no arbitrage: buy-side is skipped for them. `bestBid` is often missing on open markets.

## Kalshi (trade API)

Base URL: `https://api.elections.kalshi.com/trade-api/v2`

| Endpoint | Used for | Notes |
|---|---|---|
| `GET /markets?status=open&limit=&cursor=` | **not used**: the default listing is flooded by multivariate combo markets (zero usable quotes in two pages) | cursor pagination |
| `GET /events?status=open&with_nested_markets=true&limit=&cursor=` | baskets **and** all binary quotes (flattened from the nested markets) | event has `mutually_exclusive` and nested `markets`; `limit` up to 200 |

Fields used per market:

| Field | Meaning |
|---|---|
| `ticker` | identifier |
| `title` + `yes_sub_title` | event-level titles are shared by all markets of an event, so the sub-title is appended |
| `yes_bid_dollars`, `yes_ask_dollars`, `no_bid_dollars`, `no_ask_dollars` | **dollar strings** (`"0.0400"`); `"0.0000"` and `"1.0000"` mean no quote. Cents fields are only a fallback |
| `close_time` (fallback `expiration_time`) | end date |
| `volume_fp` | traded volume (fixed-point string) |
| `status`, `mve_collection_ticker` | non-active markets and multivariate combo markets are skipped |

`mutually_exclusive` does **not** imply exhaustive (live example: asks summing to 0.315), so buy-side baskets are off by default. Sell-side results only need mutual exclusivity.

## Rate limiting and errors

`get_json` retries on HTTP 429 and 5xx with exponential back-off (1s, 2s, 4s) and raises on other errors. Keep `--pages` small while testing.

## Fees

`fees.py` ships assumptions, not guarantees:

- Polymarket: taken from each market's `feeSchedule` as `rate * (p * (1 - p)) ** exponent` (formula to verify, see findings); zero when no schedule is published.
- Kalshi: `0.07 * p * (1 - p)` per contract, without the round-up to the next cent.

Always check each venue's current fee schedule and pass your own function (`fee_fn`) if it differs.
