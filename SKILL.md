---
name: firstrade-quote
description: Fetch delayed US equity quotes (last price, bid/ask, day range, volume, change %) using Firstrade's public quote API. No login or credentials needed. Trigger when the user asks for a stock price, quote, bid/ask, or daily range — e.g. "what's AAPL at", "quote NVDA", "show me INTC", "price of TSLA", or `/firstrade-quote MSFT`. Accepts one or many tickers in a single call.
---

# firstrade-quote

Fetch US equity quotes by hitting Firstrade's mobile-app public quote endpoint directly. The endpoint needs no login — only a hardcoded `access-token` header (reverse-engineered from the Firstrade Android app).

## Usage

```bash
"$CLAUDE_PLUGIN_ROOT/quote.py" AAPL NVDA INTC
"$CLAUDE_PLUGIN_ROOT/quote.py" --json TSLA          # machine-readable
```

If `$CLAUDE_PLUGIN_ROOT` isn't set in your environment, use the skill's directory directly:

```bash
~/.claude/skills/firstrade-quote/quote.py AAPL
```

Multiple symbols are fetched in parallel. Output is plain text, one block per symbol with last price, change ($ and %), bid/ask + MMIDs, day range, volume, and quote time.

## What the data looks like

```
NVDA — NVIDIA Corporation (NASDAQ)
  Last:   $236.33   (+10.50, +4.65%, green)
  Prev close: $225.83
  Bid:    $236.31 x 300  [IEXG]
  Ask:    $236.34 x 200  [IEXG]
  Day:    low $229.30  high $236.47
  Volume: 93,716,902
  Quote time:      11:43:25 am
  Last trade time: 11:43 am
  Realtime:        F
```

## Where the data comes from

- Endpoint: `https://api3x.firstrade.com/public/quote?account=00000000&q=<SYMBOL>`
- Auth: only an `access-token: 833w3XuIFycv18ybi` header — same value the Firstrade Android app uses.
- The `account=` query param is required by the server but **not validated** — any placeholder works (the script uses `00000000`).
- The script is stdlib-only (`urllib.request`, `concurrent.futures`). No `pip install` needed.

## Important caveats

- **Quotes are delayed**, not real-time. The response has `realtime: F` for unauthenticated callers. The `quote_time` field is server-side and lags by ~15 minutes on US equities.
- **US equities only.** No FX, no futures, no international symbols.
- **No options/OHLC here.** This skill is equity quotes only. Firstrade's public API also exposes `/public/ohlc` and `/public/oc` (option chains, expirations) — extend the script if needed.
- **Private API, schema drift risk.** This is a reverse-engineered endpoint, not documented or stable. The companion `firstrade` Python package's `SymbolQuote` class currently crashes on a missing `shares` field — this script does not depend on `shares` and surfaces schema drift with a clear `missing <key>` message instead of crashing.

## When to invoke

Invoke whenever the user asks for any of:
- "quote <ticker>", "what's <ticker> at", "price of <ticker>"
- "show me <ticker(s)>" in a markets/trading context
- bid/ask, daily range, volume for a US-listed symbol

Do not invoke for: international tickers, options, FX, futures, crypto.

## On errors

- HTTP 4xx/5xx → the script prints the error inline and continues for other symbols. Do not retry — there is no documented SLA.
- Schema drift (missing field) → the script falls back to printing the raw JSON so the user can inspect.
- Network failures → printed as `network: <reason>`.
