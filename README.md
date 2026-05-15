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
| `positions.py` | List Firstrade accounts and currently held positions | **login required** |

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
```

**Session caveat:** Firstrade allows only one active session per account
across all devices (mobile app, web, this CLI). Every `positions.py`
invocation transparently re-POSTs `/sess/login` to get a fresh `sid` —
this is normal and matches what the upstream `firstrade` package does.
If you log into the Firstrade mobile app, the next `positions.py` run
will just refresh itself (no user action needed). If your cached `ftat`
itself expires (~30 days idle), you'll get a clear message asking you to
run `./login.py request email` again.

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
| `/private/acct_list`, `/private/positions` | covered by `positions.py` |
| `/private/balances`, `/private/account_history`, `/private/order_status` | not yet — same auth as `positions.py` |
| `/private/stock_order`, `/private/option_order` (order placement) | not yet, and intentionally — see FINDINGS.md for safety notes |

For additional `/private/*` endpoints, reuse `_auth.login()` to get headers
and call `_auth.authed_get(path, headers)`. Order placement should be added
deliberately, with a hard-default `dry_run` like the upstream package has.

## License / attribution

This skill talks to Firstrade's private mobile-app API. The endpoint, token,
and request shape were derived from the firstrade-api Python package
(<https://github.com/MaxxRK/firstrade-api>). Use at your own risk; the API can
change or be revoked without notice.
