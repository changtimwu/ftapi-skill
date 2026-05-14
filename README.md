# firstrade-quote

A Claude Code skill (and standalone CLI) that fetches delayed US equity quotes
from Firstrade's public mobile-app API. **No login, no credentials, no
`pip install`.**

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

- Fetches last price, change ($ and %), bid/ask + sizes + MMIDs, day high/low,
  volume, and quote timestamps for one or more US-listed equity symbols.
- Multiple symbols are fetched in parallel.
- Outputs human-readable text by default, or JSON with `--json`.

## What it is not

- **Not real-time.** The API returns `realtime: F` for unauthenticated callers;
  quotes lag by ~15 minutes.
- **Not for options, OHLC, FX, futures, crypto, or non-US listings.** The
  underlying API has option/OHLC endpoints too — this skill just covers equity
  quotes. See [FINDINGS.md](FINDINGS.md) for the full API surface.
- **Not an official Firstrade integration.** The endpoint and access token were
  reverse-engineered from the Firstrade Android app and are not documented or
  guaranteed stable.

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

The skill auto-triggers on natural-language quote requests:

> "what's AAPL at"
> "quote NVDA"
> "show me INTC and MSFT"
> "price of TSLA"

Or invoke explicitly:

```
/firstrade-quote NVDA INTC AAPL
```

### From the shell

```bash
./quote.py NVDA                       # one symbol
./quote.py NVDA INTC AAPL TSLA        # many, fetched in parallel
./quote.py --json NVDA INTC           # machine-readable
```

JSON output is a list of result objects, one per requested symbol, preserving
input order. Errored symbols include an `error` key.

## How it works

```
quote.py ──HTTPS──► https://api3x.firstrade.com/public/quote
                    ?account=00000000&q=<SYMBOL>
                    Headers: access-token: 833w3XuIFycv18ybi
                             User-Agent:   okhttp/4.9.2
```

- The `/public/quote` endpoint requires no session — only the hardcoded
  `access-token` header that the Firstrade Android app ships with.
- The `account=` query parameter is required by the server but **not
  validated**; any placeholder works.
- Parallel fetches use `concurrent.futures.ThreadPoolExecutor`.
- The script does not depend on the `firstrade` Python package — it talks
  directly to the HTTP endpoint with `urllib.request`.

## Files in this repo

```
ftapi-skill/
├── SKILL.md       # Claude skill manifest (frontmatter + trigger description)
├── quote.py       # the fetcher; stdlib only, executable
├── README.md      # this file
├── FINDINGS.md    # full notes from exploring the firstrade Python package
└── venv/          # exploration-time venv (not required at runtime)
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

The underlying API also exposes:

| Endpoint | Use |
| --- | --- |
| `/public/ohlc?symbol=…&range=…` | candle data (24h, 1d, 1w, 1m, 1y) |
| `/public/oc?m=get_exp_dates&root_symbol=…` | option expiration list |
| `/public/oc?m=get_oc&root_symbol=…&exp_date=YYYYMMDD` | option chain |

All three work with the same `access-token` header and no login. See
[FINDINGS.md](FINDINGS.md) for response shapes and quirks (notably:
`exp_date` must be `YYYYMMDD`, not `YYYY-MM-DD`).

## License / attribution

This skill talks to Firstrade's private mobile-app API. The endpoint, token,
and request shape were derived from the firstrade-api Python package
(<https://github.com/MaxxRK/firstrade-api>). Use at your own risk; the API can
change or be revoked without notice.
