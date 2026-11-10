# Data sources

Both sources are **public and read-only**. No API key, no trading.

> **Status.** The parsers were written from each venue's public documentation and tested on synthetic payloads. They have not been validated against live responses. Before trusting any output, run a scanner and compare a few raw responses with what the parsers extract. Schemas evolve: update `clients.py` if a field is renamed.

## Polymarket (Gamma API)

Base URL: `https://gamma-api.polymarket.com`

| Endpoint | Used for | Notes |
|---|---|---|
| `GET /markets?active=true&closed=false&limit=&offset=` | binary markets for the cross-venue scan | paginated by `offset` |
| `GET /events?active=true&closed=false&limit=&offset=` | multi-outcome baskets | each event has `markets` and a `negRisk` flag |

Fields used per market:

| Field | Meaning |
|---|---|
| `id` / `conditionId` | market identifier |
| `question` | title |
| `outcomes` | JSON-encoded string, for example `'["Yes","No"]'`. Only exactly Yes/No markets are kept |
| `bestBid`, `bestAsk` | top of book for the YES token |
| `endDate` | ISO 8601 end date |
| `volume` / `volumeNum` | traded volume |
| `closed`, `active` | closed or inactive markets are skipped |

`negRisk` events: exactly one outcome is meant to resolve YES, so the YES prices should sum to about 1. They can contain placeholder or "other" outcomes, so buy-side results carry an exhaustiveness warning.

## Kalshi (trade API)

Base URL: `https://api.elections.kalshi.com/trade-api/v2`

| Endpoint | Used for | Notes |
|---|---|---|
| `GET /markets?status=open&limit=&cursor=` | every open market | cursor pagination |
| `GET /events?status=open&with_nested_markets=true&limit=&cursor=` | baskets | event has `mutually_exclusive` and nested `markets` |

Fields used per market:

| Field | Meaning |
|---|---|
| `ticker` | identifier |
| `title` (fallback `yes_sub_title`) | title |
| `yes_bid`, `yes_ask`, `no_bid`, `no_ask` | cents, or `*_dollars` strings in newer payloads (the `_dollars` field wins if present) |
| `close_time` (fallback `expiration_time`) | end date |
| `volume` | traded volume |

`mutually_exclusive` does not imply exhaustive: buy-side basket results are flagged. Sell-side results only need mutual exclusivity.

## Rate limiting and errors

`get_json` retries on HTTP 429 and 5xx with exponential back-off (1s, 2s, 4s) and raises on other errors. Keep `--pages` small while testing.

## Fees

`fees.py` ships assumptions, not guarantees:

- Polymarket: `no_fee` by default.
- Kalshi: `0.07 * p * (1 - p)` per contract, without the round-up to the next cent.

Always check each venue's current fee schedule and pass your own function (`fee_fn`) if it differs.
