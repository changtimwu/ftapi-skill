#!/usr/bin/env python3
"""Account transaction history (dividends, interest, buys, sells, fees) for
Firstrade accounts.

Requires login (uses the cached session from ./login.py). Hits
/private/account_history.

Usage:
    history.py                          # default: last 1 month, all accounts
    history.py 1y                       # range keyword
    history.py 2026-01-01 2026-04-30    # custom range (YYYY-MM-DD, with dashes)
    history.py --account 12345678 ytd   # one account
    history.py --json ytd               # raw JSON

Valid range keywords: today, 1w, 1m, 2m, mtd, ytd, ly
"""
import argparse
import json
import re
import sys
from collections import Counter

from _auth import authed_get, login

VALID_RANGES = ["today", "1w", "1m", "2m", "mtd", "ytd", "ly"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fetch_accounts(headers: dict) -> dict:
    return authed_get("/private/acct_list", headers)


def fetch_history(
    headers: dict, account: str, date_range: str, custom_range: list[str] | None = None
) -> dict:
    if custom_range:
        path = (
            f"/private/account_history?range=cust"
            f"&range_arr[]={custom_range[0]}&range_arr[]={custom_range[1]}"
            f"&page=1&account={account}&per_page=1000"
        )
    else:
        path = (
            f"/private/account_history?range={date_range}"
            f"&page=1&account={account}&per_page=1000"
        )
    return authed_get(path, headers)


def _f(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def render_history(account: str, data: dict, label: str) -> str:
    if data.get("error"):
        return f"{account}: ERROR — {data['error']}"
    items = data.get("items", [])
    if not items:
        return f"Account {account} — {label}: no transactions."

    rows = sorted(items, key=lambda x: x.get("report_date", ""), reverse=True)
    out = [
        f"Account {account} — {label} ({len(rows)} transactions):",
        f"  {'Date':<11} {'Type':<10} {'Symbol':<6} {'Qty':>9} {'Price':>9} {'Amount':>11}  Description",
    ]
    by_type: Counter = Counter()
    type_totals: dict[str, float] = {}
    net = 0.0
    for it in rows:
        amount = _f(it.get("amount"))
        qty = _f(it.get("quantity"))
        price = _f(it.get("trade_price"))
        ttype = it.get("trans_str", "") or "?"
        sym = it.get("symbol", "") or ""
        desc = (it.get("description") or "")[:50]
        by_type[ttype] += 1
        type_totals[ttype] = type_totals.get(ttype, 0.0) + amount
        net += amount
        out.append(
            f"  {it.get('report_date',''):<11} {ttype:<10} {sym:<6} "
            f"{qty:>9,.4f} {price:>9.2f} {amount:>+11,.2f}  {desc}"
        )

    out.append("")
    out.append("  By type:")
    for ttype, count in by_type.most_common():
        out.append(
            f"    {ttype:<10} {count:>3}x   total {type_totals[ttype]:>+11,.2f}"
        )
    out.append(f"  NET cash flow: {net:>+11,.2f}")
    return "\n".join(out)


def _parse_positional(args_list: list[str]) -> tuple[str, list[str] | None, str]:
    """Return (date_range, custom_range, human_label)."""
    if not args_list:
        return "1m", None, "last 1 month"
    if len(args_list) == 1 and args_list[0] in VALID_RANGES:
        return args_list[0], None, f"range={args_list[0]}"
    if len(args_list) == 2 and all(DATE_RE.match(s) for s in args_list):
        return "cust", list(args_list), f"{args_list[0]} to {args_list[1]}"
    raise SystemExit(
        f"Expected one of {VALID_RANGES} or two YYYY-MM-DD dates, got {args_list}"
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "range_or_dates", nargs="*",
        help="range keyword OR two YYYY-MM-DD dates for a custom range",
    )
    ap.add_argument("--account", help="account number (default: all)")
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    args = ap.parse_args(argv)

    date_range, custom_range, label = _parse_positional(args.range_or_dates)

    headers = login()
    accts = fetch_accounts(headers)
    nums = [a["account"] for a in accts.get("items", [])]
    if args.account:
        if args.account not in nums:
            print(f"Account {args.account} not in {nums}", file=sys.stderr)
            return 2
        nums = [args.account]

    results = [
        {"account": n, "history": fetch_history(headers, n, date_range, custom_range)}
        for n in nums
    ]

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    for r in results:
        print(render_history(r["account"], r["history"], label))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
