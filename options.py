#!/usr/bin/env python3
"""Fetch option expirations and chains for a US equity from Firstrade's public API.

Usage:
    options.py SYMBOL                       # list expirations
    options.py SYMBOL YYYYMMDD              # fetch chain for that expiry (ATM ±5 strikes)
    options.py SYMBOL YYYYMMDD --all        # show all strikes
    options.py SYMBOL YYYYMMDD --json       # raw JSON

Date format is YYYYMMDD (no dashes) — matches the underlying API.
"""
import argparse
import json
import sys
from urllib.parse import quote as urlquote

from _client import get_json


def fetch_expirations(symbol: str) -> dict:
    return get_json(f"/public/oc?m=get_exp_dates&root_symbol={urlquote(symbol)}")


def fetch_chain(symbol: str, exp_date: str) -> dict:
    return get_json(
        f"/public/oc?m=get_oc&root_symbol={urlquote(symbol)}"
        f"&exp_date={exp_date}&chains_range=A"
    )


def fetch_underlying_last(symbol: str) -> float | None:
    try:
        data = get_json(f"/public/quote?account=00000000&q={urlquote(symbol)}")
        return data.get("result", {}).get("last")
    except Exception:
        return None


def render_expirations(symbol: str, data: dict) -> str:
    if data.get("error"):
        return f"{symbol}: ERROR — {data['error']}"
    items = data.get("items", [])
    out = [f"{symbol} option expirations ({len(items)} total):"]
    for it in items:
        out.append(
            f"  {it['exp_date']}  {it['day_left']:>4}d  type={it['exp_type']}"
        )
    return "\n".join(out)


def _row(opt: dict) -> str:
    return (
        f"    {opt['strike']:>9.2f}  {opt['bid']:>7.2f}  {opt['ask']:>7.2f}  "
        f"{opt['last']:>7.2f}  {opt['vol']:>8,}  {opt['open_int']:>8,}"
    )


def render_chain(
    symbol: str, exp_date: str, chain: dict, underlying: float | None, show_all: bool
) -> str:
    if chain.get("error"):
        return f"{symbol}: ERROR — {chain['error']}"
    items = chain.get("items", [])
    calls = sorted([i for i in items if i["class"] == "C"], key=lambda i: i["strike"])
    puts = sorted([i for i in items if i["class"] == "P"], key=lambda i: i["strike"])
    total_strikes = len({i["strike"] for i in items})

    note = ""
    if not show_all and underlying:
        all_strikes = sorted({c["strike"] for c in calls} | {p["strike"] for p in puts})
        atm_i = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - underlying))
        keep = set(all_strikes[max(0, atm_i - 5): atm_i + 6])
        calls = [c for c in calls if c["strike"] in keep]
        puts = [p for p in puts if p["strike"] in keep]
        note = " (ATM ±5)"
    elif not show_all and underlying is None:
        note = " (--all forced: no underlying quote available)"

    header = f"    {'strike':>9}  {'bid':>7}  {'ask':>7}  {'last':>7}  {'vol':>8}  {'oi':>8}"
    out = [
        f"{symbol} option chain — expiry {exp_date}",
        f"  Underlying: ${underlying}" if underlying else "  Underlying: n/a",
        f"  Total strikes: {total_strikes}, showing {len(calls)} calls + {len(puts)} puts{note}",
        "",
        "  CALLS:",
        header,
        *(_row(c) for c in calls),
        "",
        "  PUTS:",
        header,
        *(_row(p) for p in puts),
    ]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbol", help="ticker symbol")
    ap.add_argument("exp_date", nargs="?", help="expiration date YYYYMMDD")
    ap.add_argument("--all", action="store_true", help="show all strikes (default: ATM ±5)")
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    args = ap.parse_args(argv)
    sym = args.symbol.upper()

    if not args.exp_date:
        data = fetch_expirations(sym)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(render_expirations(sym, data))
        return 0

    chain = fetch_chain(sym, args.exp_date)
    if args.json:
        print(json.dumps(chain, indent=2))
        return 0
    underlying = fetch_underlying_last(sym)
    print(render_chain(sym, args.exp_date, chain, underlying, args.all))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
