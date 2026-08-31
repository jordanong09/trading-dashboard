"""
IBKR Activity Statement analytics engine.

Reusable, statement-agnostic parser + analytics for Interactive Brokers
year-to-date Activity Statements exported as CSV.

Drop a new statement into the data/ folder and everything downstream
(the Streamlit dashboard) recomputes automatically.

All trading P&L is reported in the instrument currency (USD for this account).
Account-level NAV / time-weighted return are in the account base currency (SGD).
"""

from __future__ import annotations

import csv
import re
import glob
import os
from datetime import datetime

import numpy as np
import pandas as pd

try:
    import sectors as _sectors
except ImportError:
    _sectors = None

# --------------------------------------------------------------------------- #
# 1. Low-level statement reader
# --------------------------------------------------------------------------- #

def read_sections(path: str) -> dict[str, list[dict]]:
    """Parse a multi-section IBKR activity statement CSV.

    Each logical section (e.g. 'Trades') has one or more 'Header' rows
    followed by 'Data' rows. A section can restate its header partway
    through (IBKR does this for Trades when the asset category changes).
    We always zip a Data row against the most recent Header for its section.

    Returns {section_name: [ {col: value, ...}, ... ]}.
    """
    sections: dict[str, list[dict]] = {}
    current_header: dict[str, list[str]] = {}

    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            section, rtype = row[0], row[1]
            if rtype == "Header":
                current_header[section] = row[2:]
            elif rtype == "Data":
                header = current_header.get(section)
                if not header:
                    continue
                values = row[2:]
                # pad/truncate to header length
                if len(values) < len(header):
                    values = values + [""] * (len(header) - len(values))
                rec = dict(zip(header, values[: len(header)]))
                sections.setdefault(section, []).append(rec)
    return sections


def _to_num(series: pd.Series) -> pd.Series:
    """Convert IBKR numeric strings ('1,500', '-22259.59', '') to float."""
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).replace({"": np.nan, "nan": np.nan}),
        errors="coerce",
    )


# --------------------------------------------------------------------------- #
# 2. Option symbol parsing
# --------------------------------------------------------------------------- #

_OPT_RE = re.compile(
    r"^(?P<under>\S+)\s+(?P<exp>\d{2}[A-Z]{3}\d{2})\s+(?P<strike>[\d.]+)\s+(?P<right>[CP])$"
)


def parse_option_symbol(symbol: str):
    """'AAPL 08MAY26 285 C' -> (underlying, expiry_date, strike, right)."""
    m = _OPT_RE.match(symbol.strip())
    if not m:
        return symbol, pd.NaT, np.nan, ""
    under = m.group("under")
    try:
        exp = datetime.strptime(m.group("exp"), "%d%b%y")
    except ValueError:
        exp = pd.NaT
    return under, exp, float(m.group("strike")), m.group("right")


# --------------------------------------------------------------------------- #
# 3. Trades
# --------------------------------------------------------------------------- #

def get_trades(sections: dict) -> pd.DataFrame:
    """Clean, typed DataFrame of executed orders (one row per fill/order)."""
    rows = sections.get("Trades", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # keep only actual order executions (drop SubTotal/Total rows which have blank discriminator)
    df = df[df.get("DataDiscriminator") == "Order"].copy()
    if df.empty:
        return df

    df["datetime"] = pd.to_datetime(df["Date/Time"], format="%Y-%m-%d, %H:%M:%S", errors="coerce")
    df["date"] = df["datetime"].dt.normalize()
    df["qty"] = _to_num(df["Quantity"])
    df["price"] = _to_num(df["T. Price"])
    df["proceeds"] = _to_num(df["Proceeds"])
    df["comm"] = _to_num(df["Comm/Fee"])
    df["basis"] = _to_num(df["Basis"])
    df["realized_pl"] = _to_num(df["Realized P/L"])
    df["code"] = df["Code"].fillna("")

    df["is_option"] = df["Asset Category"] == "Equity and Index Options"
    df["asset_type"] = np.where(df["is_option"], "Options", "Stocks")

    opt = df["Symbol"].where(df["is_option"]).apply(
        lambda s: parse_option_symbol(s) if isinstance(s, str) else (s, pd.NaT, np.nan, "")
    )
    df["underlying"] = np.where(df["is_option"], [o[0] for o in opt], df["Symbol"])
    df["opt_expiry"] = [o[1] if isinstance(o, tuple) else pd.NaT for o in opt]
    df["opt_strike"] = [o[2] if isinstance(o, tuple) else np.nan for o in opt]
    df["opt_right"] = [o[3] if isinstance(o, tuple) else "" for o in opt]

    # code flags
    codes = df["code"].str.split(";")
    df["is_open"] = codes.apply(lambda c: "O" in c)
    df["is_close"] = codes.apply(lambda c: "C" in c)
    df["is_expired"] = codes.apply(lambda c: "Ep" in c)
    df["is_exercise"] = codes.apply(lambda c: "Ex" in c)
    df["is_assignment"] = codes.apply(lambda c: "A" in c)

    df["multiplier"] = np.where(df["is_option"], 100, 1)
    return df.sort_values("datetime").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 4. FIFO round-trip matching  ->  closed trades with holding period
# --------------------------------------------------------------------------- #

def match_round_trips(trades: pd.DataFrame) -> pd.DataFrame:
    """Build one closed-trade record per CLOSING execution.

    P&L is taken directly from IBKR's authoritative 'Realized P/L' column
    (true tax-lot cost basis, incl. positions carried over from a prior year),
    so totals reconcile exactly to the statement.

    FIFO matching against in-period opening executions is used only to recover
    the entry date / holding period. Opening vs closing is decided by IBKR's
    action codes (O = opening, C = closing), not by inferring position sign.

    Fields:
      matched_frac  fraction of the closing qty matched to an in-period open
      holding_days  qty-weighted holding period over the matched portion
                    (NaN when the position was opened before this statement)
      carryover     True when part of the closing qty had no in-period open
    """
    closed = []
    if trades.empty:
        return pd.DataFrame()

    for symbol, g in trades.groupby("Symbol", sort=False):
        g = g.sort_values("datetime")
        lots: list[dict] = []  # FIFO open lots: {date, remaining, price}
        for _, t in g.iterrows():
            qty = abs(t["qty"])
            if qty == 0 or pd.isna(qty):
                continue

            if t["is_open"] and not t["is_close"]:
                # opening execution -> add a lot
                lots.append({"date": t["date"], "remaining": qty, "price": t["price"]})
                continue

            if not t["is_close"]:
                continue  # neither open nor close (shouldn't happen)

            # closing execution -> match FIFO lots for holding period only
            remaining = qty
            matched_qty = 0.0
            weighted_days = 0.0
            entry_prices = []
            first_entry = pd.NaT
            while remaining > 1e-9 and lots:
                lot = lots[0]
                m = min(remaining, lot["remaining"])
                days = (t["date"] - lot["date"]).days
                weighted_days += days * m
                matched_qty += m
                entry_prices.append((lot["price"], m))
                if pd.isna(first_entry):
                    first_entry = lot["date"]
                lot["remaining"] -= m
                remaining -= m
                if lot["remaining"] < 1e-9:
                    lots.pop(0)

            matched_frac = matched_qty / qty if qty else 0.0
            hold_days = (weighted_days / matched_qty) if matched_qty > 1e-9 else np.nan
            entry_px = (
                sum(p * q for p, q in entry_prices) / matched_qty
                if matched_qty > 1e-9 else np.nan
            )
            pnl = t["realized_pl"]
            notional = t["multiplier"] * abs(t["proceeds"]) / t["multiplier"] if t["proceeds"] else np.nan
            notional = abs(t["proceeds"]) if t["proceeds"] else np.nan
            ret_pct = (pnl / notional * 100) if notional and not pd.isna(notional) else np.nan

            closed.append({
                "symbol": symbol,
                "underlying": t["underlying"],
                "asset_type": t["asset_type"],
                "is_option": t["is_option"],
                "opt_right": t["opt_right"],
                "entry_date": first_entry,
                "exit_date": t["date"],
                "holding_days": hold_days,
                "matched_frac": matched_frac,
                "carryover": matched_frac < 0.999,
                "qty": qty,
                "entry_price": entry_px,
                "exit_price": t["price"],
                "pnl": pnl,
                "notional": notional,
                "return_pct": ret_pct,
                "exit_code": t["code"],
                "closed_by_exercise": t["is_exercise"],
                "closed_by_expiry": t["is_expired"],
                "closed_by_assignment": t["is_assignment"],
            })

    return pd.DataFrame(closed)


# --------------------------------------------------------------------------- #
# 5. Other sections
# --------------------------------------------------------------------------- #

def get_open_positions(sections: dict) -> pd.DataFrame:
    rows = sections.get("Open Positions", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[df.get("DataDiscriminator") == "Summary"].copy()
    for c in ["Quantity", "Mult", "Cost Price", "Cost Basis", "Close Price", "Value", "Unrealized P/L"]:
        if c in df:
            df[c] = _to_num(df[c])
    df["is_option"] = df["Asset Category"] == "Equity and Index Options"
    df["asset_type"] = np.where(df["is_option"], "Options", "Stocks")
    return df.reset_index(drop=True)


def get_perf_summary(sections: dict) -> pd.DataFrame:
    rows = sections.get("Realized & Unrealized Performance Summary", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[df["Symbol"].notna() & (df["Symbol"] != "")].copy()
    numcols = [c for c in df.columns if c not in ("Asset Category", "Symbol", "Code")]
    for c in numcols:
        df[c] = _to_num(df[c])
    # drop total/subtotal aggregate rows (they have blank asset category or 'Total' symbol)
    df = df[df["Asset Category"].isin(["Stocks", "Equity and Index Options"])]
    return df.reset_index(drop=True)


def _sum_section(sections: dict, name: str, amount_col: str = "Amount") -> pd.DataFrame:
    rows = sections.get(name, [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if amount_col in df:
        df[amount_col] = _to_num(df[amount_col])
    return df


def get_income(sections: dict) -> dict:
    """Dividends, withholding tax, interest, fees, deposits/withdrawals totals."""
    out = {}

    def total(name, col="Amount", exclude_total=True):
        df = _sum_section(sections, name, col)
        if df.empty or col not in df:
            return 0.0, df
        d = df.copy()
        if exclude_total and "Currency" in d:
            d = d[~d["Currency"].astype(str).str.contains("Total", case=False, na=False)]
        # drop rows that are subtotal markers
        if "Date" in d:
            d = d[d["Date"].astype(str).str.len() > 0]
        return float(d[col].sum(skipna=True)), df

    out["dividends"], out["dividends_df"] = total("Dividends")
    out["withholding"], out["withholding_df"] = total("Withholding Tax")
    out["interest"], out["interest_df"] = total("Interest")
    out["fees"], out["fees_df"] = total("Fees")
    return out


def get_account_info(sections: dict) -> dict:
    info = {r["Field Name"]: r["Field Value"] for r in sections.get("Account Information", []) if "Field Name" in r}
    stmt = {r["Field Name"]: r["Field Value"] for r in sections.get("Statement", []) if "Field Name" in r}
    info.update({f"stmt_{k}": v for k, v in stmt.items()})
    # NAV / TWR
    nav = sections.get("Net Asset Value", [])
    nav_change = {r.get("Field Name"): r.get("Field Value") for r in sections.get("Change in NAV", [])}
    info["nav_start"] = _num(nav_change.get("Starting Value"))
    info["nav_end"] = _num(nav_change.get("Ending Value"))
    # TWR appears as a standalone Data row after a 'Time Weighted Rate of Return' header
    twr = None
    for r in nav:
        for v in r.values():
            if isinstance(v, str) and v.strip().endswith("%"):
                twr = v.strip()
    info["twr"] = twr
    return info


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return np.nan


# --------------------------------------------------------------------------- #
# 6. Analytics
# --------------------------------------------------------------------------- #

def classify_holding(days: float) -> str:
    if pd.isna(days):
        return "Unknown"
    if days <= 0:
        return "Intraday (day trade)"
    if days <= 5:
        return "Short swing (1-5d)"
    if days <= 20:
        return "Swing (6-20d)"
    return "Position (>20d)"


def kpi_block(closed: pd.DataFrame, open_pos: pd.DataFrame, income: dict) -> dict:
    realized = closed["pnl"].sum() if not closed.empty else 0.0
    unreal = open_pos["Unrealized P/L"].sum() if not open_pos.empty else 0.0
    wins = closed[closed["pnl"] > 0] if not closed.empty else closed
    losses = closed[closed["pnl"] < 0] if not closed.empty else closed
    n = len(closed)
    gross_win = wins["pnl"].sum() if len(wins) else 0.0
    gross_loss = losses["pnl"].sum() if len(losses) else 0.0
    return {
        "realized_pnl": realized,
        "unrealized_pnl": unreal,
        "total_trading_pnl": realized + unreal,
        "dividends": income.get("dividends", 0.0),
        "withholding": income.get("withholding", 0.0),
        "interest": income.get("interest", 0.0),
        "fees": income.get("fees", 0.0),
        "n_trades": n,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": (len(wins) / n * 100) if n else 0.0,
        "avg_win": wins["pnl"].mean() if len(wins) else 0.0,
        "avg_loss": losses["pnl"].mean() if len(losses) else 0.0,
        "largest_win": closed["pnl"].max() if n else 0.0,
        "largest_loss": closed["pnl"].min() if n else 0.0,
        "profit_factor": (gross_win / abs(gross_loss)) if gross_loss else np.inf,
        "expectancy": closed["pnl"].mean() if n else 0.0,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "avg_hold_days": closed["holding_days"].dropna().mean() if n else 0.0,
        "n_carryover": int(closed["carryover"].sum()) if n else 0,
        "n_matched": int((~closed["carryover"]).sum()) if n else 0,
    }


def monthly_pnl(closed: pd.DataFrame) -> pd.DataFrame:
    if closed.empty:
        return pd.DataFrame(columns=["month", "pnl"])
    m = closed.copy()
    m["month"] = m["exit_date"].dt.to_period("M").dt.to_timestamp()
    out = m.groupby("month", as_index=False)["pnl"].sum()
    out["cumulative"] = out["pnl"].cumsum()
    return out


def by_asset(closed: pd.DataFrame) -> pd.DataFrame:
    if closed.empty:
        return pd.DataFrame()
    g = closed.groupby("asset_type")
    out = g.agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl=("pnl", "mean"),
        avg_hold=("holding_days", "mean"),
    ).reset_index()
    return out


def by_symbol(closed: pd.DataFrame, level: str = "underlying") -> pd.DataFrame:
    if closed.empty:
        return pd.DataFrame()
    g = closed.groupby(level)
    out = g.agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
        avg_hold=("holding_days", "mean"),
    ).reset_index().sort_values("pnl", ascending=False)
    return out


def by_holding_bucket(closed: pd.DataFrame) -> pd.DataFrame:
    if closed.empty:
        return pd.DataFrame()
    c = closed.copy()
    c = c[c["holding_days"].notna()]  # only trades opened & closed within the period
    if c.empty:
        return pd.DataFrame()
    c["bucket"] = c["holding_days"].apply(classify_holding)
    order = ["Intraday (day trade)", "Short swing (1-5d)", "Swing (6-20d)", "Position (>20d)"]
    out = c.groupby("bucket").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl=("pnl", "mean"),
    ).reindex(order).dropna(how="all").reset_index()
    return out


def by_sector(closed: pd.DataFrame) -> pd.DataFrame:
    if closed.empty or "sector" not in closed:
        return pd.DataFrame()
    g = closed.groupby("sector")
    out = g.agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl=("pnl", "mean"),
        avg_hold=("holding_days", "mean"),
    ).reset_index().sort_values("pnl", ascending=False)
    return out


def strengths_weaknesses(closed: pd.DataFrame) -> dict:
    """Rank sectors and holding windows into strengths vs weaknesses."""
    out = {"strength_sectors": pd.DataFrame(), "weak_sectors": pd.DataFrame()}
    bs = by_sector(closed)
    if not bs.empty:
        material = bs[bs["trades"] >= 2]
        out["strength_sectors"] = material[material["pnl"] > 0].head(4)
        out["weak_sectors"] = material[material["pnl"] < 0].sort_values("pnl").head(4)
    return out


def day_of_week(closed: pd.DataFrame, which: str = "entry") -> pd.DataFrame:
    """P&L and win rate by day of week of entry (or exit)."""
    if closed.empty:
        return pd.DataFrame()
    col = "entry_date" if which == "entry" else "exit_date"
    c = closed[closed[col].notna()].copy()
    if c.empty:
        return pd.DataFrame()
    c["dow"] = c[col].dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    out = c.groupby("dow").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
    ).reindex(order).dropna(how="all").reset_index()
    return out


def build_journal(closed: pd.DataFrame) -> pd.DataFrame:
    """Chronological trade journal: entry date -> exit date -> profit."""
    if closed.empty:
        return pd.DataFrame()
    j = closed.copy()
    j = j.sort_values("exit_date", ascending=False)
    j["result"] = np.where(j["pnl"] > 0, "Win", np.where(j["pnl"] < 0, "Loss", "Flat"))
    cols = ["exit_date", "entry_date", "symbol", "sector", "asset_type", "side_note",
            "qty", "entry_price", "exit_price", "holding_days", "pnl", "return_pct",
            "result", "exit_code"]
    j["side_note"] = np.where(j["carryover"], "carried from prior yr", "")
    return j[[c for c in cols if c in j.columns]]


# --- Review / weekly workflow helpers ------------------------------------- #

def list_periods(closed: pd.DataFrame) -> dict:
    """Available months and ISO weeks (by exit date), newest first, for filters."""
    out = {"months": [], "weeks": []}
    if closed.empty:
        return out
    c = closed[closed["exit_date"].notna()].copy()
    if c.empty:
        return out
    months = sorted(c["exit_date"].dt.to_period("M").unique(), reverse=True)
    out["months"] = [str(m) for m in months]  # e.g. "2026-08"
    # weeks: label -> (start, end)
    wk = c["exit_date"].dt.to_period("W-SUN")
    weeks = sorted(wk.unique(), reverse=True)
    out["weeks"] = [
        {"label": f"{w.start_time:%b %d} – {w.end_time:%b %d, %Y}",
         "start": w.start_time.normalize(), "end": w.end_time.normalize()}
        for w in weeks
    ]
    return out


def filter_period(closed: pd.DataFrame, mode: str, value=None) -> pd.DataFrame:
    """Filter closed trades by exit date. mode: 'all' | 'month' | 'week' | 'last30'."""
    if closed.empty or mode == "all":
        return closed
    c = closed[closed["exit_date"].notna()].copy()
    if mode == "month" and value:
        return c[c["exit_date"].dt.to_period("M").astype(str) == value]
    if mode == "last30":
        cutoff = c["exit_date"].max() - pd.Timedelta(days=30)
        return c[c["exit_date"] >= cutoff]
    if mode == "week" and value is not None:
        start, end = value
        return c[(c["exit_date"] >= start) & (c["exit_date"] <= end)]
    return c


def top_bottom_by_ticker(df: pd.DataFrame, n: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Top-n winning and bottom-n losing UNDERLYINGS by net P&L in df."""
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    g = df.groupby("underlying").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
    ).reset_index().sort_values("pnl", ascending=False)
    winners = g[g["pnl"] > 0].head(n)
    losers = g[g["pnl"] < 0].sort_values("pnl").head(n)
    return winners, losers


def repeat_offenders(closed: pd.DataFrame, min_trades: int = 2) -> pd.DataFrame:
    """Underlyings traded >= min_trades that are net negative — the 'avoid' list."""
    if closed.empty:
        return pd.DataFrame()
    g = closed.groupby("underlying").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        wins=("pnl", lambda x: int((x > 0).sum())),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl=("pnl", "mean"),
        last_traded=("exit_date", "max"),
        sector=("sector", "first") if "sector" in closed else ("underlying", "first"),
    ).reset_index()
    off = g[(g["trades"] >= min_trades) & (g["pnl"] < 0)].sort_values("pnl")
    return off


def reliable_performers(closed: pd.DataFrame, min_trades: int = 2) -> pd.DataFrame:
    """Underlyings traded >= min_trades that are net positive — the 'keep' list."""
    if closed.empty:
        return pd.DataFrame()
    g = closed.groupby("underlying").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl=("pnl", "mean"),
        last_traded=("exit_date", "max"),
        sector=("sector", "first") if "sector" in closed else ("underlying", "first"),
    ).reset_index()
    keep = g[(g["trades"] >= min_trades) & (g["pnl"] > 0)].sort_values("pnl", ascending=False)
    return keep


def option_events(trades: pd.DataFrame) -> pd.DataFrame:
    """Exercise / assignment / expiry events on options."""
    if trades.empty:
        return pd.DataFrame()
    ev = trades[trades["is_exercise"] | trades["is_assignment"] | trades["is_expired"]].copy()
    if ev.empty:
        return ev
    ev["event"] = np.select(
        [ev["is_exercise"], ev["is_assignment"], ev["is_expired"]],
        ["Exercise", "Assignment", "Expired"],
        default="",
    )
    return ev[[
        "date", "Symbol", "underlying", "asset_type", "opt_right", "opt_strike",
        "qty", "price", "realized_pl", "code", "event",
    ]].sort_values("date")


def mtd_pnl(closed: pd.DataFrame) -> float:
    if closed.empty:
        return 0.0
    last = closed["exit_date"].max()
    if pd.isna(last):
        return 0.0
    m = closed[(closed["exit_date"].dt.year == last.year) & (closed["exit_date"].dt.month == last.month)]
    return m["pnl"].sum()


def option_call_put(closed: pd.DataFrame) -> pd.DataFrame:
    if closed.empty:
        return pd.DataFrame()
    o = closed[closed["is_option"]].copy()
    if o.empty:
        return pd.DataFrame()
    o["right"] = o["opt_right"].map({"C": "Calls", "P": "Puts"}).fillna("Other")
    return o.groupby("right").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100),
    ).reset_index()


def best_worst_trades(closed: pd.DataFrame, n: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    if closed.empty:
        return pd.DataFrame(), pd.DataFrame()
    cols = ["exit_date", "symbol", "asset_type", "qty", "entry_price", "exit_price",
            "holding_days", "pnl", "return_pct"]
    s = closed.sort_values("pnl", ascending=False)
    return s.head(n)[cols], s.tail(n)[cols].iloc[::-1]


def generate_recommendations(r: dict) -> list[dict]:
    """Data-driven insights & recommendations. Recomputed on every statement,
    so the guidance always reflects the latest upload."""
    k = r["kpis"]
    recs = []
    ba = r["by_asset"].set_index("asset_type") if not r["by_asset"].empty else pd.DataFrame()

    # Stocks vs options
    if {"Stocks", "Options"}.issubset(set(ba.index)):
        st, op = ba.loc["Stocks", "pnl"], ba.loc["Options", "pnl"]
        if st > 0 and op < 0:
            recs.append({
                "type": "critical",
                "title": "Your edge is in stocks, not options",
                "body": f"Stocks generated {st:,.0f} USD (win rate {ba.loc['Stocks','win_rate']:.0f}%) "
                        f"while options lost {op:,.0f} USD (win rate {ba.loc['Options','win_rate']:.0f}%). "
                        f"Consider cutting or re-designing the options program until it shows a positive expectancy.",
            })

    # Long-call expiry bleed
    ev = r["option_events"]
    if not ev.empty:
        expired = ev[ev["event"] == "Expired"]
        if len(expired):
            loss = expired["realized_pl"].sum()
            recs.append({
                "type": "warning",
                "title": f"{len(expired)} long options expired worthless (−{abs(loss):,.0f} USD)",
                "body": "Buying single-leg calls and holding to expiry is the biggest options leak. "
                        "Consider (a) taking profits/cutting at a rule-based level well before expiry, "
                        "(b) using spreads to lower premium at risk, or (c) sizing premium as a fixed small % of equity.",
            })

    # Day trading
    bh = r["by_holding"]
    if not bh.empty and "Intraday (day trade)" in set(bh["bucket"]):
        row = bh[bh["bucket"] == "Intraday (day trade)"].iloc[0]
        if row["pnl"] < 0:
            recs.append({
                "type": "warning",
                "title": "Day trades are a net drag",
                "body": f"Intraday trades: {row['pnl']:,.0f} USD across {int(row['trades'])} trades "
                        f"(win rate {row['win_rate']:.0f}%). Your swing/position trades carry the account — "
                        f"lean into the multi-day timeframe where your win rate and expectancy are highest.",
            })
        # find best bucket
        best = bh.loc[bh["pnl"].idxmax()]
        recs.append({
            "type": "positive",
            "title": f"Sweet spot: {best['bucket']}",
            "body": f"This holding window produced {best['pnl']:,.0f} USD at a {best['win_rate']:.0f}% win rate — "
                    f"your most productive timeframe. Concentrate risk here.",
        })

    # Margin interest
    if k["interest"] < -1000:
        recs.append({
            "type": "warning",
            "title": f"Margin interest cost {k['interest']:,.0f} USD",
            "body": "Financing is a meaningful drag on net returns. Review overnight margin usage — "
                    "trimming leverage or holding less overnight would lift net performance directly.",
        })

    # Concentration / worst trade
    _, worst = best_worst_trades(r["closed"], 1)
    if not worst.empty:
        w = worst.iloc[0]
        if w["pnl"] < -0.05 * max(k["realized_pnl"], 1):
            recs.append({
                "type": "warning",
                "title": f"Largest single loss: {w['symbol']} {w['pnl']:,.0f} USD",
                "body": f"One {w['symbol']} exit lost {abs(w['pnl']):,.0f} USD "
                        f"({w['holding_days']:.0f}-day hold). Check that position sizing and stop discipline "
                        f"are consistent — a few outsized losers can erase many good trades.",
            })

    # Sector strength / weakness
    bsec = r.get("by_sector", pd.DataFrame())
    if not bsec.empty:
        material = bsec[bsec["trades"] >= 2]
        if not material.empty:
            best_sec = material.iloc[0]
            worst_sec = material.iloc[-1]
            if best_sec["pnl"] > 0:
                recs.append({
                    "type": "positive",
                    "title": f"Strongest sector: {best_sec['sector']} ({best_sec['pnl']:,.0f} USD)",
                    "body": f"{int(best_sec['trades'])} trades at a {best_sec['win_rate']:.0f}% win rate. "
                            f"This is where your read on the market is sharpest — a natural place to size up.",
                })
            if worst_sec["pnl"] < 0:
                recs.append({
                    "type": "warning",
                    "title": f"Weakest sector: {worst_sec['sector']} ({worst_sec['pnl']:,.0f} USD)",
                    "body": f"{int(worst_sec['trades'])} trades, {worst_sec['win_rate']:.0f}% win rate. "
                            f"Either tighten your criteria here or reduce exposure until the edge returns.",
                })

    # Repeat offenders — names to consider avoiding
    off = r.get("repeat_offenders", pd.DataFrame())
    if not off.empty:
        names = ", ".join(f"{row.underlying} ({row.pnl:,.0f})" for row in off.head(3).itertuples())
        recs.append({
            "type": "critical",
            "title": f"Repeat offenders: {len(off)} names you keep trading at a loss",
            "body": f"Your biggest recurring drains: {names}. These are traded multiple times yet net "
                    f"negative. Put them on a watch/avoid list and review before re-entering — cutting a few "
                    f"repeat losers is often the fastest way to lift overall returns.",
        })

    # Profit factor / positive expectancy
    if k["profit_factor"] > 1.3:
        recs.append({
            "type": "positive",
            "title": f"Positive, durable edge (profit factor {k['profit_factor']:.2f})",
            "body": f"Win rate {k['win_rate']:.0f}% with expectancy of {k['expectancy']:,.0f} USD per trade. "
                    f"The system works — the biggest gains now come from cutting the leaks above, not new strategies.",
        })

    return recs


# --------------------------------------------------------------------------- #
# 7. Top-level convenience
# --------------------------------------------------------------------------- #

def find_latest_statement(data_dir: str) -> str | None:
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")), key=os.path.getmtime)
    return files[-1] if files else None


def analyze(path: str) -> dict:
    sections = read_sections(path)
    trades = get_trades(sections)
    closed = match_round_trips(trades)
    # attach sector to each closed trade (by underlying)
    if not closed.empty:
        if _sectors is not None:
            smap = _sectors.sectors_for(closed["underlying"].unique())
            closed["sector"] = closed["underlying"].map(smap).fillna("Unknown")
        else:
            closed["sector"] = "Unknown"
    open_pos = get_open_positions(sections)
    perf = get_perf_summary(sections)
    income = get_income(sections)
    info = get_account_info(sections)
    result = {
        "path": path,
        "sections": sections,
        "trades": trades,
        "closed": closed,
        "open_positions": open_pos,
        "perf_summary": perf,
        "income": income,
        "info": info,
        "kpis": kpi_block(closed, open_pos, income),
        "mtd": mtd_pnl(closed),
        "monthly": monthly_pnl(closed),
        "by_asset": by_asset(closed),
        "by_underlying": by_symbol(closed, "underlying"),
        "by_holding": by_holding_bucket(closed),
        "call_put": option_call_put(closed),
        "option_events": option_events(trades),
        "by_sector": by_sector(closed),
        "strengths_weaknesses": strengths_weaknesses(closed),
        "dow_entry": day_of_week(closed, "entry"),
        "dow_exit": day_of_week(closed, "exit"),
        "journal": build_journal(closed),
        "periods": list_periods(closed),
        "repeat_offenders": repeat_offenders(closed),
        "reliable_performers": reliable_performers(closed),
    }
    result["recommendations"] = generate_recommendations(result)
    return result


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "statement.csv"
    r = analyze(p)
    k = r["kpis"]
    print(f"Statement: {p}")
    print(f"Closed trades: {k['n_trades']}  win rate: {k['win_rate']:.1f}%")
    print(f"Realized: {k['realized_pnl']:,.0f}  Unrealized: {k['unrealized_pnl']:,.0f}")
    print(f"Profit factor: {k['profit_factor']:.2f}  Expectancy: {k['expectancy']:,.0f}")
    print("\nBy asset:\n", r["by_asset"])
    print("\nBy holding:\n", r["by_holding"])
