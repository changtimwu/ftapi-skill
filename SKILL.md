---
name: firstrade-quote
description: Fetch US equity market data and (with login) Firstrade account state + order management. Public endpoints — quotes, OHLC candles, option chains — need no credentials. Account positions/balances/transactions/orders need FIRSTRADE_USERNAME/PASSWORD plus 2FA (TOTP secret or email/SMS OTP via login.py). Trigger when the user asks for: a stock price/quote/bid/ask/daily range, candle/OHLC/price history, option expirations/chains, "my positions"/"what do I own"/"holdings"/"account balance", transaction history ("dividends I received", "trades last month", "account history"), OR order operations ("show my open orders", "cancel order X", "preview a buy of 10 NVDA at $200", "what would it cost to buy …", "place a dry-run sell …"). Examples: "what's AAPL at", "quote NVDA", "TSLA option chain", "show my positions", "dividends YTD", "open orders", "cancel C12345-6", "preview buy 10 INTC at $50". US equities only; quotes are delayed ~15 min.
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
volume, net change). Use `--json` for the full candle list.

**Candle shape varies by range.** `1d` returns 5-tuples `[ts, o, h, l, c]`
with a separate aligned `vol: [[ts, v], …]` array. `1w` / `1m` / `1y`
return 6-tuples `[ts, o, h, l, c, v]` with volume inline; the `vol` array
may be empty. The summary view handles both transparently; if you parse
`--json` yourself, treat the row length as variable: `vol = row[5] if
len(row) > 5 else dict(data['vol']).get(row[0])`.

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

### `history.py` — account transaction history (requires login)

```bash
"$CLAUDE_PLUGIN_ROOT/history.py"                            # default: last 1 month
"$CLAUDE_PLUGIN_ROOT/history.py" ytd                        # range keyword
"$CLAUDE_PLUGIN_ROOT/history.py" 2026-01-01 2026-04-30      # custom range
"$CLAUDE_PLUGIN_ROOT/history.py" --account 12345678 ly      # one account
"$CLAUDE_PLUGIN_ROOT/history.py" --json ytd                 # raw JSON
```

Range keywords: `today`, `1w`, `1m`, `2m`, `mtd`, `ytd`, `ly` — or two
`YYYY-MM-DD` dates (with dashes; the account_history endpoint accepts dashed
format, unlike option dates which want `YYYYMMDD`).

Renders dividends / interest / buys / sells / fees as a table sorted
newest-first, with a per-`trans_str` summary and net cash-flow total:

```
Account 88218207 — range=ytd (6 transactions):
  Date        Type       Symbol     Qty     Price     Amount   Description
  2026-04-16  INTEREST              ...               +0.45    INTEREST ON CREDIT BALANCE…
  2026-03-31  DIV        VOO        ...             +256.52    VANGUARD S&P 500 ETF CASH DIV…
  …
  By type:
    INTEREST     4x   total       +1.50
    DIV          2x   total     +265.68
  NET cash flow:     +267.18
```

Observed `trans_str` values so far: `INTEREST`, `DIV`. Trades (`BUY`/`SELL`) and
fees show up here too — not yet observed in this account.

### `positions.py` — account holdings (requires login)

```bash
"$CLAUDE_PLUGIN_ROOT/positions.py"                   # all accounts + positions
"$CLAUDE_PLUGIN_ROOT/positions.py" 12345678          # one account
"$CLAUDE_PLUGIN_ROOT/positions.py" --list-accounts   # accounts + balances only
"$CLAUDE_PLUGIN_ROOT/positions.py" --json            # raw JSON
```

Unlike the other three scripts, this one hits `/private/*` endpoints and
**requires authentication**. Credentials are read from environment variables
(or a `.env` file in the skill directory):

| Env var | Required | Notes |
| --- | --- | --- |
| `FIRSTRADE_USERNAME` | yes | login username |
| `FIRSTRADE_PASSWORD` | yes | login password |
| `FIRSTRADE_MFA_SECRET` | if 2FA is on | TOTP **seed** (base32 string from Firstrade's 2FA QR), not the 6-digit code |

The session token (`ftat` + `sid`) is cached at
`~/.config/firstrade-skill/session-<username>.json` (mode 0600) and reused
across runs until it expires (~30 days, per `remember_for=30`). Cached sessions
are smoke-tested via `/private/userinfo` before reuse; an invalid cache silently
falls through to a fresh login.

Default output renders accounts and their holdings as tables:

```
Accounts (1 total):
  12345678      total $123,456.78

Positions in 12345678 (3 symbols):
  Symbol            Qty    Avg Cost       Last      Mkt Value      Day Δ    Total P/L
  NVDA           50.000      120.45     235.06     11,753.00    +473.00    +5,730.50
  …
```

If `$CLAUDE_PLUGIN_ROOT` isn't set, the scripts also live at
`~/.claude/skills/firstrade-quote/`.

## Where the data comes from

| Endpoint | Used by | Auth |
| --- | --- | --- |
| `/public/quote?account=…&q=<SYM>` | `quote.py`, `options.py` (for ATM) | access-token only |
| `/public/ohlc?symbol=<SYM>&range=<R>&_v=v2` | `ohlc.py` | access-token only |
| `/public/oc?m=get_exp_dates&root_symbol=<SYM>` | `options.py` (list expiries) | access-token only |
| `/public/oc?m=get_oc&root_symbol=<SYM>&exp_date=<YYYYMMDD>&chains_range=A` | `options.py` (chain) | access-token only |
| `/sess/login`, `/sess/verify_pin`, `/sess/request_code` | `login.py` | — |
| `/private/acct_list`, `/private/positions`, `/private/balances` | `positions.py` | ftat + sid |
| `/private/account_history` | `history.py` | ftat + sid |

Every request sends `access-token: 833w3XuIFycv18ybi` and
`User-Agent: okhttp/4.9.2`. `/public/*` needs nothing else; `/private/*`
additionally needs `ftat` + `sid` from the login response.

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
- "my positions", "what do I own", "show holdings", "account balance" → `positions.py`
- Transaction history, dividends received, trades last month/year, account activity → `history.py`
- Open orders, "show my orders", cancel an order → inline `/private/order_status`, `/private/cancel_order` via `_auth.py`
- "preview a buy/sell", "what would it cost to buy …", "place a dry-run …" → inline `/private/stock_order` with `preview=true` via `_auth.py`

Do not invoke for: international tickers, FX, futures, crypto, or anything
needing real-time/intraday millisecond accuracy.

If `positions.py` exits with a "Missing credentials" message, tell the user
which env vars to set rather than guessing or hardcoding values — never put
real credentials into committed code.

### Order placement safety rules

There is no `order.py` script yet — order placement is handled inline against
`/private/stock_order` using the patterns documented in FINDINGS.md. **Always
follow this sequence:**

1. **Preview first.** Run with `preview=true` (and no `stage` field). This
   round-trips through Firstrade for validation but never places an order.
2. **Show the preview output to the user** (estimated_total, current bid/ask,
   commission) and ask for explicit confirmation before submitting for real.
3. **Real placement** uses `preview=false` + `stage=P`. Capture the returned
   `order_id` and immediately verify via `/private/order_status`.
4. **Never assume "buy NVDA" means real placement.** Default to dry-run unless
   the user explicitly says "place it for real", "submit it", "actually buy",
   or similar unambiguous wording. When in doubt, ask.
5. **For sells**, also confirm the user actually owns enough shares of that
   symbol (cross-check `positions.py`) — Firstrade will reject short sales by
   default but it's friendlier to catch this client-side.
