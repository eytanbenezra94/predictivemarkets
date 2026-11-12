# Fixtures

Excerpts of live API responses captured on 2026-11-10 through the Claude desktop built-in browser.

| File | Origin | Notes |
|---|---|---|
| `polymarket_closed_market.json` | Gamma `/events`, real values | closed market inside an *active* event, `bestBid` absent |
| `polymarket_fee_market.json` | Gamma `/events`, real `feeSchedule` | bid/ask are illustrative (not captured) |
| `kalshi_mve_market.json` | Kalshi `/markets`, real values | multivariate combo market, no quotes |
| `kalshi_event_market.json` | Kalshi `/events` nested market, real values | `no_bid_dollars` derived as 1 - yes_ask |

Captured on 2026-11-12 (built-in browser):

| File | Origin | Notes |
|---|---|---|
| `polymarket_book.json` | CLOB `/book?token_id=...`, real values, trimmed | bids ascending, asks **descending**: best price is the last element. Gamma `clobTokenIds` is a JSON *string* `["<yes>", "<no>"]`, same order as `outcomes` |
