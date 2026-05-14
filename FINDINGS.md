# firstrade-api 0.0.38 — Source Exploration

Notes from reading the installed package at
`venv/lib/python3.14/site-packages/firstrade/`.

## Package map

```
firstrade/
├── __init__.py     # re-exports: account, order, symbols, urls
├── urls.py         # endpoint builders — every call hits api3x.firstrade.com
├── exceptions.py   # Login/Quote/Account error hierarchy
├── account.py      # FTSession (auth) + FTAccountData (read account state)
├── order.py        # Order placement + 5 enums (PriceType, Duration, OrderType, OrderInstructions, OptionType)
└── symbols.py      # SymbolQuote, OptionQuote, SymbolOHLC
```

Whole package is ~45KB. It is a thin wrapper around the
`api3x.firstrade.com` private REST API used by Firstrade's mobile app.
Giveaways: `User-Agent: okhttp/4.9.2` (Android OkHttp client) and a
hardcoded `access-token` constant in `urls.access_token()`. There is no
officially published API — this is reverse-engineered from the app.

## Auth flow (`FTSession.login`)

Three MFA paths, selected in `_handle_mfa()`:

1. **`pin`** → `_handle_pin_mfa` (PIN-based). Single `login()` call,
   returns `False`.
2. **`email` or `phone`** → `_handle_otp_mfa`. Requests a code; `login()`
   returns `True`, caller must invoke `login_two(code)` with the
   delivered OTP to finish.
3. **`mfa_secret` (TOTP seed)** → `_handle_secret_mfa`. Uses
   `pyotp.TOTP(secret).now()` to generate the 6-digit code locally.
   Single `login()` call, returns `False`.

Cookies — specifically the `ftat` session token — are persisted
unconditionally to `ft_cookies<username>.json` in CWD (or in
`profile_path` if set). On the next `login()`, the saved `ftat` is sent
in request headers via `_load_cookies()`, so repeat logins skip MFA
until the token expires.

`FTSession.__getattr__` forwards unknown attribute access to the
underlying `requests.Session`, so `ft_ss.get(...)`, `ft_ss.headers`,
etc. work transparently.

## FTAccountData

`FTAccountData(ft_ss)` eagerly fetches `user_info` + `acct_list` on
construction → populates `account_numbers`, `account_balances`,
`all_accounts`.

Methods:

| Method | Purpose |
| --- | --- |
| `get_account_balances(account)` | Raw balances JSON |
| `get_positions(account)` | Current holdings |
| `get_account_history(account, date_range, custom_range)` | Transactions. `date_range` ∈ {today, 1w, 1m, 2m, mtd, ytd, ly, cust}; `cust` requires `custom_range=["YYYY-MM-DD","YYYY-MM-DD"]` |
| `get_orders(account)` | Recent orders |
| `cancel_order(order_id)` | Cancel by id |
| `get_balance_overview(account, keywords=None)` | Convenience: recursively walks the balances response and returns dot-notated keys whose path contains any keyword (default: cash, avail, withdraw, buying, bp, equity, value, margin) |

## Order placement

`Order(ft_ss).place_order(...)` / `.place_option_order(...)`.

- Both default to `dry_run=True` — must explicitly pass
  `dry_run=False` to actually submit.
- Two-stage submission: first POST with `preview=true`, then if not a
  dry run, a second POST with `preview=false, stage=P`.
- AON orders are validated locally: must be LIMIT and >100
  shares/contracts.
- For `MARKET` orders without `notional`, `price` is forced to `""`.
- `notional=True` (equity only) replaces `shares` with `dollar_amount`.

### Enums (`order.py`)

```python
PriceType:        MARKET=1, LIMIT=2, STOP=3, STOP_LIMIT=4,
                  TRAILING_STOP_DOLLAR=5, TRAILING_STOP_PERCENT=6
Duration:         DAY=0, DAY_EXT=D, OVERNIGHT=N, GT90=1
OrderType:        BUY=B, SELL=S, SELL_SHORT=SS, BUY_TO_COVER=BC,
                  BUY_OPTION=BO, SELL_OPTION=SO
OrderInstructions: NONE=0, AON=1, OPG=4, CLO=5
OptionType:       CALL=C, PUT=P
```

## Quotes & market data (`symbols.py`)

- `SymbolQuote(ft_ss, account, symbol)` — eagerly fetches and unpacks
  ~25 fields (bid/ask/last + sizes + MMIDs, OHLC for the day, volume,
  company name, `is_etf`, `is_fractional`, `has_option`, …).
- `OptionQuote(ft_ss, symbol)` — on construction fetches expiration
  dates into `.option_dates`. Then:
  - `get_option_quote(symbol, exp_date)` — option chain for one expiry
  - `get_greek_options(symbol, exp_date)` — greeks for the chain
- `SymbolOHLC(ft_ss, symbol, range_)` — `range_` ∈ {24h, 1d, 1w, 1m,
  1y}. Aligns volume with candles (separate arrays in the API
  response) and exposes `(timestamp_ms, open, high, low, close,
  volume)` tuples in `.candles`.

## Endpoints (`urls.py`)

All under `https://api3x.firstrade.com/`:

| Path | Purpose |
| --- | --- |
| `/sess/login`, `/sess/request_code`, `/sess/verify_pin` | Auth/MFA |
| `/private/userinfo`, `/private/acct_list` | User + accounts |
| `/private/balances`, `/private/positions`, `/private/account_history` | Account state |
| `/private/order_status`, `/private/stock_order`, `/private/option_order`, `/private/cancel_order` | Orders |
| `/private/greekoptions/analytical` | Option greeks |
| `/public/quote`, `/public/ohlc`, `/public/oc` | Market data |

`urls.access_token()` returns the hardcoded string `"833w3XuIFycv18ybi"` —
sent in the `access-token` header on every request.

## Which endpoints actually need login?

Tested empirically against the live API with **only** the hardcoded
`access-token` header (no `ftat`, no `sid`, no `FTSession.login()`
call):

| Endpoint | Auth needed | Notes |
| --- | --- | --- |
| `/public/quote` | **No** | `account=` query param is required by the server but **not validated** — a bogus `account=00000000` returned a real INTC quote. |
| `/public/ohlc` | **No** | Candles return without an account param. |
| `/public/oc?m=get_exp_dates` | **No** | Option expiration list. |
| `/public/oc?m=get_oc` | **No** | Option chain. `exp_date` must be `YYYYMMDD`, not `YYYY-MM-DD`. |
| `/private/*` (balances, positions, orders, history, cancel) | **Yes** | Need a valid `ftat`/`sid` from `FTSession.login()`. |

Implication: a read-only quotes/OHLC/option-chain client can be built
without ever logging in. The `SymbolQuote(ft_session, account, symbol)`
signature forces you to pass an account because it gets templated into
the URL, but the server doesn't enforce it on `/public/*` routes.

## Mismatches between installed code and the GitHub `test.py`

The example at
`https://github.com/MaxxRK/firstrade-api/raw/refs/heads/main/test.py`
is ahead of the published 0.0.38:

- Example calls `FTSession(..., save_session=True)`. The installed
  `__init__` **does not accept `save_session`** — copying the example
  verbatim raises `TypeError`. The installed version always saves
  cookies; use `profile_path=...` to control where, or drop the kwarg
  entirely.

Otherwise the example matches the installed API surface.

## Gotchas / safety notes

- **Debug mode dumps secrets.** `FTSession(debug=True)` logs full
  response bodies including the `ftat` session token. The source
  itself warns: "DO NOT POST YOUR LOGS ONLINE."
- **`mfa_secret` is the TOTP seed**, not a 6-digit code, not a backup
  code. It is the base32 string Firstrade gives you when you scan the
  QR code during 2FA setup (link in the example points at Firstrade's
  2FA help page).
- **All order paths default to `dry_run=True`.** This is the only
  built-in safeguard against accidentally submitting an order. Verify
  `dry_run` is set on every call until you are sure of the flow.
- **No rate limiting / retry logic.** Calls go straight to
  `requests.Session.request`. The package will not back off on 429s.
- **Latent issue, harmless at runtime:** `order.py` annotates a local
  with `response: requests.Response` but does not `import requests`.
  Local variable annotations are not evaluated at runtime in any
  Python version, so this does not error — but it would break if
  anyone changed the annotation to a class-level or signature
  annotation in the future.
- **Active bug: `SymbolQuote` crashes against the live API.**
  `symbols.py:92` does `response.json()["result"]["shares"]`, but the
  current `/public/quote` response has no `shares` key. Constructing
  `SymbolQuote(...)` raises `KeyError: 'shares'` even with a fully
  authenticated session. Workaround: hit `urls.quote(account, symbol)`
  directly with `requests.get` and read the JSON yourself; the
  response carries everything `SymbolQuote` exposes except `shares`.

## Next steps to consider

- Build a small interactive runner that loads credentials from
  `.env` and runs the read-only parts (account list, balances,
  positions, quotes, OHLC, option chain).
- Inspect concrete response shapes for `get_account_balances`,
  `get_positions`, `get_orders` against your account so the JSON
  structure is documented.
- If submitting real orders, wrap `place_order` with an explicit
  confirmation prompt and never default `dry_run` to `False`.
