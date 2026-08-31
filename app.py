"""
TradeLens · Trading Performance Analytics  (Streamlit)
------------------------------------------------------
Run:   streamlit run app.py

Upload an IBKR year-to-date Activity Statement (CSV) from the sidebar, or drop
files into ./data. Light / dark theme toggle in the sidebar. Nothing you upload
in-app is saved to disk.
"""

from __future__ import annotations

import os
import hashlib
import tempfile
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

import ibkr_analytics as ia

st.set_page_config(page_title="TradeLens · Trading Analytics", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# --------------------------------------------------------------------------- #
# Theme tokens  (validated dataviz palette: dark + light)
# --------------------------------------------------------------------------- #

THEMES = {
    "dark": {
        "page": "#0d0d0d", "surface": "#1a1a19", "surface2": "#232320",
        "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#8f8d86",
        "border": "rgba(255,255,255,0.10)", "border2": "rgba(255,255,255,0.06)",
        "hover": "rgba(255,255,255,0.05)", "grid": "#2c2c2a", "axis": "#383835",
        "profit": "#0ca30c", "loss": "#e0564f", "profit_ink": "#2fbf2f", "loss_ink": "#f0736c",
        "warning": "#fab219", "accent": "#3987e5",
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"],
        "fill_alpha": "rgba(57,135,229,0.14)",
    },
    "light": {
        "page": "#f4f3ef", "surface": "#ffffff", "surface2": "#faf9f6",
        "ink": "#0b0b0b", "ink2": "#3f3e3b", "muted": "#6f6e69",
        "border": "rgba(11,11,11,0.12)", "border2": "rgba(11,11,11,0.07)",
        "hover": "rgba(11,11,11,0.035)", "grid": "#e4e3dc", "axis": "#c3c2b7",
        "profit": "#0f9d0f", "loss": "#d03b3b", "profit_ink": "#067306", "loss_ink": "#c0271f",
        "warning": "#b9791b", "accent": "#2a78d6",
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#c98500", "#c9598a", "#4a3aa7"],
        "fill_alpha": "rgba(42,120,214,0.12)",
    },
}

# --- theme state + toggle (must resolve before we build styles) ------------- #
if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"

with st.sidebar:
    brand_ph = st.empty()  # filled after the theme is resolved, so colors are correct
    dark_on = st.toggle("🌙 Dark mode", value=(st.session_state["theme"] == "dark"))
    st.session_state["theme"] = "dark" if dark_on else "light"
    PRIV = st.toggle("🔒 Privacy mode", value=False,
                     help="Hide all dollar amounts and account identity — safe for "
                          "screenshots and sharing. Percentages, win rates and chart "
                          "shapes stay visible.")

T = THEMES[st.session_state["theme"]]
brand_ph.markdown(
    f"""<div style="display:flex;align-items:center;gap:10px;margin:2px 0 6px">
    <div style="width:34px;height:34px;border-radius:9px;
         background:linear-gradient(135deg,{T['accent']},#7b4de0);
         display:flex;align-items:center;justify-content:center;font-size:18px">📊</div>
    <div><div style="font-size:19px;font-weight:750;letter-spacing:-0.02em;line-height:1;
         color:{T['ink']}">TradeLens</div>
    <div style="font-size:11px;color:{T['muted']};letter-spacing:0.04em">TRADING ANALYTICS</div>
    </div></div>""", unsafe_allow_html=True)
SERIES = T["series"]

# --------------------------------------------------------------------------- #
# Plotly template (rebuilt per theme)
# --------------------------------------------------------------------------- #

pio.templates["tl"] = go.layout.Template(layout=dict(
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=T["ink2"], size=13),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=SERIES,
    xaxis=dict(gridcolor=T["grid"], zerolinecolor=T["axis"], linecolor=T["axis"],
               tickfont=dict(color=T["muted"]), automargin=True),
    yaxis=dict(gridcolor=T["grid"], zerolinecolor=T["axis"], linecolor=T["axis"],
               tickfont=dict(color=T["muted"]), automargin=True),
    legend=dict(font=dict(color=T["ink2"])), margin=dict(l=60, r=20, t=30, b=40),
    hoverlabel=dict(bgcolor=T["surface2"], font=dict(color=T["ink2"]),
                    bordercolor=T["border"]),
))
pio.templates.default = "tl"

def newfig():
    f = go.Figure()
    f.update_layout(template="tl", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return f

# --------------------------------------------------------------------------- #
# CSS  (placeholder-substituted so we never fight f-string braces)
# --------------------------------------------------------------------------- #

CSS = """
<style>
  .stApp { background: __PAGE__; }
  [data-testid="stHeader"] { background: transparent; }
  section[data-testid="stSidebar"] { background: __SURFACE2__; border-right: 1px solid __BORDER__; }
  .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px; }

  .stApp, .stMarkdown, p, span, li, label, div[data-testid="stMarkdownContainer"] { color: __INK2__; }
  h1, h2, h3, h4 { color: __INK__ !important; font-weight: 680; letter-spacing: -0.015em; }
  hr { border-color: __BORDER__ !important; }

  /* cards */
  .kpi-card { background: __SURFACE__; border: 1px solid __BORDER__; border-radius: 14px;
      padding: 15px 17px; height: 100%; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
  .kpi-label { color: __MUTED__; font-size: 11.5px; text-transform: uppercase;
      letter-spacing: 0.06em; margin-bottom: 6px; }
  .kpi-value { font-size: 25px; font-weight: 720; line-height: 1.1; color: __INK__;
      font-variant-numeric: tabular-nums; }
  .kpi-sub { color: __MUTED__; font-size: 11.5px; margin-top: 4px; }

  .rec { border-left: 3px solid __MUTED__; background: __SURFACE__; border: 1px solid __BORDER__;
      border-left-width: 3px; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; }
  .rec-title { font-weight: 660; color: __INK__; margin-bottom: 3px; font-size: 15px; }
  .rec-body { color: __INK2__; font-size: 13.5px; line-height: 1.55; }
  .rec.critical { border-left-color: __LOSS__; }
  .rec.warning  { border-left-color: __WARNING__; }
  .rec.positive { border-left-color: __PROFIT__; }
  .rec.tip      { border-left-color: __ACCENT__; }

  /* themed tables */
  .tbl-wrap { overflow: auto; border: 1px solid __BORDER__; border-radius: 12px; }
  .tbl { width: 100%; border-collapse: collapse; font-size: 13px;
      font-variant-numeric: tabular-nums; }
  .tbl thead th { position: sticky; top: 0; background: __SURFACE2__; color: __MUTED__;
      text-align: left; padding: 9px 13px; font-weight: 650; white-space: nowrap;
      border-bottom: 1px solid __BORDER__; font-size: 11.5px; text-transform: uppercase;
      letter-spacing: 0.03em; }
  .tbl tbody td { padding: 8px 13px; color: __INK2__; border-bottom: 1px solid __BORDER2__;
      white-space: nowrap; }
  .tbl tbody tr:last-child td { border-bottom: none; }
  .tbl tbody tr:hover td { background: __HOVER__; }

  /* tabs */
  .stTabs [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid __BORDER__; }
  .stTabs [data-baseweb="tab"] { padding: 9px 15px; color: __MUTED__; font-weight: 560; }
  .stTabs [aria-selected="true"] { color: __INK__ !important; }
  .stTabs [data-baseweb="tab-highlight"] { background: __ACCENT__; }

  /* widgets */
  [data-baseweb="select"] > div, [data-baseweb="input"] > div,
  .stTextInput input, .stNumberInput input {
      background: __SURFACE__ !important; border-color: __BORDER__ !important; color: __INK__ !important; }
  [data-baseweb="select"] * , .stTextInput input { color: __INK__ !important; }
  [data-baseweb="tag"] { background: __ACCENT__ !important; color: #fff !important; }
  [data-baseweb="popover"] div, [role="listbox"], [role="option"] {
      background: __SURFACE__ !important; color: __INK2__ !important; }
  [role="option"]:hover { background: __HOVER__ !important; }

  .stButton>button, .stDownloadButton>button {
      background: __SURFACE__; color: __INK__; border: 1px solid __BORDER__;
      border-radius: 9px; font-weight: 600; padding: 6px 16px; transition: all .12s; }
  .stButton>button:hover, .stDownloadButton>button:hover {
      border-color: __ACCENT__; color: __ACCENT__; }

  .stRadio label, .stCheckbox label, .stSelectbox label, .stMultiSelect label,
  .stTextInput label, .stToggle label, [data-testid="stWidgetLabel"] p { color: __INK2__ !important; }

  /* radio circles (structure-targeted; emotion hashes are unstable) */
  [data-testid="stRadioOption"] > div > div > div:first-child {
      background: __SURFACE__ !important; border-color: __MUTED__ !important; }
  [data-testid="stRadioOption"][data-selected="true"] > div > div > div:first-child {
      border-color: __ACCENT__ !important; }
  [data-testid="stRadioOption"][data-selected="true"] > div > div > div:first-child > div {
      background: __ACCENT__ !important; }

  [data-testid="stFileUploader"] section {
      background: __SURFACE__; border: 1px dashed __BORDER__; border-radius: 12px; }
  [data-testid="stFileUploaderDropzoneInstructions"] * { color: __MUTED__ !important; }
  [data-testid="stFileUploader"] button {
      background: __SURFACE2__ !important; color: __INK__ !important;
      border: 1px solid __BORDER__ !important; }

  .pill { display:inline-block; padding:3px 10px; border-radius:999px; font-size:11px;
      font-weight:650; }
</style>
"""
for k, v in T.items():
    if isinstance(v, str):
        CSS = CSS.replace(f"__{k.upper()}__", v)
st.markdown(CSS, unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def money(x, dp=0):
    if PRIV:
        return "$•••"
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    s = f"${abs(x):,.{dp}f}"
    return f"−{s}" if x < 0 else s

def pnl_ink(x):
    return T["profit_ink"] if x >= 0 else T["loss_ink"]

def pnl_fill(x):
    return T["profit"] if x >= 0 else T["loss"]

def kpi(col, label, value, sub="", value_color=None):
    col.markdown(f"""<div class="kpi-card"><div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{value_color or T['ink']}">{value}</div>
        <div class="kpi-sub">{sub}</div></div>""", unsafe_allow_html=True)

def rec_card(rec):
    st.markdown(f"""<div class="rec {rec['type']}"><div class="rec-title">{rec['title']}</div>
        <div class="rec-body">{rec['body']}</div></div>""", unsafe_allow_html=True)

def show_table(df, fmts=None, color_cols=None, height=420):
    """Render a DataFrame as a themed HTML table (follows the active theme)."""
    fmts = fmts or {}
    color_cols = color_cols or []
    if df is None or df.empty:
        st.caption("No data.")
        return
    head = "".join(f"<th>{c}</th>" for c in df.columns)
    body = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            if pd.isna(v):
                disp = "—"
            elif PRIV and c in fmts and "$" in fmts[c]:
                disp = "•••"          # mask dollar columns in privacy mode
            elif c in fmts:
                try:
                    disp = fmts[c].format(v)
                except (ValueError, TypeError):
                    disp = str(v)
            else:
                disp = str(v)
            numeric = c in fmts
            style = f"text-align:{'right' if numeric else 'left'};"
            if c in color_cols and isinstance(v, (int, float)) and pd.notna(v):
                style += f"color:{pnl_ink(v)};font-weight:650;"
            cells.append(f"<td style='{style}'>{disp}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    html = (f"<div class='tbl-wrap' style='max-height:{height}px'>"
            f"<table class='tbl'><thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")
    st.markdown(html, unsafe_allow_html=True)

def section(title, caption=None):
    st.markdown(f"### {title}")
    if caption:
        st.caption(caption)

@st.cache_data(show_spinner=False)
def analyze_path(path, mtime):
    return ia.analyze(path)

@st.cache_data(show_spinner="Analysing statement…")
def analyze_bytes(data: bytes, name: str):
    h = hashlib.md5(data).hexdigest()
    tmp = os.path.join(tempfile.gettempdir(), f"tradelens_{h}.csv")
    with open(tmp, "wb") as fh:
        fh.write(data)
    return ia.analyze(tmp)

def plot(fig):
    if PRIV:
        # disable hover so no dollar values leak in a live/shared session
        fig.update_traces(hoverinfo="skip", hovertemplate=None)
    st.plotly_chart(fig, use_container_width=True, theme=None)

def bar_pnl(x, y, height=300, horizontal=False, labels=True, custom=None, hover=None):
    fig = newfig()
    fills = [pnl_fill(v) for v in (x if horizontal else y)]
    vals = x if horizontal else y
    txt = [money(v) for v in vals] if (labels and not PRIV) else None
    kw = dict(marker_color=fills, marker_line_width=0)
    if horizontal:
        fig.add_trace(go.Bar(y=y, x=x, orientation="h", customdata=custom, hovertemplate=hover, **kw))
        fig.update_xaxes(tickprefix="$", tickformat=",.0f", showticklabels=not PRIV)
    else:
        fig.add_trace(go.Bar(x=x, y=y, text=txt, textposition="outside",
                             textfont=dict(color=T["ink2"]), customdata=custom, hovertemplate=hover, **kw))
        fig.update_yaxes(tickprefix="$", tickformat=",.0f", showticklabels=not PRIV)
    fig.update_layout(height=height, showlegend=False)
    return fig

# --------------------------------------------------------------------------- #
# Data source — upload (one-off) or ./data fallback
# --------------------------------------------------------------------------- #

with st.sidebar:
    st.markdown("---")
    st.markdown("#### Statement")
    up = st.file_uploader("Upload IBKR statement (CSV)", type=["csv"],
                          help="Activity Statement, Year-to-Date, CSV. Analyzed in-app only — not saved.")

os.makedirs(DATA_DIR, exist_ok=True)
data_files = sorted([f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv")],
                    key=lambda f: os.path.getmtime(os.path.join(DATA_DIR, f)), reverse=True)

R, source = None, None
if up is not None:
    try:
        R = analyze_bytes(up.getvalue(), up.name)
        source = up.name
    except Exception as e:  # noqa
        st.sidebar.error(f"Could not read that file: {e}")
elif data_files:
    with st.sidebar:
        if PRIV:  # don't expose account-number filenames in a shared screenshot
            labels = [f"Statement {i+1}" for i in range(len(data_files))]
            picked = st.selectbox("Or pick a saved statement", labels, index=0)
            choice = data_files[labels.index(picked)]
        else:
            choice = st.selectbox("Or pick a saved statement", data_files, index=0)
    R = analyze_path(os.path.join(DATA_DIR, choice), os.path.getmtime(os.path.join(DATA_DIR, choice)))
    source = choice

# Landing screen if nothing loaded
if R is None:
    st.markdown("# 📊 TradeLens")
    st.markdown(f"<div style='color:{T['muted']};margin-top:-10px;font-size:15px'>"
                "Professional trading performance analytics for Interactive Brokers.</div>",
                unsafe_allow_html=True)
    st.write("")
    st.markdown(f"""<div class="kpi-card" style="max-width:720px;padding:28px 30px">
        <div style="font-size:19px;font-weight:700;color:{T['ink']};margin-bottom:8px">
        Upload your statement to begin</div>
        <div style="color:{T['ink2']};font-size:14px;line-height:1.6">
        1. In IBKR: <b>Performance &amp; Reports → Statements → Activity</b><br>
        2. Set period to <b>Year to Date</b> and format to <b>CSV</b>, then download<br>
        3. Use <b>Upload IBKR statement</b> in the sidebar ←<br><br>
        Your file is analyzed in-app only and is not saved.</div></div>""",
        unsafe_allow_html=True)
    st.stop()

K, info, closed = R["kpis"], R["info"], R["closed"]

with st.sidebar:
    st.caption(f"Loaded: **{'(hidden)' if PRIV else source}**")
    st.caption(f"Trades analysed: **{K['n_trades']}** · Period: {info.get('stmt_Period','')}")
    st.markdown("---")
    with st.expander("How to update"):
        st.markdown("Upload a fresh **YTD Activity Statement (CSV)** anytime — or drop files "
                    "into the app's **`data/`** folder to keep a library.")
    st.caption("Not investment advice.")

# --------------------------------------------------------------------------- #
# Header + KPIs
# --------------------------------------------------------------------------- #

if PRIV:
    name = "Demo Trader"
    acct_mask = "••••••"
else:
    name = info.get("Name", "Account Holder").title()
    acct = info.get("Account", "")
    acct_mask = (acct[:4] + "•••" + acct[-2:]) if len(acct) > 6 else acct
period = info.get("stmt_Period", "")

st.markdown("# Trading Performance")
st.markdown(f"<div style='color:{T['muted']};margin-top:-12px;font-size:14px'>"
            f"{name} · Account {acct_mask} · {period} · Trading P&L in USD · "
            f"Account NAV in {info.get('Base Currency','SGD')}</div>", unsafe_allow_html=True)
st.write("")

total = K["total_trading_pnl"]
net_account = (K["realized_pnl"] + K["unrealized_pnl"] + K["dividends"]
               + K["withholding"] + K["interest"] + K["fees"])

c = st.columns(5)
kpi(c[0], "Total Trading P&L", money(total), "Realized + unrealized (USD)", pnl_ink(total))
kpi(c[1], "Realized P&L", money(K["realized_pnl"]), f"{K['n_trades']} closed trades", pnl_ink(K["realized_pnl"]))
kpi(c[2], "Unrealized P&L", money(K["unrealized_pnl"]), "Open positions, statement marks", pnl_ink(K["unrealized_pnl"]))
kpi(c[3], "Month-to-Date", money(R["mtd"]), "Realized, current month", pnl_ink(R["mtd"]))
try:
    twr = f"{float(str(info.get('twr')).replace('%','').replace(',','')):.1f}%"
except (TypeError, ValueError):
    twr = "—"
kpi(c[4], "Account Return (TWR)", twr, f"Time-weighted, in {info.get('Base Currency','SGD')}",
    T["profit_ink"] if twr != "—" and not twr.startswith("-") else T["ink"])
st.write("")

c = st.columns(5)
kpi(c[0], "Win Rate", f"{K['win_rate']:.1f}%", f"{K['n_wins']}W / {K['n_losses']}L")
pf = K["profit_factor"]
kpi(c[1], "Profit Factor", f"{pf:.2f}" if np.isfinite(pf) else "∞", "Gross win ÷ gross loss",
    T["profit_ink"] if pf >= 1.3 else (T["warning"] if pf >= 1 else T["loss_ink"]))
kpi(c[2], "Expectancy / Trade", money(K["expectancy"]), "Avg P&L per closed trade", pnl_ink(K["expectancy"]))
kpi(c[3], "Avg Win / Avg Loss", f"{money(K['avg_win'])} / {money(K['avg_loss'])}", "Per winner / loser")
kpi(c[4], "Avg Holding", f"{K['avg_hold_days']:.0f} days", f"{K['n_matched']} in-period · {K['n_carryover']} carried over")
st.write("")

st.markdown(f"<div style='color:{T['ink2']};font-size:13.5px'><b>Net account contribution (USD):</b> "
    f"Realized {money(K['realized_pnl'])} + Unrealized {money(K['unrealized_pnl'])} "
    f"+ Dividends {money(K['dividends'])} − Withholding {money(abs(K['withholding']))} "
    f"− Margin interest {money(abs(K['interest']))} − Fees {money(abs(K['fees']))} "
    f"= <b style='color:{pnl_ink(net_account)}'>{money(net_account)}</b></div>", unsafe_allow_html=True)

st.write("")
t_overview, t_review, t_sectors, t_time, t_options, t_journal, t_play = st.tabs(
    ["📈 Overview", "🔁 Review", "🏭 Sectors", "⏱ Timeframes", "🎯 Options",
     "📓 Journal", "🧭 Playbook"])

# =========================================================================== #
# OVERVIEW
# =========================================================================== #
with t_overview:
    left, right = st.columns([3, 2])
    with left:
        section("Cumulative realized P&L")
        m = R["monthly"]
        if not m.empty:
            fig = newfig()
            fig.add_trace(go.Scatter(x=m["month"], y=m["cumulative"], mode="lines",
                line=dict(color=T["accent"], width=2.5), fill="tozeroy",
                fillcolor=T["fill_alpha"],
                hovertemplate="%{x|%b %Y}<br>Cumulative: $%{y:,.0f}<extra></extra>"))
            fig.update_layout(height=320, showlegend=False)
            fig.update_yaxes(tickprefix="$", tickformat=",.0f", showticklabels=not PRIV)
            plot(fig)
    with right:
        section("Monthly realized P&L")
        m = R["monthly"]
        if not m.empty:
            fig = bar_pnl(m["month"], m["pnl"], height=320, labels=False,
                          hover="%{x|%b %Y}<br>$%{y:,.0f}<extra></extra>")
            fig.update_layout(bargap=0.25)
            plot(fig)

    st.divider()
    left, right = st.columns(2)
    with left:
        section("Stocks vs Options")
        ba = R["by_asset"]
        if not ba.empty:
            fig = bar_pnl(ba["asset_type"], ba["pnl"], height=300,
                          custom=np.stack([ba["trades"], ba["win_rate"]], axis=-1),
                          hover="%{x}<br>P&L $%{y:,.0f}<br>%{customdata[0]} trades · %{customdata[1]:.0f}% win<extra></extra>")
            plot(fig)
    with right:
        section("Best & worst names")
        bu = R["by_underlying"]
        if not bu.empty:
            top = pd.concat([bu.head(8), bu.tail(8)]).drop_duplicates("underlying").sort_values("pnl")
            fig = bar_pnl(top["pnl"], top["underlying"], height=300, horizontal=True,
                          custom=np.stack([top["trades"], top["win_rate"], top["avg_hold"]], axis=-1),
                          hover="%{y}<br>P&L $%{x:,.0f}<br>%{customdata[0]} trades · %{customdata[1]:.0f}% win · %{customdata[2]:.0f}d<extra></extra>")
            plot(fig)

    st.divider()
    section("Open positions", "Unrealized P&L at statement marks.")
    op = R["open_positions"]
    if not op.empty:
        show = op[["Symbol","asset_type","Quantity","Cost Price","Close Price","Value","Unrealized P/L"]].copy()
        show = show.rename(columns={"asset_type":"Type","Cost Price":"Avg cost","Close Price":"Mark","Unrealized P/L":"Unrealized"}).sort_values("Unrealized", ascending=False)
        show_table(show, {"Quantity":"{:,.0f}","Avg cost":"${:,.2f}","Mark":"${:,.2f}",
                   "Value":"${:,.0f}","Unrealized":"${:,.0f}"}, ["Unrealized"], height=460)
    else:
        st.info("No open positions.")

# =========================================================================== #
# REVIEW
# =========================================================================== #
with t_review:
    section("Trade review",
            "Pick a period to review your biggest winners and losers, then check the "
            "repeat-offender list to decide which names to stop trading.")
    per = R["periods"]
    week_labels = [w["label"] for w in per["weeks"]]
    month_labels = per["months"]

    fc = st.columns([2, 3])
    scope = fc[0].selectbox("Period", ["Latest week", "Pick a week", "This month",
                        "Pick a month", "Last 30 days", "All-time"], index=0)
    if scope == "Latest week":
        wk = per["weeks"][0] if per["weeks"] else None
        dfp = ia.filter_period(closed, "week", (wk["start"], wk["end"])) if wk else closed
        plabel = wk["label"] if wk else "—"
    elif scope == "Pick a week":
        sel = fc[1].selectbox("Week (by close date)", week_labels) if week_labels else None
        wk = next((w for w in per["weeks"] if w["label"] == sel), None)
        dfp = ia.filter_period(closed, "week", (wk["start"], wk["end"])) if wk else closed
        plabel = sel or "—"
    elif scope == "This month":
        m = month_labels[0] if month_labels else None
        dfp = ia.filter_period(closed, "month", m); plabel = m or "—"
    elif scope == "Pick a month":
        m = fc[1].selectbox("Month (by close date)", month_labels) if month_labels else None
        dfp = ia.filter_period(closed, "month", m); plabel = m or "—"
    elif scope == "Last 30 days":
        dfp = ia.filter_period(closed, "last30"); plabel = "Last 30 days"
    else:
        dfp = closed; plabel = "All-time"

    st.markdown(f"**Reviewing: {plabel}** · {len(dfp)} closed trade(s)")
    if not dfp.empty:
        s = st.columns(4)
        kpi(s[0], "Net P&L", money(dfp["pnl"].sum()), value_color=pnl_ink(dfp["pnl"].sum()))
        wr = (dfp["pnl"] > 0).mean()*100
        kpi(s[1], "Win rate", f"{wr:.0f}%", f"{int((dfp['pnl']>0).sum())}W / {int((dfp['pnl']<0).sum())}L")
        kpi(s[2], "Best trade", money(dfp["pnl"].max()), value_color=T["profit_ink"])
        kpi(s[3], "Worst trade", money(dfp["pnl"].min()), value_color=T["loss_ink"])
        st.write("")

    win, los = ia.top_bottom_by_ticker(dfp, 3)
    cc = st.columns(2)
    with cc[0]:
        st.markdown("#### 🏆 Top 3 winners")
        if not win.empty:
            for _, row in win.iterrows():
                st.markdown(f"<div class='rec positive'><div class='rec-title'>{row['underlying']} · "
                    f"<span style='color:{T['profit_ink']}'>{money(row['pnl'])}</span></div>"
                    f"<div class='rec-body'>{int(row['trades'])} trade(s) · {row['win_rate']:.0f}% win</div></div>",
                    unsafe_allow_html=True)
        else:
            st.caption("No winning names in this period.")
    with cc[1]:
        st.markdown("#### 💀 Top 3 losers")
        if not los.empty:
            for _, row in los.iterrows():
                st.markdown(f"<div class='rec critical'><div class='rec-title'>{row['underlying']} · "
                    f"<span style='color:{T['loss_ink']}'>{money(row['pnl'])}</span></div>"
                    f"<div class='rec-body'>{int(row['trades'])} trade(s) · {row['win_rate']:.0f}% win</div></div>",
                    unsafe_allow_html=True)
        else:
            st.caption("No losing names in this period.")

    st.divider()
    section("⚠️ Repeat offenders — your avoid list",
            "Names traded 2+ times that are net negative overall (all-time). Think twice before re-entering.")
    off = R["repeat_offenders"]
    if not off.empty:
        show = off[["underlying","sector","trades","wins","win_rate","pnl","avg_pnl","last_traded"]].copy()
        show["last_traded"] = pd.to_datetime(show["last_traded"]).dt.strftime("%Y-%m-%d")
        show = show.rename(columns={"underlying":"Ticker","sector":"Sector","trades":"Trades",
                           "wins":"Wins","win_rate":"Win %","pnl":"Net P&L","avg_pnl":"Avg / trade",
                           "last_traded":"Last traded"})
        show_table(show, {"Trades":"{:.0f}","Wins":"{:.0f}","Win %":"{:.0f}%",
                   "Net P&L":"${:,.0f}","Avg / trade":"${:,.0f}"}, ["Net P&L","Avg / trade"], height=420)
        if not PRIV:
            st.download_button("⬇ Download avoid list (CSV)",
                               show.to_csv(index=False).encode("utf-8"), "avoid_list.csv", "text/csv")
    else:
        st.success("No repeat offenders — no multi-trade name is net negative. Nice discipline.")

    st.divider()
    section("✅ Reliable performers — names that keep working")
    rp = R["reliable_performers"]
    if not rp.empty:
        show = rp.head(15)[["underlying","sector","trades","win_rate","pnl","avg_pnl"]].copy()
        show = show.rename(columns={"underlying":"Ticker","sector":"Sector","trades":"Trades",
                           "win_rate":"Win %","pnl":"Net P&L","avg_pnl":"Avg / trade"})
        show_table(show, {"Trades":"{:.0f}","Win %":"{:.0f}%","Net P&L":"${:,.0f}",
                   "Avg / trade":"${:,.0f}"}, ["Net P&L"], height=420)

    st.divider()
    section(f"Trades in this period — {plabel}")
    if not dfp.empty:
        d = dfp.sort_values("exit_date", ascending=False).copy()
        d["exit_date"] = pd.to_datetime(d["exit_date"]).dt.strftime("%Y-%m-%d")
        d["entry_date"] = pd.to_datetime(d["entry_date"]).dt.strftime("%Y-%m-%d")
        d = d.rename(columns={"exit_date":"Sold","entry_date":"Bought","symbol":"Symbol",
                     "sector":"Sector","asset_type":"Type","qty":"Qty","entry_price":"Entry",
                     "exit_price":"Exit","holding_days":"Hold (d)","pnl":"Profit","return_pct":"Return %"})
        cols = ["Sold","Bought","Symbol","Sector","Type","Qty","Entry","Exit","Hold (d)","Profit","Return %"]
        show_table(d[cols], {"Qty":"{:,.0f}","Entry":"${:,.2f}","Exit":"${:,.2f}",
                   "Hold (d)":"{:.0f}","Profit":"${:,.0f}","Return %":"{:.1f}%"}, ["Profit"], height=380)
    else:
        st.info("No closed trades in this period.")

# =========================================================================== #
# SECTORS
# =========================================================================== #
with t_sectors:
    bs = R["by_sector"]
    section("Profit & loss by sector")
    if not bs.empty:
        left, right = st.columns([3, 2])
        with left:
            b = bs.sort_values("pnl")
            fig = bar_pnl(b["pnl"], b["sector"], height=380, horizontal=True,
                          custom=np.stack([b["trades"], b["win_rate"], b["avg_hold"]], axis=-1),
                          hover="%{y}<br>P&L $%{x:,.0f}<br>%{customdata[0]} trades · %{customdata[1]:.0f}% win · %{customdata[2]:.0f}d<extra></extra>")
            plot(fig)
        with right:
            st.markdown("**Win rate by sector**")
            b = bs.sort_values("win_rate", ascending=True)
            fig = newfig()
            fig.add_trace(go.Bar(y=b["sector"], x=b["win_rate"], orientation="h",
                marker_color=T["accent"], marker_line_width=0,
                text=[f"{v:.0f}%" for v in b["win_rate"]], textposition="outside",
                textfont=dict(color=T["ink2"]),
                hovertemplate="%{y}<br>%{x:.0f}% win<extra></extra>"))
            fig.update_layout(height=380, showlegend=False)
            fig.update_xaxes(ticksuffix="%", range=[0, 108])
            plot(fig)

        st.markdown("**Sector detail**")
        show = bs.rename(columns={"sector":"Sector","pnl":"P&L","trades":"Trades",
                        "win_rate":"Win %","avg_pnl":"Avg P&L","avg_hold":"Avg hold (d)"})
        show_table(show, {"P&L":"${:,.0f}","Trades":"{:.0f}","Win %":"{:.0f}%","Avg P&L":"${:,.0f}",
                   "Avg hold (d)":"{:.0f}"}, ["P&L"], height=420)

        st.divider()
        section("Where profit concentrates (sector → ticker)")
        cl = closed[closed["pnl"] != 0].copy()
        agg = cl.groupby(["sector","underlying"], as_index=False).agg(pnl=("pnl","sum"))
        agg["abs"] = agg["pnl"].abs()
        # Build an explicit hierarchy: sector parent nodes (parent="") + ticker leaves.
        # Every referenced parent MUST exist as a node, or Plotly draws nothing.
        sec_tot = agg.groupby("sector", as_index=False).agg(pnl=("pnl","sum"))
        ids, labels, parents, values, colors, cdata = [], [], [], [], [], []
        for _, s in sec_tot.iterrows():
            ids.append(f"SEC::{s['sector']}"); labels.append(s["sector"]); parents.append("")
            values.append(0); colors.append(T["surface2"]); cdata.append(s["pnl"])
        for _, r in agg.iterrows():
            ids.append(f"SEC::{r['sector']}::{r['underlying']}"); labels.append(r["underlying"])
            parents.append(f"SEC::{r['sector']}"); values.append(r["abs"])
            colors.append(pnl_fill(r["pnl"])); cdata.append(r["pnl"])
        fig = go.Figure(go.Treemap(
            ids=ids, labels=labels, parents=parents, values=values, customdata=cdata,
            branchvalues="remainder",
            marker=dict(colors=colors, line=dict(width=1, color=T["page"])),
            texttemplate="%{label}" if PRIV else "%{label}<br>$%{customdata:,.0f}",
            hovertemplate="%{label}<br>P&L $%{customdata:,.0f}<extra></extra>",
            textfont=dict(color="#ffffff", size=13), tiling=dict(pad=2)))
        fig.update_layout(height=460, margin=dict(l=0,r=0,t=10,b=0), paper_bgcolor="rgba(0,0,0,0)")
        plot(fig)
        st.caption("Tile size = size of P&L; green = net profit, red = net loss. "
                   "Sectors use a curated GICS-style map (edit sectors.py to refine).")

        sw = R["strengths_weaknesses"]
        cc = st.columns(2)
        with cc[0]:
            st.markdown("**💪 Strengths**")
            s = sw["strength_sectors"]
            if not s.empty:
                for _, row in s.iterrows():
                    st.markdown(f"- **{row['sector']}** · {money(row['pnl'])} over {int(row['trades'])} trades ({row['win_rate']:.0f}% win)")
            else:
                st.caption("No clearly positive sectors yet.")
        with cc[1]:
            st.markdown("**⚠️ Weaknesses**")
            w = sw["weak_sectors"]
            if not w.empty:
                for _, row in w.iterrows():
                    st.markdown(f"- **{row['sector']}** · {money(row['pnl'])} over {int(row['trades'])} trades ({row['win_rate']:.0f}% win)")
            else:
                st.caption("No materially losing sectors — nice.")
    else:
        st.info("No sector data available.")

# =========================================================================== #
# TIMEFRAMES
# =========================================================================== #
with t_time:
    section("Day trade vs swing vs position")
    bh = R["by_holding"]
    if not bh.empty:
        fig = bar_pnl(bh["bucket"], bh["pnl"], height=320,
                      custom=np.stack([bh["trades"], bh["win_rate"]], axis=-1),
                      hover="%{x}<br>P&L $%{y:,.0f}<br>%{customdata[0]} trades · %{customdata[1]:.0f}% win<extra></extra>")
        fig.update_xaxes(tickangle=-10)
        plot(fig)
        show = bh.rename(columns={"bucket":"Holding window","pnl":"P&L","trades":"Trades","win_rate":"Win %","avg_pnl":"Avg P&L"})
        show_table(show, {"P&L":"${:,.0f}","Trades":"{:.0f}","Win %":"{:.0f}%","Avg P&L":"${:,.0f}"}, ["P&L"], height=260)
    st.caption("Covers trades opened & closed within the period. Carried-over positions are excluded here but included in P&L.")

    st.divider()
    section("Day-of-week patterns", "Entry = day you opened; Exit = day you closed.")
    cc = st.columns(2)
    for col, key, title in [(cc[0], "dow_entry", "By entry day"), (cc[1], "dow_exit", "By exit day")]:
        with col:
            st.markdown(f"**{title}**")
            d = R[key]
            if not d.empty:
                fig = bar_pnl(d["dow"], d["pnl"], height=300, labels=False,
                              custom=np.stack([d["trades"], d["win_rate"]], axis=-1),
                              hover="%{x}<br>P&L $%{y:,.0f}<br>%{customdata[0]} trades · %{customdata[1]:.0f}% win<extra></extra>")
                plot(fig)
                sh = d.rename(columns={"dow":"Day","pnl":"P&L","trades":"Trades","win_rate":"Win %"})
                show_table(sh, {"P&L":"${:,.0f}","Trades":"{:.0f}","Win %":"{:.0f}%"}, ["P&L"], height=260)

    st.divider()
    section("Holding period vs P&L")
    cl = closed[closed["holding_days"].notna()]
    if not cl.empty:
        fig = newfig()
        fig.add_trace(go.Scatter(x=cl["holding_days"], y=cl["pnl"], mode="markers",
            marker=dict(size=8, color=[pnl_fill(v) for v in cl["pnl"]],
                        line=dict(width=1, color=T["page"]), opacity=0.8),
            customdata=cl["symbol"],
            hovertemplate="%{customdata}<br>%{x:.0f}d hold · $%{y:,.0f}<extra></extra>"))
        fig.update_layout(height=340, showlegend=False)
        fig.update_xaxes(title="Holding days")
        fig.update_yaxes(tickprefix="$", tickformat=",.0f", showticklabels=not PRIV)
        plot(fig)

# =========================================================================== #
# OPTIONS
# =========================================================================== #
with t_options:
    section("Options program")
    oc1, oc2 = st.columns([2, 3])
    with oc1:
        cp = R["call_put"]
        st.markdown("**Calls vs puts**")
        if not cp.empty:
            fig = bar_pnl(cp["right"], cp["pnl"], height=300,
                          custom=np.stack([cp["trades"], cp["win_rate"]], axis=-1),
                          hover="%{x}<br>$%{y:,.0f}<br>%{customdata[0]} trades · %{customdata[1]:.0f}% win<extra></extra>")
            plot(fig)
        else:
            st.info("No option trades in this statement.")
    with oc2:
        st.markdown("**Exercises, assignments & expiries**")
        ev = R["option_events"]
        if not ev.empty:
            show = ev.copy()
            show["date"] = pd.to_datetime(show["date"]).dt.strftime("%Y-%m-%d")
            show = show.rename(columns={"date":"Date","Symbol":"Contract","event":"Event",
                                        "qty":"Qty","realized_pl":"Realized P&L","code":"Code"})
            show_table(show[["Date","Contract","Event","Qty","Realized P&L","Code"]],
                       {"Qty":"{:.0f}","Realized P&L":"${:,.0f}"}, ["Realized P&L"], height=300)
            n_ex = (ev["event"] == "Exercise").sum(); n_exp = (ev["event"] == "Expired").sum()
            st.caption(f"{n_ex} exercise event(s) converted long calls into stock · {n_exp} expired worthless.")
        else:
            st.info("No exercise / assignment / expiry events.")
    st.divider()
    opt = closed[closed["is_option"]]
    if not opt.empty:
        st.markdown("**Every option round-trip**")
        show = opt[["exit_date","symbol","opt_right","qty","entry_price","exit_price","holding_days","pnl"]].copy()
        show["exit_date"] = pd.to_datetime(show["exit_date"]).dt.strftime("%Y-%m-%d")
        show = show.rename(columns={"exit_date":"Closed","symbol":"Contract","opt_right":"C/P",
                           "qty":"Qty","entry_price":"Entry","exit_price":"Exit","holding_days":"Hold (d)","pnl":"P&L"}).sort_values("Closed", ascending=False)
        show_table(show, {"Qty":"{:.0f}","Entry":"${:,.2f}","Exit":"${:,.2f}",
                   "Hold (d)":"{:.0f}","P&L":"${:,.0f}"}, ["P&L"], height=380)

# =========================================================================== #
# JOURNAL
# =========================================================================== #
with t_journal:
    section("Trading journal",
            "Every closed trade: when you opened, when you closed, how long you held, and the profit.")
    j = R["journal"]
    if not j.empty:
        f = st.columns(4)
        asset_f = f[0].multiselect("Asset", sorted(j["asset_type"].unique()), default=list(j["asset_type"].unique()))
        sec_f = f[1].multiselect("Sector", sorted(j["sector"].dropna().unique()), default=list(j["sector"].dropna().unique()))
        res_f = f[2].selectbox("Result", ["All","Win","Loss"])
        sym_f = f[3].text_input("Symbol contains", "")

        v = j[j["asset_type"].isin(asset_f) & j["sector"].isin(sec_f)]
        if res_f != "All":
            v = v[v["result"] == res_f]
        if sym_f:
            v = v[v["symbol"].str.contains(sym_f, case=False, na=False)]

        s = st.columns(4)
        kpi(s[0], "Trades", f"{len(v)}")
        kpi(s[1], "Net P&L", money(v["pnl"].sum()), value_color=pnl_ink(v["pnl"].sum()))
        wr = (v["pnl"] > 0).mean()*100 if len(v) else 0
        kpi(s[2], "Win rate", f"{wr:.0f}%")
        kpi(s[3], "Avg hold", f"{v['holding_days'].dropna().mean():.0f} d" if len(v) else "—")
        st.write("")

        disp = v.copy()
        disp["entry_date"] = pd.to_datetime(disp["entry_date"]).dt.strftime("%Y-%m-%d")
        disp["exit_date"] = pd.to_datetime(disp["exit_date"]).dt.strftime("%Y-%m-%d")
        disp = disp.rename(columns={"entry_date":"Bought","exit_date":"Sold","symbol":"Symbol",
                           "sector":"Sector","asset_type":"Type","qty":"Qty","entry_price":"Entry",
                           "exit_price":"Exit","holding_days":"Hold (d)","pnl":"Profit",
                           "return_pct":"Return %","result":"Result","side_note":"Note"})
        cols = ["Sold","Bought","Symbol","Sector","Type","Qty","Entry","Exit","Hold (d)","Profit","Return %","Result","Note"]
        show_table(disp[cols], {"Qty":"{:,.0f}","Entry":"${:,.2f}","Exit":"${:,.2f}",
                   "Hold (d)":"{:.0f}","Profit":"${:,.0f}","Return %":"{:.1f}%"}, ["Profit"], height=520)
        if not PRIV:
            st.download_button("⬇ Download journal (CSV)",
                               disp[cols].to_csv(index=False).encode("utf-8"), "trading_journal.csv", "text/csv")
        st.caption("'Bought' is blank for positions carried over from a prior year (entry date not in this statement).")

# =========================================================================== #
# PLAYBOOK
# =========================================================================== #
with t_play:
    section("What the data says — analysis & recommendations")
    for rec in R["recommendations"]:
        rec_card(rec)

    st.divider()
    section("Trading discipline — things to watch")
    tips = [
        ("tip", "Trade your edge, not your boredom",
         "The money is made in multi-day swings on large-cap Tech, Financials and Healthcare. Trades outside "
         "that profile (day trades, single-leg long calls) are where the leaks are. Before every entry, ask: "
         "does this fit the setup that actually makes me money?"),
        ("tip", "Cap the damage on any single trade",
         "Your worst exit lost roughly as much as 8–10 average winners. Define a max loss per position (e.g. 1–2% "
         "of equity) and a mechanical stop before you enter. One avoided outlier beats several good trades."),
        ("tip", "Give options a rule, or give them up",
         "Buying calls and holding to expiry has a negative expectancy for you. If you keep trading options: take "
         "profits at a pre-set multiple, cut at a pre-set loss, prefer spreads to cut premium at risk, and never "
         "let a long option ride into expiry week hoping."),
        ("tip", "Respect the financing cost",
         "Margin interest quietly removes a chunk of your net return every year. Know your overnight buying-power "
         "usage, and treat leverage as a cost that must be earned back before a trade is truly profitable."),
        ("tip", "Let winners run, size them up",
         "Your position-trade and strong-sector buckets have the best win rates. Scale into your highest-conviction, "
         "best-sector setups rather than spreading size thinly across many marginal ideas."),
        ("tip", "Journal the 'why', not just the numbers",
         "This dashboard captures the what (entry, exit, P&L). Keep a one-line note per trade on the reason for the "
         "entry and exit. Reviewing those notes against outcomes is how the edge compounds."),
    ]
    for t in tips:
        rec_card({"type": t[0], "title": t[1], "body": t[2]})
    st.caption("General trading-discipline guidance tailored to the patterns in your data — not investment advice.")

# --------------------------------------------------------------------------- #
st.markdown(f"<div style='color:{T['muted']};font-size:11.5px;margin-top:24px'>"
    f"TradeLens · generated {datetime.now():%Y-%m-%d %H:%M} · Source: {'(hidden)' if PRIV else source} · "
    "P&L uses IBKR's tax-lot Realized P/L (reconciled to statement). Not investment advice.</div>",
    unsafe_allow_html=True)
