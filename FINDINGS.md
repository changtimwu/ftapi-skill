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

## Session model: `ftat` is durable, `sid` is per-login

Confirmed empirically. `/sess/verify_pin` returns both `ftat` and `sid`. The
`ftat` is the long-lived bearer (Firstrade calls it the "remember me" token,
TTL ~30 days when `remember_for=30`). The `sid` is **per-login** — Firstrade
maintains one active session per account across all clients (mobile app, web,
CLI). Any new login on any device invalidates the prior `sid` everywhere.

Implication: caching `sid` across processes doesn't work. Cache only `ftat`
and on each invocation re-POST `/sess/login` with the cached `ftat` in the
header plus `username`+`password` in the body. The response then carries a
fresh `ftat` (possibly rotated) and a fresh `sid`, no MFA step needed. This
is exactly what `firstrade.account.FTSession.login()` does — even with a
saved cookie, it still hits `/sess/login` every call.

Observed failure mode if you ignore this: first `/private/*` call after a
process restart returns
`HTTP 401 {"error":"Unauthorized","message":"Blank or invalid session"}`,
because the cached `sid` was invalidated by some intervening login (yours or
the API server's idle expiry).

Position-item field names (from `/private/positions`, undocumented):

| Field | Meaning |
| --- | --- |
| `quantity` | shares held |
| `unit_cost` | avg cost per share (cost basis ÷ qty) |
| `cost` | total cost basis |
| `last` | last trade price |
| `change` | per-share intraday change |
| `change_percent` | intraday % |
| `day_change` | **position-level** intraday $ P/L |
| `market_value` | qty × last |
| `gainloss` / `gainloss_percent` | total realized+unrealized P/L vs cost basis |
| `adj_cost` / `adj_gainloss` | adjusted for splits/dividends |
| `52w_high` / `52w_low`, `eps`, `pe`, `beta`, `div_share`, `yield`, … | bonus quote-like fields included with each position |

## Order placement: dry-run vs real, and market-side price-band rejects

Confirmed empirically (BUY 1 INTC LIMIT $0.01 DAY against `/private/stock_order`).

### Request payload (form-encoded POST)

| Field | Value | Notes |
| --- | --- | --- |
| `symbol` | `INTC` | ticker |
| `transaction` | `B` | BUY (`S` = SELL, `SS` = SELL_SHORT, `BC` = BUY_TO_COVER, `BO` = BUY_OPTION, `SO` = SELL_OPTION) |
| `shares` | `1` | omit and send `dollar_amount` for notional orders |
| `duration` | `0` | DAY (`D` = DAY_EXT, `N` = OVERNIGHT, `1` = GT90) |
| `instructions` | `0` | NONE (`1` = AON, `4` = OPG, `5` = CLO) |
| `price_type` | `2` | LIMIT (`1` = MARKET, `3` = STOP, `4` = STOP_LIMIT, `5` = TS$, `6` = TS%) |
| `limit_price` | `0.01` | required for LIMIT/STOP_LIMIT |
| `account` | `88218207` | |
| `preview` | `true` / `false` | see below |
| `stage` | `P` | **only on the real-placement call**, not on previews |

### Two-stage call pattern

- **Dry run / preview:** `preview=true` (no `stage`). Returns a `result` block with
  validated order details and a current quote (`bid`, `ask`, `last`, sizes, MMIDs,
  `realtime: T`). **No order touches the book; no order_id is generated.** This is
  also how the upstream `firstrade` package's default `dry_run=True` works.
- **Real placement:** `preview=false` + `stage=P`. Returns `result.order_id` and
  initial `state: "ORDER-REQUESTED"`. The order is now in Firstrade's order
  management system and will be routed to the market.

### Order state lifecycle (observed)

- `ORDER-REQUESTED` — submitted to Firstrade, awaiting routing
- `ORDER-REJECTED` — terminal; market rejected it (see below). `cancelable: false`
- (other states presumably: open/working, partially filled, filled, canceled — not yet observed)

### Market-side price-band rejection ("Reference code: 1500")

A BUY at $0.01 on INTC (ask ~$107) was **rejected by the exchange**, not by
Firstrade, with:

> "This order was rejected by market due to either excessive price or other
> reasons, please contact Firstrade for assistance. **Reference code: 1500**"

Implication: SEC LULD (limit-up/limit-down) bands and exchange clearly-erroneous-
order protections will reject obvious fat-finger prices before they ever reach
the book. To get a resting unmatched order (e.g. to exercise `cancel_order`),
use a limit that is below market but still inside the daily LULD band — for
INTC at $107, somewhere like $50–80 would rest; $0.01 will not.

`reject_msg` carries the human-readable text and `Reference code: 1500` appears
to be Firstrade's label for market-side excessive-price rejects specifically.

### Bonus finding: authenticated quotes are real-time

`/public/quote` returns `realtime: F` (delayed). The same quote data embedded
in an authenticated order preview (`/private/stock_order` with `preview=true`)
returns `realtime: T` and live prices. Suggests Firstrade's real-time data
entitlement is tied to a logged-in session, not the `access-token` alone.

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
