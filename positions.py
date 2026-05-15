#!/usr/bin/env python3
"""List currently held positions for Firstrade account(s).

Unlike quote.py/ohlc.py/options.py, this hits /private/* endpoints and
requires login. Credentials come from environment variables (or a .env
file in this directory):

    FIRSTRADE_USERNAME, FIRSTRADE_PASSWORD, FIRSTRADE_MFA_SECRET

The session token is cached at ~/.config/firstrade-skill/ so repeat runs
skip the login round-trip. Cookie cache lasts ~30 days per Firstrade.

Usage:
    positions.py                       # all accounts
    positions.py <ACCOUNT>             # one account
    positions.py --list-accounts       # just balances, no positions
    positions.py --json                # raw JSON
"""
import argparse
import json
import sys

from _auth import authed_get, login


def fetch_accounts(headers: dict) -> dict:
    return authed_get("/private/acct_list", headers)


def fetch_positions(headers: dict, account: str) -> dict:
    return authed_get(f"/private/positions?account={account}&per_page=200", headers)


def _f(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def render_accounts(data: dict) -> str:
    items = data.get("items", [])
    out = [f"Accounts ({len(items)} total):"]
    for it in items:
        out.append(
            f"  {it.get('account', '?'):<12}  total ${_f(it.get('total_value')):>14,.2f}"
        )
    return "\n".join(out)


def render_positions(account: str, data: dict) -> str:
    if data.get("error"):
        return f"{account}: ERROR — {data['error']}"
    items = data.get("items", [])
    if not items:
        return f"{account}: no positions held."

    rows = sorted(items, key=lambda p: -_f(p.get("market_value")))
    total_mv = sum(_f(p.get("market_value")) for p in rows)
    total_day = sum(_f(p.get("day_change")) for p in rows)
    total_cost = sum(_f(p.get("cost")) for p in rows)
    total_pl = sum(_f(p.get("gainloss")) for p in rows)
    overall_pct = (total_pl / total_cost * 100) if total_cost else 0.0

    header = (
        f"  {'Symbol':<8} {'Qty':>10} {'Avg Cost':>10} {'Last':>10} "
        f"{'Mkt Value':>14} {'Day Δ':>10} {'Total P/L':>12} {'Total %':>8}"
    )
    out = [f"Positions in {account} ({len(items)} symbols):", header]
    for p in rows:
        out.append(_fmt_position(p))
    out.append(
        f"  {'TOTAL':<8} {'':>10} {'':>10} {'':>10} "
        f"{total_mv:>14,.2f} {total_day:>+10,.2f} {total_pl:>+12,.2f} {overall_pct:>+7.2f}%"
    )
    return "\n".join(out)


def _fmt_position(p: dict) -> str:
    sym = p.get("symbol", "?")
    qty = _f(p.get("quantity"))
    avg = _f(p.get("unit_cost"))
    last = _f(p.get("last"))
    mv = _f(p.get("market_value"))
    day = _f(p.get("day_change"))
    pl = _f(p.get("gainloss"))
    plpct = _f(p.get("gainloss_percent"))
    return (
        f"  {sym:<8} {qty:>10,.4f} {avg:>10.2f} {last:>10.2f} "
        f"{mv:>14,.2f} {day:>+10,.2f} {pl:>+12,.2f} {plpct:>+7.2f}%"
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("account", nargs="?", help="account number (default: all)")
    ap.add_argument(
        "--list-accounts", action="store_true", help="show account numbers + balances and exit"
    )
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    args = ap.parse_args(argv)

    headers = login()
    accts = fetch_accounts(headers)
    nums = [a["account"] for a in accts.get("items", [])]

    if args.list_accounts:
        if args.json:
            print(json.dumps(accts, indent=2))
        else:
            print(render_accounts(accts))
        return 0

    if args.account:
        if args.account not in nums:
            print(f"Account {args.account} not in {nums}", file=sys.stderr)
            return 2
        nums = [args.account]

    results = [{"account": n, "positions": fetch_positions(headers, n)} for n in nums]

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    if not args.account:
        print(render_accounts(accts))
        print()
    for r in results:
        print(render_positions(r["account"], r["positions"]))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
