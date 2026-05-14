---
name: firstrade-quote
description: Fetch delayed US equity market data (quotes, OHLC candles, option chains) from Firstrade's public mobile-app API. No login or credentials needed. Trigger when the user asks for a stock price/quote/bid/ask/daily range, candle/OHLC/price history, or option expirations/chains — e.g. "what's AAPL at", "quote NVDA", "INTC last year", "TSLA option chain", "MSFT expirations", "/firstrade-quote NVDA". Supports US-listed equities only; quotes are delayed ~15 min.
---

# firstrade-quote

Three small stdlib-only scripts that talk directly to Firstrade's mobile-app
public API. No login required — only the hardcoded `access-token` header that
ships with the Firstrade Android app. All three scripts share `_client.py`
for the HTTP plumbing.

## Tools

### `quote.py` — equity quotes

```bash
"$CLAUDE_PLUGIN_ROOT/quote.py" AAPL                 # one symbol
"$CLAUDE_PLUGIN_ROOT/quote.py" NVDA INTC AAPL TSLA  # parallel multi-symbol
"$CLAUDE_PLUGIN_ROOT/quote.py" --json TSLA          # machine-readable
```

Returns last price, change ($/% + color), prev close, bid/ask + sizes + MMIDs,
day high/low, volume, and quote/trade timestamps.

### `ohlc.py` — candle data

```bash
"$CLAUDE_PLUGIN_ROOT/ohlc.py" NVDA                  # default range 1d
"$CLAUDE_PLUGIN_ROOT/ohlc.py" NVDA 1y               # year of daily candles
"$CLAUDE_PLUGIN_ROOT/ohlc.py" NVDA 1m --json        # full raw candle list
```

Valid ranges: `24h`, `1d`, `1w`, `1m`, `1y`.
Default output is a summary (candle count, first/last close, range, total
volume, net change). Use `--json` for the full `[ts_ms, o, h, l, c]` tuples
plus aligned `[ts_ms, vol]` entries.

### `options.py` — option expirations & chains

```bash
"$CLAUDE_PLUGIN_ROOT/options.py" NVDA                       # list expirations
"$CLAUDE_PLUGIN_ROOT/options.py" NVDA 20260515              # chain, ATM ±5 strikes
"$CLAUDE_PLUGIN_ROOT/options.py" NVDA 20260515 --all        # full chain
"$CLAUDE_PLUGIN_ROOT/options.py" NVDA 20260515 --json       # raw JSON
```

Without an expiry: prints expirations table (date, days-left, type M=monthly /
W=weekly). With an expiry: fetches the underlying quote to find ATM, then
shows calls + puts for the 11 strikes nearest ATM (strike, bid, ask, last,
volume, open interest). Pass `--all` to show every strike.

**Date format is `YYYYMMDD` (no dashes)** — the API rejects `YYYY-MM-DD`.

If `$CLAUDE_PLUGIN_ROOT` isn't set, the scripts also live at
`~/.claude/skills/firstrade-quote/`.

## Where the data comes from

| Endpoint | Used by |
| --- | --- |
| `/public/quote?account=…&q=<SYM>` | `quote.py`, `options.py` (for ATM) |
| `/public/ohlc?symbol=<SYM>&range=<R>&_v=v2` | `ohlc.py` |
| `/public/oc?m=get_exp_dates&root_symbol=<SYM>` | `options.py` (list expiries) |
| `/public/oc?m=get_oc&root_symbol=<SYM>&exp_date=<YYYYMMDD>&chains_range=A` | `options.py` (chain) |

Every request sends `access-token: 833w3XuIFycv18ybi` and
`User-Agent: okhttp/4.9.2`. No session cookies, no login.

The `account=` query param on `/public/quote` is required but **not validated**
— the script uses `00000000` as a placeholder.

## Important caveats

- **All data is delayed**, not real-time. Quote responses carry `realtime: F`
  for unauthenticated callers. The displayed timestamps lag by ~15 minutes.
- **US equities only.** No FX, futures, international symbols, or crypto.
- **Private API, schema drift risk.** Reverse-engineered from the mobile app;
  not documented, not guaranteed stable. The companion `firstrade` Python
  package's `SymbolQuote` class currently crashes on a missing `shares` field
  — these scripts only read keys they actually use and report drift cleanly.
- **No retry / no rate-limit handling.** A 4xx/5xx prints and continues.

## When to invoke

Invoke whenever the user asks for any of:
- Last price, quote, bid/ask, daily range, volume for a US ticker → `quote.py`
- Price history, candle data, OHLC, "show me the chart" → `ohlc.py`
- Option expirations, option chain, calls/puts at strike X → `options.py`

Do not invoke for: international tickers, FX, futures, crypto, or anything
needing real-time/intraday millisecond accuracy.
