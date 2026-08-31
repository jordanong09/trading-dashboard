"""
Sector / industry classification for traded underlyings.

Primary source is a curated GICS-style map (offline, instant, reliable).
A JSON override cache (data/sector_cache.json) is consulted first, so any
ticker enriched via Alpha Vantage (see enrich_sectors.py) or hand-edited
wins over the built-in map. Unknown tickers fall back to "Unknown" and are
surfaced in the dashboard so you can add them.
"""

from __future__ import annotations
import json
import os

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sector_cache.json")

# GICS-style sectors. ETFs/index products grouped separately.
SECTOR_MAP: dict[str, str] = {
    # Technology
    "AAPL": "Technology", "ADBE": "Technology", "AMD": "Technology", "APH": "Technology",
    "CRM": "Technology", "CRWD": "Technology", "CRWV": "Technology", "DELL": "Technology",
    "INTC": "Technology", "MCHP": "Technology", "MRVL": "Technology", "MSFT": "Technology",
    "MU": "Technology", "NOW": "Technology", "NVDA": "Technology", "ORCL": "Technology",
    "PLTR": "Technology", "TWLO": "Technology", "WDC": "Technology", "ZETA": "Technology",
    "TTD": "Technology", "MSTR": "Technology", "APP": "Technology",
    # Communication Services
    "GOOGL": "Communication Services", "META": "Communication Services",
    "NFLX": "Communication Services", "DIS": "Communication Services",
    "RBLX": "Communication Services", "RDDT": "Communication Services",
    "BIDU": "Communication Services", "SE": "Communication Services",
    "ASTS": "Communication Services",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "BABA": "Consumer Discretionary", "JD": "Consumer Discretionary",
    "PDD": "Consumer Discretionary", "NKE": "Consumer Discretionary",
    "LOW": "Consumer Discretionary", "MCD": "Consumer Discretionary",
    "CCL": "Consumer Discretionary", "EXPE": "Consumer Discretionary",
    "DKNG": "Consumer Discretionary", "PTON": "Consumer Discretionary",
    "FLUT": "Consumer Discretionary", "EBAY": "Consumer Discretionary",
    "NIO": "Consumer Discretionary",
    # Consumer Staples
    "PEP": "Consumer Staples", "CHD": "Consumer Staples", "UL": "Consumer Staples",
    "CELH": "Consumer Staples",
    # Financials
    "JPM": "Financials", "C": "Financials", "ALLY": "Financials", "V": "Financials",
    "PYPL": "Financials", "HOOD": "Financials", "COIN": "Financials", "MET": "Financials",
    "AFRM": "Financials", "XYZ": "Financials", "CRCL": "Financials", "MARA": "Financials",
    "RIOT": "Financials", "UPST": "Financials",
    # Healthcare
    "UNH": "Healthcare", "JNJ": "Healthcare", "NVO": "Healthcare",
    # Industrials
    "BA": "Industrials", "GE": "Industrials", "UPS": "Industrials", "DAL": "Industrials",
    "UAL": "Industrials", "AAL": "Industrials", "RKLB": "Industrials",
    # Utilities
    "OKLO": "Utilities",
    # ETF / Index
    "SPY": "ETF / Index", "QQQ": "ETF / Index", "IWM": "ETF / Index", "ARKK": "ETF / Index",
    "KWEB": "ETF / Index", "GLD": "ETF / Index", "IGV": "ETF / Index", "VOO": "ETF / Index",
}


def _load_cache() -> dict:
    try:
        with open(_CACHE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def sector_for(ticker: str, cache: dict | None = None) -> str:
    if cache is None:
        cache = _load_cache()
    t = ticker.upper()
    if t in cache and cache[t]:
        return cache[t]
    return SECTOR_MAP.get(t, "Unknown")


def sectors_for(tickers) -> dict:
    """Return {ticker: sector} for an iterable of tickers (cache-aware)."""
    cache = _load_cache()
    return {t: sector_for(t, cache) for t in tickers}
