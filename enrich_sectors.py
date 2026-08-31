"""
Optional: enrich the sector cache for any tickers not in the built-in map.

Runs entirely on your machine. Needs a free Alpha Vantage API key
(https://www.alphavantage.co/support/#api-key) and the `requests` package.

Usage:
    set ALPHAVANTAGE_API_KEY=your_key        (Windows)
    export ALPHAVANTAGE_API_KEY=your_key     (macOS/Linux)
    python enrich_sectors.py

It scans the loaded statement for underlyings classified "Unknown", looks up
each via Alpha Vantage COMPANY_OVERVIEW, maps Alpha Vantage's coarse sector to
a GICS-style label, and writes the result to data/sector_cache.json (which the
dashboard reads first). Free-tier rate limits apply (~25 requests/day), so this
only fetches the Unknowns, not everything.
"""

from __future__ import annotations
import json
import os
import time

import ibkr_analytics as ia
import sectors as sc

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sector_cache.json")

# Alpha Vantage returns coarse sectors; map to GICS-style buckets.
AV_TO_GICS = {
    "TECHNOLOGY": "Technology",
    "LIFE SCIENCES": "Healthcare",
    "FINANCE": "Financials",
    "MANUFACTURING": "Industrials",
    "TRADE & SERVICES": "Consumer Discretionary",
    "ENERGY & TRANSPORTATION": "Energy",
    "REAL ESTATE & CONSTRUCTION": "Real Estate",
}


def main():
    key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not key:
        print("Set ALPHAVANTAGE_API_KEY first (free key at alphavantage.co).")
        return
    import requests

    path = ia.find_latest_statement(os.path.join(os.path.dirname(__file__), "data"))
    if not path:
        print("No statement found in data/.")
        return
    r = ia.analyze(path)
    unders = sorted(r["closed"]["underlying"].unique())
    cache = sc._load_cache()
    unknown = [t for t in unders if sc.sector_for(t, cache) == "Unknown"]
    if not unknown:
        print("No unknown tickers — nothing to enrich.")
        return

    print(f"Enriching {len(unknown)} ticker(s): {unknown}")
    for t in unknown:
        try:
            resp = requests.get("https://www.alphavantage.co/query",
                                params={"function": "COMPANY_OVERVIEW", "symbol": t, "apikey": key},
                                timeout=20)
            data = resp.json()
            av_sector = (data.get("Sector") or "").upper().strip()
            gics = AV_TO_GICS.get(av_sector, av_sector.title() if av_sector else "Unknown")
            if gics and gics != "Unknown":
                cache[t] = gics
                print(f"  {t}: {gics}")
            else:
                print(f"  {t}: no sector returned")
            time.sleep(1)  # be gentle on rate limits
        except Exception as e:  # noqa
            print(f"  {t}: error {e}")

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2)
    print(f"Saved {CACHE_PATH}")


if __name__ == "__main__":
    main()
