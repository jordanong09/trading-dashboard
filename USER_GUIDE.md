# TradeLens — User Guide

**TradeLens** turns an Interactive Brokers (IBKR) year-to-date statement into a clean,
interactive dashboard of your trading performance — profit & loss, win rate, sector
strengths and weaknesses, holding-period and day-vs-swing patterns, an options
breakdown, a full trade journal, and a weekly review console with a "repeat offender"
avoid list.

Everything runs **on your own computer**. Your statement is never uploaded to any
server — see [Privacy & your data](#privacy--your-data).

---

## 1. What you need

- A computer with **Python 3.9 or newer** installed ([python.org/downloads](https://www.python.org/downloads/); on Windows, tick *"Add Python to PATH"* during install).
- An **Interactive Brokers** account and its **Activity Statement** exported as a CSV (below).

---

## 2. Export your statement from IBKR

1. Log in to **IBKR Client Portal** (or Account Management).
2. Go to **Performance & Reports → Statements**.
3. Choose **Activity** statement.
4. Set:
   - **Period:** *Year to Date* (or any custom date range you want to analyse)
   - **Format:** *CSV*
5. **Run / Download** the file. You'll get a file named something like
   `U1234567_20260101_20260828.csv`.

> Tip: the same app works for any date range — a full year, a single quarter, etc.
> Just export that range as CSV.

---

## 3. Install & run

**Windows (easiest):** double-click **`run_dashboard.bat`**. The first time, it installs
what it needs and then opens the dashboard in your browser. Leave the small black
window open while you use it; close it to stop.

**Any OS (manual):** open a terminal in the TradeLens folder and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

The dashboard opens automatically at **http://localhost:8501**.

---

## 4. Load your statement

Two ways, either works:

1. **Upload (recommended):** in the sidebar, use **Upload IBKR statement (CSV)** and pick
   your file. It's analysed instantly and **not saved anywhere**.
2. **Folder library:** drop CSV files into the **`data/`** folder next to the app. The
   sidebar lets you pick any of them; the newest loads by default. Use this if you want
   to keep past statements handy.

To review a newer period later, just export a fresh statement and upload it again.

---

## 5. Key features

Everything is organised into tabs across the top:

- **📈 Overview** — headline numbers (total / realized / unrealized P&L, month-to-date,
  account return, win rate, profit factor, expectancy, average holding), your equity
  curve, monthly P&L, stocks-vs-options, best & worst names, and open positions.
- **🔁 Review** — your weekly review console. Pick a period (latest week, any week, a
  month, last 30 days, or all-time) and see your **top 3 winners and top 3 losers**, plus
  a **repeat-offenders "avoid list"** (names you've traded more than once that keep losing
  money) and a list of reliable performers.
- **🏭 Sectors** — profit & loss and win rate by sector, a treemap of where your profit
  concentrates (sector → ticker), and an auto-generated strengths / weaknesses summary.
- **⏱ Timeframes** — day-trade vs swing vs position performance, day-of-week patterns
  (which days your entries and exits actually work), and a holding-period vs P&L scatter.
- **🎯 Options** — calls vs puts, every exercise / assignment / expiry event, and a full
  option round-trip table.
- **📓 Journal** — every closed trade with the date you bought, the date you sold, how
  long you held, and the profit. Filter by asset, sector, or result, and export to CSV.
- **🧭 Playbook** — data-driven observations and trading-discipline tips based on your own
  numbers.

**Two switches in the sidebar:**

- **🌙 Dark mode** — toggle light / dark theme.
- **🔒 Privacy mode** — hides every dollar amount and your account identity (name,
  account number, filename) while keeping win rates, ratios, and chart shapes visible.
  Turn this on before taking screenshots or sharing your screen. (Collapse the sidebar
  with the **«** button for the cleanest capture.)

---

## 6. What it CAN do

- Read a standard **IBKR Activity Statement CSV** and reconcile realized P&L to the cent
  against IBKR's own figures.
- Analyse **US stocks and equity / index options**.
- Correctly handle positions **carried over from a prior year** (sold this period but
  bought earlier) — their P&L is included using IBKR's true cost basis.
- Detect **option exercises, assignments, and expiries** automatically.
- Recompute **every number, chart, and recommendation** each time you load a new
  statement — nothing is hard-coded.
- Work **fully offline** once installed.

## 7. What it CANNOT do (limitations)

- It is **not** a live brokerage connection or a trade-execution tool. It only reads a
  statement file you provide — it cannot place trades or see your account in real time.
- **Unrealized P&L uses the mark prices in your statement**, not live market prices. It's
  as fresh as your statement, not up-to-the-second.
- It expects the **IBKR Activity Statement CSV** format. Other brokers, or IBKR's other
  export types (e.g. Flex Queries with different sections), may not parse without changes.
- Trading P&L is shown in **USD** (the trade currency). Account-level return (TWR) is
  shown separately in your account's **base currency**, taken from the statement.
- **Holding-period / day-vs-swing stats** only cover trades both opened *and* closed
  within the statement period. Carried-over positions are counted in P&L but excluded
  from holding-time stats (their original buy date isn't in the file).
- **Sector labels** come from a built-in list (`sectors.py`). A ticker that isn't listed
  shows as *Unknown* until you add it (one line) or run `enrich_sectors.py`.
- It analyses **equities and equity/index options**. Futures, forex, bonds, and funds are
  not specifically modelled.
- **It is not investment advice.** The observations and tips are descriptive analysis of
  your past trades, not recommendations to buy or sell anything.

---

## 8. Privacy & your data

- Your statement is processed **locally on your machine**. Nothing is sent to TradeLens,
  the developer, or any external server.
- **Uploaded** files are analysed in memory and **not saved**. Files you place in `data/`
  stay on your computer.
- When sharing the app itself, **do not include your `data/` folder** — it may contain
  your account number and trade history. (The packaged version excludes it by design.)
- Use **Privacy mode** for any screenshot or screen-share.

---

## 9. Troubleshooting

- **"python is not recognised" / nothing happens** — Python isn't installed or isn't on
  PATH. Reinstall from python.org and tick *Add Python to PATH*.
- **The browser tab didn't open** — go to **http://localhost:8501** manually.
- **"No statement found"** — upload a CSV in the sidebar, or drop one into `data/`.
- **A ticker shows as "Unknown" sector** — add it to `sectors.py`, or run
  `python enrich_sectors.py` (needs a free Alpha Vantage API key).
- **Numbers look off** — make sure you exported the **Activity** statement as **CSV**
  (not a Flex Query or PDF), covering the period you intend.

---

## 10. FAQ

**Does this connect to my broker?** No. It only reads a statement file you export yourself.

**Will my data be shared?** No. Everything runs locally; uploads aren't saved.

**Can others use it with their own account?** Yes — that's the point. Anyone installs it,
exports their own IBKR statement, and uploads it. The account name auto-fills from
whatever file is loaded.

**Can I use a different date range than year-to-date?** Yes. Export any range as CSV.

**Is my profit shown to anyone if I share a screenshot?** Not if you enable **Privacy
mode** first — all dollar amounts and your identity are masked.

---

*TradeLens is a personal analytics tool. It is not affiliated with Interactive Brokers,
and nothing here is investment advice.*
