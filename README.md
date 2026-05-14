# firstrade-quote

A Claude Code skill (and standalone CLI) for delayed US equity market data —
**quotes, OHLC candles, and option chains** — from Firstrade's public
mobile-app API. **No login, no credentials, no `pip install`.**

```
$ ./quote.py NVDA INTC
NVDA — NVIDIA Corporation (NASDAQ)
  Last:   $235.60   (+9.77, +4.33%, green)
  Prev close: $225.83
  Bid:    $235.60 x 100  [XNAS]
  Ask:    $235.62 x 200  [IEXG]
  Day:    low $229.30  high $236.47
  Volume: 95,144,693
  Quote time:      11:47:36 am
  Last trade time: 11:47 am
  Realtime:        F

INTC — Intel Corporation (NASDAQ)
  Last:   $116.14   (-4.15, -3.45%, red)
  ...
```

## What it does

Three small stdlib-only scripts sharing one HTTP helper:

| Script | Purpose |
| --- | --- |
| `quote.py` | Last price, bid/ask, day range, volume — one or many symbols in parallel |
| `ohlc.py`  | OHLC candle data (24h, 1d, 1w, 1m, 1y) with summary or raw JSON |
| `options.py` | Option expirations list, or chain for a given expiry (ATM ±5 strikes by default) |

All three output human-readable text by default, with `--json` for the raw
response.

## What it is not

- **Not real-time.** Quote responses carry `realtime: F` for unauthenticated
  callers; data lags by ~15 minutes.
- **Not for FX, futures, crypto, or non-US listings.** US equities only.
- **Not an official Firstrade integration.** The endpoint and access token
  were reverse-engineered from the Firstrade Android app and are not
  documented or guaranteed stable.

## Install

```bash
git clone <this-repo> ~/Documents/ftapi-skill
ln -s ~/Documents/ftapi-skill ~/.claude/skills/firstrade-quote
chmod +x ~/Documents/ftapi-skill/quote.py
```

That's it. The script is stdlib-only (Python 3.10+), so no virtualenv or
dependencies are required for the skill itself. The `venv/` in this directory
holds the `firstrade` package used during exploration but is **not** needed at
runtime.

## Usage

### From Claude Code

The skill auto-triggers on natural-language requests:

> "what's AAPL at" / "quote NVDA" / "price of TSLA"
> "show me NVDA candles for the last year"
> "TSLA option chain expiring 20260620"
> "MSFT option expirations"

Or invoke explicitly:

```
/firstrade-quote NVDA INTC AAPL
```

### From the shell

```bash
# Quotes
./quote.py NVDA                          # one symbol
./quote.py NVDA INTC AAPL TSLA           # parallel multi-symbol
./quote.py --json NVDA INTC              # machine-readable

# OHLC candles
./ohlc.py NVDA                           # default range 1d
./ohlc.py NVDA 1y                        # year of daily candles
./ohlc.py NVDA 1m --json                 # full raw candles

# Options
./options.py NVDA                        # list expirations
./options.py NVDA 20260515               # chain, ATM ±5 strikes
./options.py NVDA 20260515 --all         # full chain (all strikes)
./options.py NVDA 20260515 --json        # raw JSON
```

Option dates use **`YYYYMMDD` format with no dashes** — the API rejects
`YYYY-MM-DD`.

## How it works

```
quote.py / ohlc.py / options.py
   │
   ▼
_client.py  ──HTTPS──►  https://api3x.firstrade.com/public/{quote,ohlc,oc}
                        Headers: access-token: 833w3XuIFycv18ybi
                                 User-Agent:   okhttp/4.9.2
```

- All three scripts share `_client.py` for HTTP + auth.
- `/public/*` endpoints need no session — only the hardcoded `access-token`
  header the Firstrade Android app ships with.
- `quote.py` parallelises multi-symbol fetches via `ThreadPoolExecutor`.
- `options.py` fetches the underlying quote first to find ATM, then filters
  the chain to ±5 strikes around it (unless `--all`).
- No dependency on the `firstrade` Python package — pure stdlib
  (`urllib.request`).

## Files in this repo

```
ftapi-skill/
├── SKILL.md       # Claude skill manifest (frontmatter + trigger description)
├── _client.py     # shared HTTP helper (stdlib only)
├── quote.py       # equity quotes — parallel multi-symbol
├── ohlc.py        # OHLC candle data
├── options.py     # option expirations + chains
├── README.md      # this file
├── FINDINGS.md    # full notes from exploring the firstrade Python package
└── venv/          # exploration-time venv (not required at runtime, gitignored)
```

## Caveats

- **Delayed quotes only.** Treat the timestamp as "the price as of ~15 min
  ago", not "now."
- **No retry / no rate-limit handling.** If the API returns 429 or 5xx, the
  script prints the error and moves on. Firstrade does not publish rate limits
  for this endpoint.
- **Schema drift risk.** The companion `firstrade` Python package's
  `SymbolQuote` class currently crashes on a missing `shares` field. This
  script avoids that pitfall by reading only the keys it actually uses, and
  prints a clear `schema drift, missing <key>` message if the response shape
  changes again.
- **Do not use for trading decisions.** Quote freshness, halts, and
  corporate-action handling are all unverified.

## Extending

The same `access-token`-only auth opens up the rest of the public surface:

| Endpoint | Status |
| --- | --- |
| `/public/quote` | covered by `quote.py` |
| `/public/ohlc` | covered by `ohlc.py` |
| `/public/oc` (expirations + chains) | covered by `options.py` |
| `/private/*` (balances, positions, orders) | **needs login** — see [FINDINGS.md](FINDINGS.md) |

For private endpoints (account balances, positions, order placement), see the
auth flow notes in FINDINGS.md. Those require running through `FTSession.login()`
with credentials + TOTP.

## License / attribution

This skill talks to Firstrade's private mobile-app API. The endpoint, token,
and request shape were derived from the firstrade-api Python package
(<https://github.com/MaxxRK/firstrade-api>). Use at your own risk; the API can
change or be revoked without notice.
