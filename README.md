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

Four small stdlib-only scripts sharing one HTTP helper:

| Script | Purpose | Auth |
| --- | --- | --- |
| `quote.py`     | Last price, bid/ask, day range, volume — one or many symbols in parallel | none |
| `ohlc.py`      | OHLC candle data (24h, 1d, 1w, 1m, 1y) with summary or raw JSON | none |
| `options.py`   | Option expirations list, or chain for a given expiry (ATM ±5 strikes) | none |
| `positions.py` | List Firstrade accounts and currently held positions + cash | **login required** |
| `history.py`   | Transaction history (dividends, interest, trades, fees) | **login required** |

All scripts output human-readable text by default, with `--json` for the raw
response.

## What it is not

- **Not real-time.** Quote responses carry `realtime: F` for unauthenticated
  callers; data lags by ~15 minutes.
- **Not for FX, futures, crypto, or non-US listings.** US equities only.
- **Not an official Firstrade integration.** The endpoint and access token
  were reverse-engineered from the Firstrade Android app and are not
  documented or guaranteed stable.

## Install

Requires **Python 3.10+** (uses PEP 604 `X | None` syntax). Stdlib only — no
`pip install` needed.

```bash
# Clone wherever you like; example uses ~/src/ftapi-skill
git clone https://github.com/changtimwu/ftapi-skill.git ~/src/ftapi-skill

# Make sure Claude Code's skills directory exists, then symlink the repo into it
mkdir -p ~/.claude/skills
ln -snf ~/src/ftapi-skill ~/.claude/skills/firstrade-quote

# git preserves +x on the committed scripts, but if you grabbed a zip instead
# of cloning, restore them:
chmod +x ~/src/ftapi-skill/{quote,ohlc,options,positions,login}.py
```

Verify:

```bash
~/.claude/skills/firstrade-quote/quote.py NVDA
```

If you see a price block, you're done. Inside Claude Code, type
`/firstrade-quote` to confirm the skill is registered.

The `venv/` in this repo only exists for exploration (it holds the upstream
`firstrade` PyPI package) and is gitignored. Runtime needs nothing from it.

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

#### Positions (requires login)

This is the only command that touches your real Firstrade account. First,
put your username and password in a `.env` file next to the scripts (the
file is gitignored, mode 0600 recommended):

```bash
cat > ~/.claude/skills/firstrade-quote/.env <<'EOF'
FIRSTRADE_USERNAME=your_username
FIRSTRADE_PASSWORD=your_password
# Only set this if your account uses an authenticator app (TOTP) for 2FA;
# leave it out if your second factor is email or SMS.
# FIRSTRADE_MFA_SECRET=YOUR_BASE32_SEED
EOF
chmod 600 ~/.claude/skills/firstrade-quote/.env
```

Then run **one** of these one-time login flows, depending on how your
Firstrade account's 2FA is configured:

- **Email or SMS OTP** (the default for most accounts):

  ```bash
  ./login.py request email          # or `request sms`
  # Read the 6-digit code from your inbox / phone
  ./login.py verify 123456
  ```

- **TOTP / authenticator app** (only if you set up an authenticator
  during Firstrade 2FA enrollment and saved the base32 seed):

  ```bash
  # Add FIRSTRADE_MFA_SECRET to .env first, then:
  ./login.py totp
  ```

After a successful login, the session is cached at
`~/.config/firstrade-skill/session-<user>.json` (mode 0600) and reused for
~30 days. `./login.py status` shows the current state.

Once logged in:

```bash
./positions.py                       # all accounts + holdings + cash
./positions.py 12345678              # one account
./positions.py --list-accounts       # accounts + balances only
./positions.py --json                # raw JSON

./history.py                         # transactions, last 1 month, all accounts
./history.py ytd                     # year-to-date  (or: today/1w/1m/2m/mtd/ly)
./history.py 2026-01-01 2026-04-30   # custom range (YYYY-MM-DD with dashes)
./history.py --account 12345678 ly   # one account
```

**Session caveat:** Firstrade allows only one active session per account
across all devices (mobile app, web, this CLI). Every `positions.py`
invocation transparently re-POSTs `/sess/login` to get a fresh `sid` —
this is normal and matches what the upstream `firstrade` package does.
If you log into the Firstrade mobile app, the next `positions.py` run
will just refresh itself (no user action needed). If your cached `ftat`
itself expires (~30 days idle), you'll get a clear message asking you to
run `./login.py request email` again.

## Example outputs

All shown with illustrative (not real) values where the data is account-
specific. The top-of-page `quote.py` block is reproduced from a live run;
the rest below mirror real shapes but use sanitized numbers.

### `ohlc.py NVDA 1w`

```
NVDA OHLC (1w)
  Candles: 5
  First:   2026-05-08 08:00   close $221.30
  Last:    2026-05-14 08:00   close $235.13
  Range:   $218.40 – $236.47
  Change:  +13.83 (+6.25%)
  Volume:  411,205,884
```

For `--json`, you get the full `[ts_ms, o, h, l, c]` (or `[…, vol]` for 1w+)
tuples plus the aligned `vol` array.

### `options.py NVDA 20260515` (chain, ATM ±5 strikes)

```
NVDA option chain — expiry 20260515
  Underlying: $235.07
  Total strikes: 97, showing 11 calls + 11 puts (ATM ±5)

  CALLS:
     strike      bid      ask     last       vol        oi
     230.00     6.75     6.80     6.25   248,648    91,852
     232.50     4.85     4.95     4.45   272,102    11,892
     235.00     3.35     3.40     2.98   574,982    83,598
     237.50     2.23     2.25     1.92   260,364    13,080
     240.00     1.40     1.42     1.18   305,877    45,189
     ...

  PUTS:
     strike      bid      ask     last       vol        oi
     230.00     0.86     0.88     1.02   159,340     2,079
     232.50     1.51     1.52     1.73   131,542       405
     235.00     2.49     2.52     2.84    80,223     2,635
     ...
```

### `login.py` (one-time auth — email/SMS flow)

```
$ ./login.py request email
Code sent via email to u****@e****.com.
When you have it, run: ./login.py verify <code>
(Code expires in ~10 minutes.)

$ ./login.py verify 123456
Login complete. Session cached — positions.py will now work.

$ ./login.py status
User:    your_username
Session: cached (age 0h1m, ftat=409C73B7…)
Pending: none
```

### `positions.py`

```
Accounts (1 total):
  12345678      total $     XX,XXX.XX

Positions in 12345678 (2 symbols + cash):
  Symbol          Qty   Avg Cost       Last      Mkt Value      Day Δ    Total P/L  Total %
  VOO        100.0000     400.00     680.00      68,000.00    -750.00   +28,000.00  +70.00%
  VT          20.0000      85.00     155.00       3,100.00     -40.00    +1,400.00  +82.35%
  CASH                                            2,500.00
  TOTAL                                          73,600.00    -790.00   +29,400.00  +66.43%
```

### `history.py ytd`

```
Account 12345678 — range=ytd (6 transactions):
  Date        Type       Symbol       Qty     Price      Amount  Description
  2026-04-16  INTEREST              0.0000      0.00       +0.45  INTEREST ON CREDIT BALANCE AT 0.150% 03/16 THRU 04
  2026-03-31  DIV        VOO        0.0000      0.00     +256.52  VANGUARD S&P 500 ETF CASH DIV ON XXX SHS REC 03/27
  2026-03-24  DIV        VT         0.0000      0.00       +9.16  VANGUARD INTL EQUITY INDEX FD TOTAL WORLD STOCK IN
  2026-03-16  INTEREST              0.0000      0.00       +0.40  INTEREST ON CREDIT BALANCE AT 0.150% 02/16 THRU 03
  2026-02-17  INTEREST              0.0000      0.00       +0.44  INTEREST ON CREDIT BALANCE AT 0.150% 01/16 THRU 02
  2026-01-16  INTEREST              0.0000      0.00       +0.21  INTEREST ON CREDIT BALANCE AT 0.150% 01/01 THRU 01

  By type:
    INTEREST     4x   total       +1.50
    DIV          2x   total     +265.68
  NET cash flow:     +267.18
```

Custom date range with two `YYYY-MM-DD` arguments works the same way:

```
$ ./history.py 2026-03-01 2026-03-31
Account 12345678 — 2026-03-01 to 2026-03-31 (3 transactions):
  ...
```

## How it works

```
quote.py / ohlc.py / options.py
   │
   ▼
_client.py  ──HTTPS──►  https://api3x.firstrade.com/public/{quote,ohlc,oc}
                        Headers: access-token: 833w3XuIFycv18ybi
                                 User-Agent:   okhttp/4.9.2


login.py  ─┐
positions.py ──► _auth.py  ──HTTPS──►  /sess/login, /sess/request_code,
                                       /sess/verify_pin
                                  ──►  /private/acct_list, /private/positions,
                                       /private/balances
                       Headers: access-token + ftat + sid
```

- All four data scripts share `_client.py` for the base URL + access-token.
- `/public/*` endpoints need no session — just the hardcoded `access-token`
  header the Firstrade Android app ships with.
- `quote.py` parallelises multi-symbol fetches via `ThreadPoolExecutor`.
- `options.py` fetches the underlying quote first to find ATM, then filters
  the chain to ±5 strikes around it (unless `--all`).
- `_auth.py` implements RFC 6238 TOTP from scratch (no `pyotp` needed) and
  caches only the long-lived `ftat` — `sid` is refreshed on every invocation
  via a re-POST to `/sess/login`.
- No dependency on the upstream `firstrade` PyPI package or `requests` —
  pure stdlib (`urllib.request`, `hmac`, `hashlib`, `base64`).

## Files in this repo

```
ftapi-skill/
├── SKILL.md       # Claude skill manifest (frontmatter + trigger description)
├── _client.py     # shared HTTP helper for /public/* (stdlib only)
├── _auth.py       # login flow + TOTP + session cache for /private/*
├── quote.py       # equity quotes — parallel multi-symbol
├── ohlc.py        # OHLC candle data
├── options.py     # option expirations + chains
├── login.py       # one-time CLI for /private/* login (status/totp/request/verify)
├── positions.py   # account holdings + cash (needs login)
├── history.py     # transaction history — dividends/interest/trades (needs login)
├── README.md      # this file
├── FINDINGS.md    # notes from exploring the firstrade Python package
├── .env           # local credentials (gitignored; create yourself)
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

| Endpoint | Status |
| --- | --- |
| `/public/quote` | covered by `quote.py` |
| `/public/ohlc` | covered by `ohlc.py` |
| `/public/oc` (expirations + chains) | covered by `options.py` |
| `/private/acct_list`, `/private/positions`, `/private/balances` | covered by `positions.py` |
| `/private/account_history` | covered by `history.py` |
| `/private/order_status` | not yet — same auth as `positions.py` |
| `/private/stock_order`, `/private/option_order` (order placement) | not yet, and intentionally — see FINDINGS.md for safety notes |

For additional `/private/*` endpoints, reuse `_auth.login()` to get headers
and call `_auth.authed_get(path, headers)`. Order placement should be added
deliberately, with a hard-default `dry_run` like the upstream package has.

## License / attribution

This skill talks to Firstrade's private mobile-app API. The endpoint, token,
and request shape were derived from the firstrade-api Python package
(<https://github.com/MaxxRK/firstrade-api>). Use at your own risk; the API can
change or be revoked without notice.
