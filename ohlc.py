#!/usr/bin/env python3
"""Fetch OHLC candle data for a US-listed equity from Firstrade's public API.

Usage:
    ohlc.py SYMBOL [RANGE]
    ohlc.py NVDA              # default range: 1d
    ohlc.py NVDA 1y
    ohlc.py NVDA 1m --json    # raw JSON

Valid ranges: 24h, 1d, 1w, 1m, 1y
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from urllib.parse import quote as urlquote

from _client import get_json

RANGES = ["24h", "1d", "1w", "1m", "1y"]


def fetch(symbol: str, range_: str) -> dict:
    data = get_json(f"/public/ohlc?symbol={urlquote(symbol)}&range={range_}&_v=v2")
    if data.get("error"):
        return {"error": data["error"]}
    return data["result"]


def _fmt_ts(ms: int) -> str:
    return (
        datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
    )


def render(symbol: str, range_: str, result: dict) -> str:
    if "error" in result:
        return f"{symbol}: ERROR — {result['error']}"
    ohlc = result.get("ohlc") or []
    if not ohlc:
        return f"{symbol} ({range_}): no candles returned"
    vols = dict(result.get("vol") or [])
    first, last = ohlc[0], ohlc[-1]
    highs = [c[2] for c in ohlc]
    lows = [c[3] for c in ohlc]
    closes = [c[4] for c in ohlc]
    total_vol = sum(vols.values()) if vols else 0
    change = closes[-1] - closes[0]
    pct = (change / closes[0]) * 100 if closes[0] else 0.0
    return "\n".join([
        f"{symbol} OHLC ({range_})",
        f"  Candles: {len(ohlc)}",
        f"  First:   {_fmt_ts(first[0])}   close ${first[4]:.2f}",
        f"  Last:    {_fmt_ts(last[0])}   close ${last[4]:.2f}",
        f"  Range:   ${min(lows):.2f} – ${max(highs):.2f}",
        f"  Change:  {change:+.2f} ({pct:+.2f}%)",
        f"  Volume:  {total_vol:,}",
    ])


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("symbol", help="ticker symbol, e.g. NVDA")
    ap.add_argument("range", nargs="?", default="1d", choices=RANGES)
    ap.add_argument("--json", action="store_true", help="emit raw JSON (full candle list)")
    args = ap.parse_args(argv)
    sym = args.symbol.upper()
    result = fetch(sym, args.range)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(render(sym, args.range, result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
