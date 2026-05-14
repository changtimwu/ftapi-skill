#!/usr/bin/env python3
"""Fetch US equity quotes from Firstrade's public mobile-app API.

No login or credentials required. Quotes are delayed (~15 min), not real-time.

Usage:
    quote.py SYMBOL [SYMBOL ...]
    quote.py --json AAPL NVDA      # machine-readable output
"""
import argparse
import json
import sys
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote as urlquote

from _client import get_json


def fetch(symbol: str) -> dict:
    try:
        data = get_json(f"/public/quote?account=00000000&q={urlquote(symbol)}")
    except urllib.error.HTTPError as e:
        return {"_symbol": symbol, "error": f"HTTP {e.code}: {e.reason}"}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"_symbol": symbol, "error": f"network: {e}"}
    if data.get("error"):
        return {"_symbol": symbol, "error": data["error"]}
    result = data.get("result")
    if not result:
        return {"_symbol": symbol, "error": "no result field in response"}
    result["_symbol"] = symbol
    return result


def render(q: dict) -> str:
    sym = q.get("symbol") or q["_symbol"]
    if q.get("error"):
        return f"{sym}: ERROR — {q['error']}"
    try:
        return "\n".join([
            f"{sym} — {q['company_name']} ({q['exchange']})",
            f"  Last:   ${q['last']}   ({q['change']:+.2f}, "
            f"{q['change_percent']:+.2f}%, {q['change_color']})",
            f"  Prev close: ${q['prev_close']}",
            f"  Bid:    ${q['bid']} x {q['bid_size']}  [{q['bid_mmid']}]",
            f"  Ask:    ${q['ask']} x {q['ask_size']}  [{q['ask_mmid']}]",
            f"  Day:    low ${q['low']}  high ${q['high']}",
            f"  Volume: {q['vol']:,}",
            f"  Quote time:      {q['quote_time']}",
            f"  Last trade time: {q['last_trade_time']}",
            f"  Realtime:        {q['realtime']}",
        ])
    except KeyError as e:
        return f"{sym}: schema drift, missing {e}; raw={json.dumps(q)[:400]}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbols", nargs="+", help="ticker symbol(s), e.g. AAPL NVDA")
    ap.add_argument("--json", action="store_true", help="emit JSON array")
    args = ap.parse_args(argv)

    syms = [s.upper() for s in args.symbols]
    with ThreadPoolExecutor(max_workers=min(8, len(syms))) as ex:
        results = list(ex.map(fetch, syms))

    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    for r in results:
        print(render(r))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
