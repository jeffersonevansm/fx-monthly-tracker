"""
FX Monthly Tracker -- institutional-grade monthly FX research, Linear-inspired UI.

Pairs: DXY, EUR/USD, GBP/USD, AUD/USD, NZD/USD, USD/IDR
Views: Reports (AI monthly research) / Dashboard / Archive / News / About

AI research (fundamental + technical + sentiment) is generated on demand via the
Claude API. Web search OFF by default to keep it cheap (~1c); tick the box for
cited, verified event research (~10-15c). Uses the Haiku model.

HOW TO RUN (needs internet):
    pip3 install streamlit yfinance pandas requests anthropic plotly
    export FINNHUB_API_KEY="your-finnhub-key"
    export FRED_API_KEY="your-fred-key"
    export ANTHROPIC_API_KEY="your-anthropic-key"
    streamlit run fx_tracker.py
"""

import os
import re
import json
import html as html_lib
import time
import calendar
import datetime as dt

import requests
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go

# ============================ CONFIG =====================================

PAIRS = {
    "DXY": {"name": "US Dollar Index", "ticker": "DX-Y.NYB", "usd_is_base": True,  "flag": "🇺🇸", "dp": 2},
    "EUR/USD": {"name": "Euro",        "ticker": "EURUSD=X", "usd_is_base": False, "flag": "🇪🇺", "dp": 4},
    "GBP/USD": {"name": "British Pound", "ticker": "GBPUSD=X", "usd_is_base": False, "flag": "🇬🇧", "dp": 4},
    "AUD/USD": {"name": "Australian Dollar", "ticker": "AUDUSD=X", "usd_is_base": False, "flag": "🇦🇺", "dp": 4},
    "NZD/USD": {"name": "New Zealand Dollar", "ticker": "NZDUSD=X", "usd_is_base": False, "flag": "🇳🇿", "dp": 4},
    "USD/IDR": {"name": "Indonesian Rupiah", "ticker": "USDIDR=X", "usd_is_base": True, "flag": "🇮🇩", "dp": 0},
}

FRED_SERIES = {
    "Fed funds rate (%, level)": "FEDFUNDS",
    "CPI (index level)":         "CPIAUCSL",
    "Core CPI (index level)":    "CPILFESL",
    "Unemployment rate (%)":     "UNRATE",
    "Nonfarm payrolls (000s)":   "PAYEMS",
}

FLAGS = {"US": "🇺🇸", "EU": "🇪🇺", "EZ": "🇪🇺", "GB": "🇬🇧", "UK": "🇬🇧", "AU": "🇦🇺",
         "NZ": "🇳🇿", "ID": "🇮🇩", "JP": "🇯🇵", "CN": "🇨🇳", "CA": "🇨🇦", "CH": "🇨🇭",
         "DE": "🇩🇪", "FR": "🇫🇷", "GL": "🌐"}

st.set_page_config(page_title="FX Monthly Tracker", page_icon="◆",
                   layout="wide", initial_sidebar_state="collapsed")

# ============================ THEME / CSS ================================

DARK = {
    "bg": "#09090B", "card": "#111113", "card2": "#0D0D0F",
    "border": "rgba(255,255,255,0.06)", "border2": "rgba(255,255,255,0.13)",
    "text": "#FAFAFA", "text2": "#A1A1AA", "text3": "#6B6B74",
    "navbg": "rgba(17,17,19,0.72)", "hover": "rgba(255,255,255,0.025)",
    "shadow": "0 10px 34px rgba(0,0,0,0.38)", "grid": "rgba(255,255,255,0.05)",
}
LIGHT = {
    "bg": "#FAFAFA", "card": "#FFFFFF", "card2": "#F4F4F5",
    "border": "rgba(0,0,0,0.07)", "border2": "rgba(0,0,0,0.16)",
    "text": "#09090B", "text2": "#52525B", "text3": "#8E8E96",
    "navbg": "rgba(255,255,255,0.78)", "hover": "rgba(0,0,0,0.02)",
    "shadow": "0 10px 30px rgba(0,0,0,0.07)", "grid": "rgba(0,0,0,0.05)",
}
ACCENT = "#2563EB"; ACCENT_SOFT = "#3B82F6"
POS = "#22C55E"; NEG = "#EF4444"; WARN = "#F59E0B"

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.stApp {background: var(--bg);}
.block-container {max-width: 1140px; padding-top: 1.0rem; padding-bottom: 5rem; margin: auto;}
[data-testid="stSidebar"] {background: var(--card); border-right: 1px solid var(--border);}

h1,h2,h3,h4, .stMarkdown, [data-testid="stWidgetLabel"] p, [data-testid="stCaptionContainer"],
div[role="radiogroup"] label p, .stButton > button, .stSelectbox, .stMultiSelect,
[data-baseweb="select"] * , .stCheckbox p, [data-testid="stMetricValue"] {
  font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif !important;
}
.stMarkdown p, .stMarkdown li {color: var(--text);}
[data-testid="stCaptionContainer"] p {color: var(--text2);}

::-webkit-scrollbar {width: 9px; height: 9px;}
::-webkit-scrollbar-thumb {background: var(--border2); border-radius: 99px;}
::-webkit-scrollbar-track {background: transparent;}

/* ---------- keyframes ---------- */
@keyframes lxfade {from {opacity: 0; transform: translateY(9px);} to {opacity: 1; transform: none;}}
.lx-fade {animation: lxfade .55s cubic-bezier(.21,.6,.35,1) both;}

/* ---------- floating glass navbar ---------- */
.st-key-topnav {position: sticky; top: 12px; z-index: 999; background: var(--navbg);
  backdrop-filter: blur(16px) saturate(1.4); -webkit-backdrop-filter: blur(16px) saturate(1.4);
  border: 1px solid var(--border); border-radius: 15px; padding: 8px 18px; box-shadow: var(--shadow);}
.lx-logo {display: flex; align-items: center; gap: 10px; white-space: nowrap;}
.lx-logo-mark {width: 12px; height: 12px; border-radius: 4px; background: #2563EB;
  box-shadow: 0 0 14px rgba(37,99,235,.55); flex: none;}
.lx-logo-name {font-size: 14.5px; font-weight: 700; letter-spacing: -0.01em; color: var(--text); font-family: Inter, sans-serif;}
.lx-logo-tag {font-size: 10px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase;
  color: var(--text3); border: 1px solid var(--border2); padding: 2px 8px; border-radius: 99px;}

/* ---------- radio -> pill nav ---------- */
div[role="radiogroup"] {display: flex; flex-wrap: wrap; gap: 6px;}
div[role="radiogroup"] label {background: transparent; border: 1px solid transparent; border-radius: 99px;
  padding: 5px 14px; margin: 0 !important; transition: all .18s ease; cursor: pointer;}
div[role="radiogroup"] label:hover {background: var(--hover); border-color: var(--border);}
div[role="radiogroup"] label:has(input:checked) {background: rgba(37,99,235,.13);
  border-color: rgba(37,99,235,.40);}
div[role="radiogroup"] label:has(input:checked) p {color: var(--text) !important;}
div[role="radiogroup"] label > div:first-child,
div[role="radiogroup"] label > div:first-of-type {display: none;}
div[role="radiogroup"] label input[type="radio"] {display: none;}
div[role="radiogroup"] label p {font-size: 13px; font-weight: 500; color: var(--text2); white-space: nowrap;}

/* ---------- buttons ---------- */
.stButton > button, .stDownloadButton > button {background: var(--card); color: var(--text);
  border: 1px solid var(--border2); border-radius: 10px; padding: .48rem 1.05rem;
  font-weight: 500; font-size: 13.5px; transition: all .18s ease; box-shadow: none;}
.stButton > button:hover {border-color: rgba(37,99,235,.55); background: rgba(37,99,235,.09);
  color: var(--text); transform: translateY(-1px);}
.stButton > button[kind="primary"] {background: #2563EB; border-color: #2563EB; color: #fff;}
.stButton > button[kind="primary"]:hover {background: #1D4ED8; border-color: #1D4ED8;}

/* ---------- inputs ---------- */
div[data-baseweb="select"] > div {background: var(--card) !important; border-color: var(--border2) !important;
  border-radius: 10px !important; color: var(--text) !important; font-size: 13.5px;}
div[data-baseweb="select"] svg {fill: var(--text2);}
div[data-baseweb="popover"] ul {background: var(--card) !important; border: 1px solid var(--border2) !important; border-radius: 12px !important;}
div[data-baseweb="popover"] li {color: var(--text) !important; background: transparent !important; font-size: 13.5px;}
div[data-baseweb="popover"] li:hover {background: rgba(37,99,235,.12) !important;}
.stCheckbox p, [data-testid="stWidgetLabel"] p {color: var(--text2) !important; font-size: 13px !important;}

/* ---------- cards ---------- */
.lx-card {background: var(--card); border: 1px solid var(--border); border-radius: 14px;
  padding: 20px 22px; transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
  animation: lxfade .55s cubic-bezier(.21,.6,.35,1) both;}
.lx-card:hover {transform: translateY(-2px); border-color: var(--border2); box-shadow: var(--shadow);}
.lx-card.flat:hover {transform: none; box-shadow: none;}

.lx-grid {display: grid; gap: 14px;}
.lx-grid.c2 {grid-template-columns: 1fr 1fr;}
.lx-grid.c3 {grid-template-columns: 1fr 1fr 1fr;}
.lx-grid > .lx-card:nth-child(2) {animation-delay: .06s;}
.lx-grid > .lx-card:nth-child(3) {animation-delay: .12s;}
.lx-grid > .lx-card:nth-child(4) {animation-delay: .18s;}
.lx-grid > .lx-card:nth-child(5) {animation-delay: .24s;}
.lx-grid > .lx-card:nth-child(6) {animation-delay: .30s;}
@media (max-width: 920px) {.lx-grid.c2, .lx-grid.c3 {grid-template-columns: 1fr;}}

/* ---------- hero ---------- */
.lx-hero {padding: 46px 0 8px;}
.lx-hero-month {font-size: 13px; color: #3B82F6; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;}
.lx-hero-title {font-size: 42px; font-weight: 750; letter-spacing: -0.022em; line-height: 1.12;
  color: var(--text); margin: 12px 0 14px; max-width: 850px;}
.lx-hero-sub {font-size: 16px; color: var(--text2); line-height: 1.7; max-width: 760px;}
@media (max-width: 700px) {.lx-hero-title {font-size: 30px;}}

/* ---------- section header ---------- */
.lx-sec {margin: 42px 0 16px; display: flex; align-items: baseline; gap: 14px;}
.lx-sec-num {font-size: 12px; color: #3B82F6; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: .08em;}
.lx-sec-title {font-size: 21px; font-weight: 650; letter-spacing: -0.015em; color: var(--text);}
.lx-sec-line {flex: 1; height: 1px; background: var(--border); align-self: center;}

/* ---------- KPI ---------- */
.lx-kpi-label {font-size: 11.5px; text-transform: uppercase; letter-spacing: .09em; color: var(--text2); font-weight: 600;}
.lx-kpi-value {font-size: 29px; font-weight: 700; letter-spacing: -0.01em; color: var(--text);
  margin-top: 7px; font-variant-numeric: tabular-nums;}
.lx-kpi-sub {font-size: 12.5px; color: var(--text2); margin-top: 5px;}

/* ---------- chips ---------- */
.lx-chip {display: inline-block; font-size: 11px; padding: 3px 10px; border-radius: 99px;
  font-weight: 600; letter-spacing: .02em; vertical-align: middle;}
.lx-chip.pos {background: rgba(34,197,94,.12); color: #22C55E;}
.lx-chip.neg {background: rgba(239,68,68,.12); color: #EF4444;}
.lx-chip.warn {background: rgba(245,158,11,.13); color: #F59E0B;}
.lx-chip.info {background: rgba(37,99,235,.13); color: #3B82F6;}
.lx-chip.muted {background: var(--hover); color: var(--text2); border: 1px solid var(--border);}

/* ---------- table ---------- */
.lx-table {width: 100%; border-collapse: collapse; font-size: 13px;}
.lx-table th {text-align: right; padding: 9px 12px; color: var(--text2); font-weight: 600;
  font-size: 11px; text-transform: uppercase; letter-spacing: .07em; border-bottom: 1px solid var(--border);}
.lx-table th:first-child, .lx-table td:first-child {text-align: left;}
.lx-table td {text-align: right; padding: 9.5px 12px; border-bottom: 1px solid var(--border);
  color: var(--text); font-variant-numeric: tabular-nums;}
.lx-table tr:last-child td {border-bottom: none;}
.lx-table tbody tr {transition: background .15s ease;}
.lx-table tbody tr:hover {background: var(--hover);}

/* ---------- timeline ---------- */
.lx-tl {position: relative; margin: 6px 0 6px 10px; padding-left: 30px;}
.lx-tl::before {content: ""; position: absolute; left: 0; top: 10px; bottom: 10px; width: 1px; background: var(--border2);}
.lx-tl-item {position: relative; padding: 4px 0 22px;}
.lx-tl-item::before {content: ""; position: absolute; left: -34.5px; top: 9px; width: 8px; height: 8px;
  border-radius: 50%; background: var(--bg); border: 2px solid #2563EB;}
.lx-tl-date {font-size: 11.5px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: #3B82F6;}
.lx-tl-head {font-size: 14.5px; font-weight: 600; color: var(--text); margin: 4px 0 2px;}
.lx-tl-afp {font-size: 12px; color: var(--text2); margin: 3px 0; font-variant-numeric: tabular-nums;}
.lx-tl-afp b {color: var(--text); font-weight: 600;}
.lx-tl-body {font-size: 13px; color: var(--text2); line-height: 1.62; max-width: 720px;}

/* ---------- risk banner ---------- */
.lx-risk {border-left: 3px solid #F59E0B; border-radius: 10px; background: var(--card);
  border-top: 1px solid var(--border); border-right: 1px solid var(--border); border-bottom: 1px solid var(--border);
  padding: 15px 18px; margin-bottom: 10px; animation: lxfade .5s ease both;}
.lx-risk.high {border-left-color: #EF4444;}
.lx-risk.low {border-left-color: #3B82F6;}
.lx-risk-title {font-size: 13.5px; font-weight: 650; color: var(--text); margin-bottom: 3px;}
.lx-risk-body {font-size: 13px; color: var(--text2); line-height: 1.6;}

/* ---------- outlook / conclusion ---------- */
.lx-outlook {border: 1px solid rgba(37,99,235,.32); border-radius: 16px; padding: 28px 30px;
  background: linear-gradient(180deg, rgba(37,99,235,.075), rgba(37,99,235,0) 55%), var(--card);
  animation: lxfade .6s ease both;}
.lx-bar {height: 6px; border-radius: 99px; background: var(--hover); border: 1px solid var(--border); overflow: hidden; margin-top: 8px;}
.lx-bar-fill {height: 100%; border-radius: 99px; background: linear-gradient(90deg, #2563EB, #3B82F6);
  transition: width 1s cubic-bezier(.2,.7,.3,1);}
.lx-mini-label {font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: var(--text3); font-weight: 650;}

/* ---------- news / misc ---------- */
.lx-news-head {font-size: 15px; font-weight: 600; line-height: 1.45; letter-spacing: -0.005em;}
.lx-news-head a {color: var(--text); text-decoration: none; transition: color .15s ease;}
.lx-news-head a:hover {color: #3B82F6;}
.lx-meta {font-size: 12px; color: var(--text3); margin: 5px 0 8px;}
.lx-body {font-size: 13.5px; color: var(--text2); line-height: 1.66;}
.lx-divider {height: 1px; background: var(--border); margin: 34px 0; border: none;}
.lx-footer {margin-top: 70px; padding-top: 22px; border-top: 1px solid var(--border);
  font-size: 12px; color: var(--text3); text-align: center; line-height: 1.8;}
a.lx-src {color: #3B82F6; text-decoration: none; font-size: 13px;}
a.lx-src:hover {text-decoration: underline;}
"""


def inject_css():
    t = LIGHT if st.session_state.get("light") else DARK
    root = (":root {" + "".join(
        f"--{k}: {v};" for k, v in
        [("bg", t["bg"]), ("card", t["card"]), ("card2", t["card2"]),
         ("border", t["border"]), ("border2", t["border2"]), ("text", t["text"]),
         ("text2", t["text2"]), ("text3", t["text3"]), ("navbg", t["navbg"]),
         ("hover", t["hover"]), ("shadow", t["shadow"])]) + "}")
    st.markdown(f"<style>{root}\n{BASE_CSS}</style>", unsafe_allow_html=True)
    return t


# ============================ DATA LAYER =================================

@st.cache_data(ttl=60 * 60, show_spinner=False)
def load_history(ticker: str, months_back: int = 26) -> pd.DataFrame:
    """Daily OHLC history with retries (Yahoo occasionally rate-limits)."""
    start = (dt.date.today() - dt.timedelta(days=months_back * 31)).isoformat()
    for attempt in range(3):
        try:
            df = yf.download(ticker, start=start, interval="1d",
                             progress=False, auto_adjust=False, threads=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                cols = [c for c in ["Open", "High", "Low", "Close"] if c in df.columns]
                out = df[cols].dropna(subset=["Close"])
                return out
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return pd.DataFrame()


def monthly_summary(df: pd.DataFrame, usd_is_base: bool) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    for (year, month), sub in df.groupby([df.index.year, df.index.month]):
        c = sub["Close"]
        first, last = float(c.iloc[0]), float(c.iloc[-1])
        pct = (last / first - 1) * 100
        hi = float(sub["High"].max()) if "High" in sub else float(c.max())
        lo = float(sub["Low"].min()) if "Low" in sub else float(c.min())
        usd_dir = ("stronger" if pct > 0 else "weaker") if usd_is_base else \
                  ("weaker" if pct > 0 else "stronger")
        rows.append({"Month": f"{year}-{month:02d}", "Open": first, "Close": last,
                     "Change %": round(pct, 2), "High": hi, "Low": lo, "USD ended": usd_dir})
    return pd.DataFrame(rows).sort_values("Month", ascending=False).reset_index(drop=True)


def month_label(ym: str) -> str:
    y, m = ym.split("-")
    return f"{calendar.month_name[int(m)]} {y}"


def fmt_price(v, dp) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    return f"{v:,.0f}" if dp == 0 else f"{v:,.{dp}f}"


# ---- news (Finnhub) ----
TAG_RE = re.compile(r"<[^>]+>")

def clean_html(raw: str, max_len: int = 380) -> str:
    """Finnhub summaries sometimes contain raw HTML -- strip to clean text."""
    if not raw:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].rstrip(",.;:") + " …"
    return text


@st.cache_data(ttl=15 * 60, show_spinner=False)
def load_news(category: str = "forex", limit: int = 25) -> dict:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return {"error": "no_key"}
    try:
        resp = requests.get("https://finnhub.io/api/v1/news",
                            params={"category": category, "token": key}, timeout=15)
        resp.raise_for_status()
        return {"items": resp.json()[:limit]}
    except Exception as e:
        return {"error": str(e)}


# ---- US macro (FRED) ----
@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def load_us_macro(months: int = 20) -> dict:
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return {"error": "no_key"}
    start = (dt.date.today() - dt.timedelta(days=months * 31)).isoformat()
    out = {}
    for label, sid in FRED_SERIES.items():
        try:
            resp = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={"series_id": sid, "api_key": key, "file_type": "json",
                        "observation_start": start, "sort_order": "asc"},
                timeout=15)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            out[label] = [(o["date"][:7], o["value"]) for o in obs
                          if o.get("value") not in (".", "", None)]
        except Exception:
            out[label] = []
    return {"data": out}


def macro_to_text(macro: dict) -> str:
    if macro.get("error") == "no_key":
        return "(no US economic data -- FRED key not set)"
    lines = []
    for label, series in macro.get("data", {}).items():
        if series:
            lines.append(f"{label} -> " + ", ".join(f"{d}: {v}" for d, v in series[-8:]))
    return "\n".join(lines) or "(no US economic data returned)"


# ============================ TECHNICALS =================================

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / down)   # down==0, up>0 -> inf -> RSI 100
    return rsi.fillna(50.0)             # 0/0 (flat) -> neutral 50


def compute_technicals(df: pd.DataFrame, ym: str, dp: int) -> dict:
    """Indicator readout as of the END of the selected month."""
    end = pd.Period(ym).end_time
    d = df[df.index <= end]
    if len(d) < 30:
        return {}
    c = d["Close"]
    px = float(c.iloc[-1])

    rsi_series = _rsi(c)
    rsi = float(rsi_series.iloc[-1])
    rsi_state = ("Overbought" if rsi >= 70 else "Bullish momentum" if rsi >= 55 else
                 "Neutral" if rsi >= 45 else "Bearish momentum" if rsi >= 30 else "Oversold")

    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    h0, h1 = float(hist.iloc[-1]), float(hist.iloc[-2])
    if h0 > 0:
        macd_state = "Bullish — MACD above signal" + (", histogram expanding" if h0 > h1 else ", momentum fading")
    else:
        macd_state = "Bearish — MACD below signal" + (", histogram expanding" if h0 < h1 else ", momentum fading")

    smas = {}
    for n in (20, 50, 200):
        smas[n] = float(c.rolling(n).mean().iloc[-1]) if len(c) >= n else None
    ma_bits = [f"{'Above' if smas[n] and px > smas[n] else 'Below'} SMA{n}"
               for n in (20, 50, 200) if smas[n]]

    mom3 = (px / float(c.iloc[-63]) - 1) * 100 if len(c) >= 63 else 0.0
    pts = sum([bool(smas[50]) and px > smas[50],
               bool(smas[200]) and px > smas[200],
               bool(smas[50]) and bool(smas[200]) and smas[50] > smas[200],
               mom3 > 0])
    trend = "Uptrend" if pts >= 3 else "Downtrend" if pts <= 1 else "Sideways / transitional"

    # market structure: last 3 monthly highs & lows
    mm = d.groupby([d.index.year, d.index.month]).agg(
        H=("High", "max") if "High" in d else ("Close", "max"),
        L=("Low", "min") if "Low" in d else ("Close", "min"))
    structure = "Range-bound / mixed"
    if len(mm) >= 3:
        H, L = mm["H"].iloc[-3:].tolist(), mm["L"].iloc[-3:].tolist()
        if H[2] > H[1] > H[0] and L[2] > L[1] > L[0]:
            structure = "Higher highs · higher lows (bullish)"
        elif H[2] < H[1] < H[0] and L[2] < L[1] < L[0]:
            structure = "Lower highs · lower lows (bearish)"
        elif L[2] > L[1] and H[2] < H[1]:
            structure = "Compression — range tightening"

    # support / resistance: classic monthly pivots + 3-month extremes
    m = d[(d.index >= pd.Period(ym).start_time) & (d.index <= end)]
    hi = float(m["High"].max()) if "High" in m else float(m["Close"].max())
    lo = float(m["Low"].min()) if "Low" in m else float(m["Close"].min())
    cl = float(m["Close"].iloc[-1])
    P = (hi + lo + cl) / 3
    rng = hi - lo
    q = d.iloc[-66:] if len(d) >= 66 else d
    q_hi = float(q["High"].max()) if "High" in q else float(q["Close"].max())
    q_lo = float(q["Low"].min()) if "Low" in q else float(q["Close"].min())
    levels = sorted([
        ("R2 (pivot)", P + rng), ("R1 (pivot)", 2 * P - lo), ("Monthly pivot", P),
        ("S1 (pivot)", 2 * P - hi), ("S2 (pivot)", P - rng),
        ("3-month high", q_hi), ("3-month low", q_lo),
    ], key=lambda x: -x[1])

    return {"px": px, "rsi": rsi, "rsi_state": rsi_state,
            "macd": float(macd_line.iloc[-1]), "macd_signal": float(signal.iloc[-1]),
            "macd_hist": h0, "macd_state": macd_state, "smas": smas, "ma_bits": ma_bits,
            "trend": trend, "mom3": mom3, "structure": structure, "levels": levels, "dp": dp}


def technicals_to_text(t: dict) -> str:
    if not t:
        return "(insufficient history for indicators)"
    sma_txt = ", ".join(f"SMA{n}={fmt_price(v, t['dp'])}" for n, v in t["smas"].items() if v)
    lv_txt = "; ".join(f"{n}={fmt_price(v, t['dp'])}" for n, v in t["levels"])
    return (f"Close={fmt_price(t['px'], t['dp'])} | Trend: {t['trend']} (3m momentum {t['mom3']:+.2f}%) | "
            f"RSI14={t['rsi']:.1f} ({t['rsi_state']}) | MACD={t['macd']:+.5f} vs signal {t['macd_signal']:+.5f} "
            f"({t['macd_state']}) | {sma_txt} | Structure: {t['structure']} | Key levels: {lv_txt}")


# ============================ AI RESEARCH ================================

REPORT_SCHEMA = """{
 "headline": "bank-style report title, <= 12 words, no pair prefix",
 "executive_summary": "120-170 word past-tense review of the month for this pair",
 "macro_drivers": [3-5 items: {"country_code":"US","title":"...","impact":"bullish|bearish|mixed","analysis":"1-3 sentences, causal"}],
 "key_events": [4-8 items, chronological: {"date":"Jun 18","country_code":"US","event":"FOMC decision","actual":"","forecast":"","previous":"","impact":"high|medium|low","analysis":"1-2 sentences on the market reaction"}],
 "fundamental_view": "3-5 sentences: policy divergence, rates, inflation, growth",
 "technical_view": "3-5 sentences grounded in the indicator readout provided",
 "sentiment_view": "3-5 sentences: positioning, risk appetite, prevailing narrative",
 "risk_factors": [2-4 items: {"title":"...","detail":"1-2 sentences","severity":"high|medium|low"}],
 "outlook": {"bias":"Bullish|Neutral|Bearish","confidence":55,"narrative":"4-6 sentence forward view for next month","key_drivers":["...","..."],"next_month_risks":["...","..."]}
}"""


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def generate_report(pair: str, ym: str, price_ctx: str, tech_ctx: str,
                    macro_ctx: str, news_ctx: str, use_search: bool) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"error": "no_key"}
    try:
        from anthropic import Anthropic
        client = Anthropic()
        label = month_label(ym)
        if use_search:
            source_instr = ("Use web search to verify the actual dated events of this month for this pair "
                            "(central-bank decisions, CPI/NFP prints, geopolitical shocks) and fill in real "
                            "actual/forecast/previous figures where you find them.")
        else:
            source_instr = ("No web access: derive events from the provided data matrices and well-known "
                            "recurring calendar patterns (FOMC, CPI, NFP weeks). Only include events you are "
                            "confident about; leave actual/forecast/previous as \"\" when unsure. Do not invent figures.")
        prompt = (
            f"You are a senior macro FX strategist at a global investment bank writing the monthly research "
            f"report on {pair} for {label}. Analyze the month through three lenses: FUNDAMENTAL (central bank "
            f"policy, rate differentials, inflation, growth, employment), TECHNICAL (use the indicator readout "
            f"provided; discuss trend, momentum and key levels), and SENTIMENT (positioning, risk appetite, "
            f"dominant market narrative).\n\n{source_instr}\n\n"
            f"Respond with ONLY one valid JSON object -- no markdown fences, no commentary -- exactly this schema:\n"
            f"{REPORT_SCHEMA}\n\n"
            f"Rules: \"bias\" is the direction of {pair} itself next month. \"confidence\" is an integer 0-100. "
            f"Event dates must fall inside {label}. country_code is ISO-2 (US, EU, GB, AU, NZ, ID...). "
            f"Be specific and causal; institutional tone; no filler. "
            f"NEVER put <cite> tags, citation markers, footnotes or URLs inside JSON strings. "
            f"Write no prose before or after the JSON object.\n\n"
            f"PRICE ACTION MATRIX (monthly):\n{price_ctx}\n\n"
            f"TECHNICAL READOUT (as of {label} close):\n{tech_ctx}\n\n"
            f"US MACRO DATA (FRED):\n{macro_ctx}\n\n"
            f"RECENT MARKET HEADLINES (sentiment context):\n{news_ctx or '(none provided)'}"
        )
        kwargs = dict(model="claude-haiku-4-5-20251001", max_tokens=8000,
                      messages=[{"role": "user", "content": prompt}])
        if use_search:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
        msg = client.messages.create(**kwargs)

        text_parts, sources, seen = [], [], set()
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
                for c in (getattr(block, "citations", None) or []):
                    url = getattr(c, "url", None)
                    if url and url not in seen:
                        seen.add(url)
                        sources.append((getattr(c, "title", None) or url, url))
        raw = "".join(text_parts).strip()
        return {"report": _extract_json(raw), "raw": raw, "sources": sources}
    except Exception as e:
        return {"error": str(e)}


CITE_RE = re.compile(r"</?cite[^>]*>")

def _clean_strings(obj):
    """Remove citation tags / collapse whitespace in every string of the report."""
    if isinstance(obj, str):
        return re.sub(r"\s+", " ", CITE_RE.sub("", obj)).strip()
    if isinstance(obj, list):
        return [_clean_strings(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _clean_strings(v) for k, v in obj.items()}
    return obj


def _close_open(chunk: str) -> str:
    """Close any unterminated string and unbalanced braces/brackets."""
    stack, in_str, esc = [], False, False
    for ch in chunk:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    if in_str:
        chunk += '"'
    chunk = re.sub(r"[,:\s]+$", "", chunk)
    return chunk + "".join(reversed(stack))


def _repair_json(chunk: str):
    """Best-effort parse of truncated JSON: close it, else chop back and retry."""
    for _ in range(60):
        try:
            return json.loads(_close_open(chunk))
        except Exception:
            cut = max(chunk.rfind(","), chunk.rfind("{"), chunk.rfind("["))
            if cut <= 0:
                return None
            chunk = chunk[:cut]
    return None


def _extract_json(text: str):
    # cite tags (from web-search citations) can carry raw quotes that break JSON:
    # strip them from the raw text BEFORE parsing.
    text = CITE_RE.sub("", re.sub(r"```(?:json)?", "", text))
    s = text.find("{")
    if s == -1:
        return None
    e = text.rfind("}")
    if e > s:
        chunk = text[s:e + 1]
        for candidate in (chunk, re.sub(r",\s*([}\]])", r"\1", chunk)):
            try:
                return _clean_strings(json.loads(candidate))
            except Exception:
                pass
    repaired = _repair_json(text[s:])
    return _clean_strings(repaired) if repaired is not None else None


# ============================ UI COMPONENTS ==============================

esc = html_lib.escape

def H(*parts) -> None:
    """Render compact HTML (joined, no blank lines -- keeps markdown parser quiet)."""
    st.markdown("".join(parts), unsafe_allow_html=True)


def section(num: str, title: str) -> None:
    H(f'<div class="lx-sec"><span class="lx-sec-num">{num}</span>'
      f'<span class="lx-sec-title">{esc(title)}</span><span class="lx-sec-line"></span></div>')


def chg_chip(pct, suffix="") -> str:
    cls = "pos" if pct > 0 else "neg" if pct < 0 else "muted"
    return f'<span class="lx-chip {cls}">{pct:+.2f}%{esc(suffix)}</span>'


IMPACT_CLS = {"bullish": "pos", "bearish": "neg", "mixed": "warn",
              "high": "neg", "medium": "warn", "low": "info"}

def impact_chip(v: str) -> str:
    v = (v or "").lower()
    return f'<span class="lx-chip {IMPACT_CLS.get(v, "muted")}">{esc(v or "n/a")}</span>'


def kpi_cards(items) -> None:
    cards = "".join(
        f'<div class="lx-card"><div class="lx-kpi-label">{esc(lb)}</div>'
        f'<div class="lx-kpi-value">{val}</div><div class="lx-kpi-sub">{sub}</div></div>'
        for lb, val, sub in items)
    H(f'<div class="lx-grid c3">{cards}</div>')


def sparkline_svg(closes, w=260, h=46, color="#3B82F6") -> str:
    if len(closes) < 2:
        return ""
    lo, hi = min(closes), max(closes)
    rng = (hi - lo) or 1e-9
    pts = [(i / (len(closes) - 1) * w, h - 4 - (v - lo) / rng * (h - 8))
           for i, v in enumerate(closes)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{h} " + line + f" {w},{h}"
    return (f'<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<polygon points="{area}" fill="{color}" opacity="0.08"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/></svg>')


def price_chart(df: pd.DataFrame, ym: str, dp: int, theme: dict, months_window: int) -> go.Figure:
    end = df.index.max()
    start = end - pd.DateOffset(months=months_window)
    d = df[df.index >= start]
    c = d["Close"]
    fig = go.Figure()
    for n, col, dash in ((20, "rgba(161,161,170,0.75)", "dot"), (50, "rgba(245,158,11,0.55)", "dot")):
        if len(df) >= n:
            sma = df["Close"].rolling(n).mean().reindex(d.index)
            fig.add_trace(go.Scatter(x=d.index, y=sma, name=f"SMA {n}", mode="lines",
                                     line=dict(color=col, width=1, dash=dash), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=d.index, y=c, name="Close", mode="lines",
                             line=dict(color="#3B82F6", width=2.1)))
    p = pd.Period(ym)
    if p.start_time <= end:
        fig.add_vrect(x0=p.start_time, x1=min(p.end_time, end), fillcolor="rgba(37,99,235,0.07)",
                      line_width=0)
    tickfmt = ",.0f" if dp == 0 else f".{dp}f"
    fig.update_layout(
        height=420, margin=dict(l=8, r=8, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color=theme["text2"]),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=theme["card"], bordercolor=theme["border2"],
                        font=dict(family="Inter, sans-serif", size=12, color=theme["text"])),
        legend=dict(orientation="h", y=1.06, x=0, font=dict(size=11)),
        xaxis=dict(showgrid=False, linecolor=theme["grid"], tickfont=dict(size=11)),
        yaxis=dict(gridcolor=theme["grid"], zeroline=False, tickformat=tickfmt,
                   tickfont=dict(size=11), side="right"),
    )
    return fig


def summary_table(summary: pd.DataFrame, dp: int, rows: int = 6) -> None:
    body = ""
    for _, r in summary.head(rows).iterrows():
        body += (f"<tr><td>{month_label(r['Month'])}</td>"
                 f"<td>{fmt_price(r['Open'], dp)}</td><td>{fmt_price(r['Close'], dp)}</td>"
                 f"<td>{chg_chip(r['Change %'])}</td>"
                 f"<td>{fmt_price(r['High'], dp)}</td><td>{fmt_price(r['Low'], dp)}</td>"
                 f"<td>USD {esc(r['USD ended'])}</td></tr>")
    H('<div class="lx-card flat" style="padding:8px 6px;">',
      '<table class="lx-table"><thead><tr><th>Month</th><th>Open</th><th>Close</th>',
      '<th>Change</th><th>High</th><th>Low</th><th>USD</th></tr></thead>',
      f'<tbody>{body}</tbody></table></div>')


def footer() -> None:
    H('<div class="lx-footer">FX Monthly Tracker — personal research dashboard · ',
      'Prices: Yahoo Finance · News: Finnhub · Macro: FRED · Analysis: Claude (Anthropic)<br>',
      'For research and educational purposes only. Not investment advice.</div>')


# ============================ NAVBAR / STATE =============================

EXTRA_CSS = """
.st-key-chartcard {background: var(--card); border: 1px solid var(--border); border-radius: 14px;
  padding: 16px 14px 6px; transition: border-color .2s ease;}
.st-key-chartcard:hover {border-color: var(--border2);}
.st-key-aipanel {background: var(--card2); border: 1px solid var(--border); border-radius: 14px; padding: 18px 20px;}
"""
BASE_CSS = BASE_CSS + EXTRA_CSS

VIEWS = ["Reports", "Dashboard", "Archive", "News", "About"]


def goto(view: str, pair: str = None, month: str = None):
    st.session_state["nav"] = view
    if pair:
        st.session_state["pair"] = pair
    if pair and month:
        st.session_state[f"month-{pair}"] = month


def keyed_container(key: str):
    try:
        return st.container(key=key)
    except TypeError:
        return st.container()


def navbar():
    with keyed_container("topnav"):
        try:
            c1, c2, c3 = st.columns([2.4, 4.6, 1.0], vertical_alignment="center")
        except TypeError:
            c1, c2, c3 = st.columns([2.4, 4.6, 1.0])
        with c1:
            H('<div class="lx-logo"><span class="lx-logo-mark"></span>',
              '<span class="lx-logo-name">FX Monthly Tracker</span>',
              '<span class="lx-logo-tag">Research</span></div>')
        with c2:
            st.radio("nav", VIEWS, key="nav", horizontal=True, label_visibility="collapsed")
        with c3:
            st.toggle("Light", key="light")


def sidebar():
    with st.sidebar:
        H('<div style="font-size:13px;font-weight:650;color:var(--text);margin:6px 0 10px;">Data sources</div>')
        rows = [("Prices · Yahoo Finance", True),
                ("News · Finnhub", bool(os.environ.get("FINNHUB_API_KEY"))),
                ("US data · FRED", bool(os.environ.get("FRED_API_KEY"))),
                ("AI · Anthropic", bool(os.environ.get("ANTHROPIC_API_KEY")))]
        items = "".join(
            '<div style="display:flex;align-items:center;gap:9px;padding:7px 0;'
            'font-size:12.5px;color:var(--text2);">'
            f'<span style="width:7px;height:7px;border-radius:50%;flex:none;'
            f'background:{POS if ok else NEG};box-shadow:0 0 8px {POS if ok else NEG}66;"></span>'
            f'{esc(name)} · {"connected" if ok else "not set"}</div>'
            for name, ok in rows)
        H(items)


# ============================ VIEWS ======================================

def data_error_card(pair: str):
    H('<div class="lx-card flat" style="margin-top:24px;">',
      '<span class="lx-chip warn">data</span>',
      f'<div class="lx-news-head" style="margin-top:10px;">Could not load {esc(pair)} prices</div>',
      '<div class="lx-body" style="margin-top:6px;">Yahoo Finance is temporarily rate-limiting. '
      'Wait a minute, then retry.</div></div>')
    if st.button("Retry", key=f"retry-{pair}"):
        load_history.clear()
        st.rerun()


def view_reports(theme):
    top1, top2 = st.columns([3.2, 1.1])
    with top1:
        st.radio("pair", list(PAIRS), key="pair", horizontal=True, label_visibility="collapsed")
    pair = st.session_state["pair"]
    cfg = PAIRS[pair]

    with st.spinner(f"Loading {pair} prices…"):
        df = load_history(cfg["ticker"])
    if df.empty:
        data_error_card(pair)
        return
    summary = monthly_summary(df, cfg["usd_is_base"])
    months = summary["Month"].tolist()
    cur_ym = dt.date.today().strftime("%Y-%m")
    default_idx = 1 if (months and months[0] == cur_ym and len(months) > 1) else 0
    with top2:
        ym = st.selectbox("month", months, index=default_idx, key=f"month-{pair}",
                          format_func=month_label, label_visibility="collapsed")

    row = summary[summary["Month"] == ym].iloc[0]
    dp = cfg["dp"]
    tech = compute_technicals(df, ym, dp)
    rk = f"{pair}|{ym}"
    res = st.session_state["reports"].get(rk)
    rep = (res or {}).get("report") if isinstance(res, dict) else None

    # ---------- hero ----------
    usd_dir = row["USD ended"]
    if rep and rep.get("headline"):
        title = rep["headline"]
    else:
        moved = "Climbs" if row["Change %"] > 0 else "Slips" if row["Change %"] < 0 else "Holds Flat"
        title = f"{pair} {moved} {abs(row['Change %']):.2f}% — Dollar Ends the Month {usd_dir.capitalize()}"
    summary_txt = (rep or {}).get("executive_summary") or (
        "Generate the AI research below to produce this month's executive summary — a "
        "fundamental, technical and sentiment deep-dive written by Claude from live "
        "price, macro and news data.")
    sub_style = "" if rep else ' style="color:var(--text3);font-style:italic;"'
    H('<div class="lx-hero lx-fade">',
      f'<div class="lx-hero-month">{cfg["flag"]}&nbsp; {esc(pair)} — {esc(month_label(ym))}</div>',
      f'<div class="lx-hero-title">{esc(title)}</div>',
      f'<div class="lx-hero-sub"{sub_style}>{esc(summary_txt)}</div></div>')

    ret_color = POS if row["Change %"] > 0 else NEG if row["Change %"] < 0 else theme["text"]
    kpi_cards([
        (f"{pair} return", f'<span style="color:{ret_color};">{row["Change %"]:+.2f}%</span>',
         f"USD ended {usd_dir} · close {fmt_price(row['Close'], dp)}"),
        ("Highest", fmt_price(row["High"], dp), "intramonth extreme"),
        ("Lowest", fmt_price(row["Low"], dp), "intramonth extreme"),
    ])

    # ---------- 01 price action ----------
    section("01", "Price Action")
    rng_cols = st.columns([2.6, 2.4])
    with rng_cols[0]:
        rng = st.radio("range", ["3M", "6M", "1Y", "2Y"], index=1, horizontal=True,
                       label_visibility="collapsed", key="rng")
    win = {"3M": 3, "6M": 6, "1Y": 12, "2Y": 24}[rng]
    with keyed_container("chartcard"):
        st.plotly_chart(price_chart(df, ym, dp, theme, win), theme=None,
                        config={"displayModeBar": False})

    # ---------- 02 monthly summary ----------
    section("02", "Monthly Summary")
    summary_table(summary, dp)

    # ---------- 03 technicals ----------
    section("03", "Technical Analysis")
    if not tech:
        H('<div class="lx-body">Not enough history for indicators.</div>')
    else:
        rsi_pct = max(0, min(100, tech["rsi"]))
        ma_rows = "".join(
            f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;">'
            f'<span style="color:var(--text2);">SMA {n}</span>'
            f'<span style="font-variant-numeric:tabular-nums;color:var(--text);">{fmt_price(v, dp)} '
            f'<span class="lx-chip {"pos" if tech["px"] > v else "neg"}" style="margin-left:6px;">'
            f'{"above" if tech["px"] > v else "below"}</span></span></div>'
            for n, v in tech["smas"].items() if v)
        trend_cls = "pos" if tech["trend"] == "Uptrend" else "neg" if tech["trend"] == "Downtrend" else "warn"
        macd_cls = "pos" if tech["macd_hist"] > 0 else "neg"
        cards = [
            ('Trend', f'<span class="lx-chip {trend_cls}">{esc(tech["trend"])}</span>',
             f'3-month momentum {tech["mom3"]:+.2f}% · price {fmt_price(tech["px"], dp)}'),
            ('RSI (14)', f'{tech["rsi"]:.1f} <span class="lx-chip info" style="margin-left:8px;">{esc(tech["rsi_state"])}</span>',
             f'<div class="lx-bar"><div class="lx-bar-fill" style="width:{rsi_pct:.0f}%;"></div></div>'),
            ('MACD (12·26·9)', f'<span class="lx-chip {macd_cls}">{esc(tech["macd_state"])}</span>',
             f'MACD {tech["macd"]:+.5f} · signal {tech["macd_signal"]:+.5f}'),
            ('Moving Averages', ma_rows, ''),
            ('Market Structure', f'<span style="font-size:15.5px;font-weight:600;">{esc(tech["structure"])}</span>',
             'last three monthly swings'),
            ('Monthly Range', f'{fmt_price(row["Low"], dp)} — {fmt_price(row["High"], dp)}',
             f'range width {((row["High"] / row["Low"]) - 1) * 100:.2f}%'),
        ]
        grid = "".join(
            f'<div class="lx-card"><div class="lx-kpi-label">{lb}</div>'
            f'<div style="margin-top:10px;font-size:15px;color:var(--text);">{val}</div>'
            f'<div class="lx-kpi-sub" style="margin-top:8px;">{sub}</div></div>'
            for lb, val, sub in cards)
        H(f'<div class="lx-grid c3">{grid}</div>')

        # ---------- 04 support & resistance ----------
        section("04", "Support & Resistance")
        lv_rows = ""
        for name, v in tech["levels"]:
            dist = (v / tech["px"] - 1) * 100
            kind = ("info", "resistance") if v > tech["px"] else ("warn", "support")
            lv_rows += (f'<tr><td>{esc(name)}</td>'
                        f'<td><span class="lx-chip {kind[0]}">{kind[1]}</span></td>'
                        f'<td>{fmt_price(v, dp)}</td><td>{chg_chip(dist, " from close")}</td></tr>')
        H('<div class="lx-card flat" style="padding:8px 6px;">',
          '<table class="lx-table"><thead><tr><th>Level</th><th>Type</th><th>Price</th>',
          '<th>Distance</th></tr></thead>', f'<tbody>{lv_rows}</tbody></table></div>')

    # ---------- AI research ----------
    render_ai_research(pair, cfg, ym, summary, tech, res, rep)
    footer()


def render_ai_research(pair, cfg, ym, summary, tech, res, rep):
    section("05", "AI Research — Fundamental · Technical · Sentiment")
    with keyed_container("aipanel"):
        c1, c2 = st.columns([3.4, 1.6])
        with c1:
            use_search = st.checkbox(
                "Search the web for verified event data (~10–15c per report vs ~1c without)",
                value=False, key=f"srch-{pair}-{ym}")
        with c2:
            clicked = st.button("Generate research →", type="primary",
                                key=f"gen-{pair}-{ym}", width="stretch")
    if clicked:
        with st.spinner("Running macro research — fundamental, technical, sentiment…"):
            macro = load_us_macro()
            idx = summary.index[summary["Month"] == ym].tolist()
            i = idx[0] if idx else 0
            price_ctx = summary.iloc[max(0, i - 1): i + 5].to_string(index=False)
            news_ctx = ""
            if ym >= (dt.date.today() - dt.timedelta(days=62)).strftime("%Y-%m"):
                news = load_news("forex")
                news_ctx = "\n".join("- " + (n.get("headline") or "")
                                     for n in news.get("items", [])[:10])
            args = (pair, ym, price_ctx, technicals_to_text(tech),
                    macro_to_text(macro), news_ctx, use_search)
            prev = st.session_state["reports"].get(f"{pair}|{ym}")
            if isinstance(prev, dict) and (prev.get("error") or not prev.get("report")):
                try:            # last attempt failed -> bypass the 24h cache and retry fresh
                    generate_report.clear(*args)
                except Exception:
                    generate_report.clear()
            result = generate_report(*args)
        st.session_state["reports"][f"{pair}|{ym}"] = result
        st.rerun()

    if res is None:
        H('<div class="lx-body" style="margin-top:14px;color:var(--text3);">',
          'The generated report adds: macro drivers, an economic-event timeline, research views, ',
          'risk factors and a monthly outlook with bias &amp; confidence.</div>')
        return
    if res.get("error") == "no_key":
        st.info("Add your ANTHROPIC_API_KEY to enable AI research.")
        return
    if "error" in res:
        st.error(f"AI error: {res['error']}")
        return
    if rep is None:
        st.warning("The model reply could not be parsed into a report — raw output below. "
                   "Click Generate research again to retry.")
        st.markdown(CITE_RE.sub("", res.get("raw", "")))
        return

    n = 6
    # ---- macro drivers ----
    drivers = rep.get("macro_drivers") or []
    if drivers:
        section(f"{n:02d}", "Macro Drivers"); n += 1
        cards = "".join(
            '<div class="lx-card">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">'
            f'<div style="font-size:14.5px;font-weight:650;color:var(--text);">'
            f'{FLAGS.get((d.get("country_code") or "GL").upper(), "🌐")}&nbsp; {esc(d.get("title") or "")}</div>'
            f'{impact_chip(d.get("impact"))}</div>'
            f'<div class="lx-body" style="margin-top:9px;">{esc(d.get("analysis") or "")}</div></div>'
            for d in drivers)
        H(f'<div class="lx-grid c2">{cards}</div>')

    # ---- economic calendar ----
    events = rep.get("key_events") or []
    if events:
        section(f"{n:02d}", "Economic Calendar"); n += 1
        items = ""
        for e in events:
            afp = ""
            vals = [("Actual", e.get("actual")), ("Forecast", e.get("forecast")),
                    ("Previous", e.get("previous"))]
            shown = [f"{k} <b>{esc(str(v))}</b>" for k, v in vals if v not in ("", None)]
            if shown:
                afp = f'<div class="lx-tl-afp">{" &nbsp;·&nbsp; ".join(shown)}</div>'
            items += ('<div class="lx-tl-item">'
                      f'<div class="lx-tl-date">{esc(e.get("date") or "")}</div>'
                      f'<div class="lx-tl-head">{FLAGS.get((e.get("country_code") or "GL").upper(), "🌐")}&nbsp; '
                      f'{esc(e.get("event") or "")} &nbsp;{impact_chip(e.get("impact"))}</div>'
                      f'{afp}'
                      f'<div class="lx-tl-body">{esc(e.get("analysis") or "")}</div></div>')
        H(f'<div class="lx-card flat"><div class="lx-tl">{items}</div></div>')

    # ---- research views ----
    views = [("Fundamental", rep.get("fundamental_view")),
             ("Technical", rep.get("technical_view")),
             ("Sentiment", rep.get("sentiment_view"))]
    views = [(a, b) for a, b in views if b]
    if views:
        section(f"{n:02d}", "Research Views"); n += 1
        cards = "".join(
            '<div class="lx-card">'
            f'<div class="lx-kpi-label" style="color:#3B82F6;">{lb}</div>'
            f'<div class="lx-body" style="margin-top:9px;color:var(--text);">{esc(tx)}</div></div>'
            for lb, tx in views)
        H(f'<div class="lx-grid c3">{cards}</div>')

    # ---- risks ----
    risks = rep.get("risk_factors") or []
    if risks:
        section(f"{n:02d}", "Risk Factors"); n += 1
        banners = "".join(
            f'<div class="lx-risk {esc((r.get("severity") or "medium").lower())}">'
            f'<div class="lx-risk-title">{esc(r.get("title") or "")} '
            f'{impact_chip(r.get("severity"))}</div>'
            f'<div class="lx-risk-body">{esc(r.get("detail") or "")}</div></div>'
            for r in risks)
        H(banners)

    # ---- outlook ----
    out = rep.get("outlook") or {}
    if out:
        section(f"{n:02d}", "Monthly Outlook"); n += 1
        bias = (out.get("bias") or "Neutral").capitalize()
        bias_cls = {"Bullish": "pos", "Bearish": "neg"}.get(bias, "muted")
        try:
            conf = int(out.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0
        conf = max(0, min(100, conf))
        dot = '<span style="color:#3B82F6;">●</span>&nbsp; '
        drivers_list = "".join(f'<div class="lx-body" style="padding:3px 0;">{dot}{esc(x)}</div>'
                               for x in (out.get("key_drivers") or []))
        risks_list = "".join(f'<div class="lx-body" style="padding:3px 0;">{dot}{esc(x)}</div>'
                             for x in (out.get("next_month_risks") or []))
        H('<div class="lx-outlook">',
          '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;">',
          f'<div><div class="lx-mini-label">Overall bias — next month</div>',
          f'<div style="font-size:30px;font-weight:750;letter-spacing:-0.02em;color:var(--text);margin-top:6px;">',
          f'{esc(bias)} <span class="lx-chip {bias_cls}" style="vertical-align:middle;margin-left:8px;">{esc(pair)}</span></div></div>',
          f'<div style="min-width:230px;"><div class="lx-mini-label">Confidence &nbsp;·&nbsp; {conf}/100</div>',
          f'<div class="lx-bar"><div class="lx-bar-fill" style="width:{conf}%;"></div></div></div></div>',
          f'<div class="lx-body" style="margin-top:18px;color:var(--text);font-size:14px;">{esc(out.get("narrative") or "")}</div>',
          '<div class="lx-grid c2" style="margin-top:20px;">',
          f'<div><div class="lx-mini-label" style="margin-bottom:8px;">Key drivers</div>{drivers_list}</div>',
          f'<div><div class="lx-mini-label" style="margin-bottom:8px;">Next month&#39;s risks</div>{risks_list}</div>',
          '</div></div>')

    # ---- references ----
    sources = res.get("sources") or []
    if sources:
        section(f"{n:02d}", "References")
        links = "".join(
            f'<div style="padding:6px 0;"><a class="lx-src" href="{esc(u)}" target="_blank" rel="noopener">'
            f'{esc(t)}</a></div>' for t, u in sources)
        H(f'<div class="lx-card flat">{links}</div>')
    H('<div class="lx-body" style="margin-top:14px;color:var(--text3);font-size:12px;">',
      'AI-generated research · verify key figures before relying on them. Reports are cached for 24h.</div>')


def view_dashboard(theme):
    H('<div class="lx-hero lx-fade" style="padding-bottom:4px;">',
      '<div class="lx-hero-month">Dashboard</div>',
      '<div class="lx-hero-title" style="font-size:34px;">Month-to-date across the board</div>',
      '<div class="lx-hero-sub">Live monthly performance for all tracked pairs. '
      'Open any pair to read its full research report.</div></div>')

    data = {}
    with st.spinner("Loading pairs…"):
        for pair, cfg in PAIRS.items():
            df = load_history(cfg["ticker"])
            if not df.empty:
                data[pair] = (df, monthly_summary(df, cfg["usd_is_base"]))
    if not data:
        data_error_card("market")
        return

    # KPI strip: DXY MTD + strongest / weakest currency vs USD
    cur_rows = {}
    for pair, (df, summ) in data.items():
        if pair == "DXY" or summ.empty:
            continue
        pct = summ.iloc[0]["Change %"]
        ccy = pair.split("/")[0] if not PAIRS[pair]["usd_is_base"] else pair.split("/")[1]
        cur_rows[ccy] = pct if not PAIRS[pair]["usd_is_base"] else -pct
    kpis = []
    if "DXY" in data and not data["DXY"][1].empty:
        r = data["DXY"][1].iloc[0]
        col = POS if r["Change %"] > 0 else NEG
        kpis.append(("DXY — " + month_label(r["Month"]),
                     f'<span style="color:{col};">{r["Change %"]:+.2f}%</span>',
                     f'close {fmt_price(r["Close"], 2)}'))
    if cur_rows:
        best = max(cur_rows, key=cur_rows.get)
        worst = min(cur_rows, key=cur_rows.get)
        kpis.append(("Strongest vs USD", f'<span style="color:{POS};">{esc(best)}</span>',
                     f"{cur_rows[best]:+.2f}% this month"))
        kpis.append(("Weakest vs USD", f'<span style="color:{NEG};">{esc(worst)}</span>',
                     f"{cur_rows[worst]:+.2f}% this month"))
    if kpis:
        kpi_cards(kpis[:3])
    H('<div style="height:10px;"></div>')

    pairs = list(data.keys())
    for row_start in range(0, len(pairs), 3):
        cols = st.columns(3)
        for col, pair in zip(cols, pairs[row_start:row_start + 3]):
            df, summ = data[pair]
            cfg = PAIRS[pair]
            r = summ.iloc[0]
            spark = sparkline_svg(df["Close"].iloc[-120:].tolist())
            with col:
                H('<div class="lx-card" style="margin-bottom:10px;">',
                  '<div style="display:flex;justify-content:space-between;align-items:center;">',
                  f'<div style="font-size:14px;font-weight:650;color:var(--text);">{cfg["flag"]}&nbsp; {esc(pair)}</div>',
                  chg_chip(r["Change %"]), '</div>',
                  f'<div style="font-size:11.5px;color:var(--text3);margin-top:2px;">{esc(cfg["name"])}</div>',
                  f'<div class="lx-kpi-value" style="font-size:25px;">{fmt_price(r["Close"], cfg["dp"])}</div>',
                  f'<div style="margin:10px 0 6px;">{spark}</div>',
                  '<div style="display:flex;justify-content:space-between;font-size:11.5px;color:var(--text2);">',
                  f'<span>H {fmt_price(r["High"], cfg["dp"])}</span><span>L {fmt_price(r["Low"], cfg["dp"])}</span>',
                  f'<span>USD {esc(r["USD ended"])}</span></div></div>')
                st.button("Open report →", key=f"open-{pair}", width="stretch",
                          on_click=goto, args=("Reports", pair))
        H('<div style="height:6px;"></div>')
    footer()


def view_archive(theme):
    H('<div class="lx-hero lx-fade" style="padding-bottom:4px;">',
      '<div class="lx-hero-month">Archive</div>',
      '<div class="lx-hero-title" style="font-size:34px;">Past monthly reports</div>',
      '<div class="lx-hero-sub">Every tracked month, per pair. Open one to view the full '
      'report and generate its AI research.</div></div>')
    st.radio("pair", list(PAIRS), key="pair", horizontal=True, label_visibility="collapsed")
    pair = st.session_state["pair"]
    cfg = PAIRS[pair]
    with st.spinner(f"Loading {pair}…"):
        df = load_history(cfg["ticker"])
    if df.empty:
        data_error_card(pair)
        return
    summ = monthly_summary(df, cfg["usd_is_base"])
    months = summ["Month"].tolist()
    for row_start in range(0, len(months), 3):
        cols = st.columns(3)
        for col, ym in zip(cols, months[row_start:row_start + 3]):
            r = summ[summ["Month"] == ym].iloc[0]
            done = f"{pair}|{ym}" in st.session_state["reports"]
            badge = '<span class="lx-chip info">report ready</span>' if done else ""
            with col:
                H('<div class="lx-card" style="margin-bottom:10px;">',
                  '<div style="display:flex;justify-content:space-between;align-items:center;">',
                  f'<div style="font-size:14.5px;font-weight:650;color:var(--text);">{esc(month_label(ym))}</div>',
                  chg_chip(r["Change %"]), '</div>',
                  f'<div style="font-size:12px;color:var(--text2);margin-top:8px;font-variant-numeric:tabular-nums;">',
                  f'O {fmt_price(r["Open"], cfg["dp"])} &nbsp;·&nbsp; C {fmt_price(r["Close"], cfg["dp"])} &nbsp;·&nbsp; '
                  f'H {fmt_price(r["High"], cfg["dp"])} &nbsp;·&nbsp; L {fmt_price(r["Low"], cfg["dp"])}</div>',
                  f'<div style="margin-top:8px;">{badge}</div></div>')
                st.button("Read →", key=f"arch-{pair}-{ym}", width="stretch",
                          on_click=goto, args=("Reports", pair, ym))
    footer()


def view_news(theme):
    H('<div class="lx-hero lx-fade" style="padding-bottom:4px;">',
      '<div class="lx-hero-month">Market News</div>',
      '<div class="lx-hero-title" style="font-size:34px;">Latest market headlines</div>',
      '<div class="lx-hero-sub">Wire headlines from Finnhub (free tier), cleaned and de-cluttered. '
      'Summaries are stripped of raw markup.</div></div>')
    st.radio("cat", ["forex", "general", "crypto", "merger"], key="newscat",
             horizontal=True, label_visibility="collapsed")
    result = load_news(st.session_state["newscat"])
    if result.get("error") == "no_key":
        st.info('No Finnhub key found. Run: export FINNHUB_API_KEY="your-key" then restart.')
    elif "error" in result:
        st.error(f"Could not load news: {result['error']}")
    elif not result.get("items"):
        H('<div class="lx-body">No news returned right now — try again shortly.</div>')
    else:
        cards = ""
        for item in result["items"]:
            ts = dt.datetime.fromtimestamp(item.get("datetime", 0)).strftime("%b %d, %Y · %H:%M")
            head = esc(item.get("headline") or "(no title)")
            url = esc(item.get("url") or "#")
            src = esc(item.get("source") or "")
            body = clean_html(item.get("summary") or "")
            body_html = f'<div class="lx-body">{esc(body)}</div>' if body else ""
            cards += ('<div class="lx-card">'
                      f'<div class="lx-news-head"><a href="{url}" target="_blank" rel="noopener">{head}</a></div>'
                      f'<div class="lx-meta">{src} &nbsp;·&nbsp; {ts}</div>{body_html}</div>')
        H(f'<div class="lx-grid" style="grid-template-columns:1fr;max-width:860px;">{cards}</div>')
    footer()


def view_about(theme):
    H('<div class="lx-hero lx-fade" style="padding-bottom:4px;">',
      '<div class="lx-hero-month">About</div>',
      '<div class="lx-hero-title" style="font-size:34px;">Monthly FX research, not a trading terminal</div>',
      '<div class="lx-hero-sub">FX Monthly Tracker publishes institutional-style monthly research for major '
      'USD pairs. Each report walks through price action, macro drivers, the economic calendar, technicals '
      'and a forward outlook — generated on demand from live data.</div></div>')
    section("01", "Methodology")
    cards = [
        ("Fundamental", "Central-bank policy, rate differentials, inflation and employment data (FRED), and the macro narrative that moved capital flows during the month."),
        ("Technical", "Trend, RSI, MACD, moving averages, market structure and classic pivot support/resistance — computed from daily Yahoo Finance data as of month end."),
        ("Sentiment", "Positioning, risk appetite and the prevailing story in wire headlines (Finnhub), synthesized by Claude into a view on the month's mood."),
    ]
    grid = "".join(
        f'<div class="lx-card"><div class="lx-kpi-label" style="color:#3B82F6;">{lb}</div>'
        f'<div class="lx-body" style="margin-top:9px;">{tx}</div></div>' for lb, tx in cards)
    H(f'<div class="lx-grid c3">{grid}</div>')
    section("02", "Data Sources")
    srcs = [("Prices", "Yahoo Finance — daily OHLC", True),
            ("News", "Finnhub free tier", bool(os.environ.get("FINNHUB_API_KEY"))),
            ("US macro", "FRED (St. Louis Fed)", bool(os.environ.get("FRED_API_KEY"))),
            ("AI research", "Anthropic Claude (Haiku)", bool(os.environ.get("ANTHROPIC_API_KEY")))]
    grid = "".join(
        '<div class="lx-card"><div style="display:flex;align-items:center;gap:9px;">'
        f'<span style="width:8px;height:8px;border-radius:50%;flex:none;background:{POS if ok else NEG};"></span>'
        f'<span style="font-size:14px;font-weight:650;color:var(--text);">{lb}</span>'
        f'<span class="lx-chip {"pos" if ok else "neg"}" style="margin-left:auto;">{"connected" if ok else "not set"}</span></div>'
        f'<div class="lx-body" style="margin-top:8px;">{tx}</div></div>'
        for lb, tx, ok in srcs)
    H(f'<div class="lx-grid c2">{grid}</div>')
    section("03", "Disclaimer")
    H('<div class="lx-card flat"><div class="lx-body">This site is a personal research dashboard. '
      'Nothing here is investment advice or a solicitation to trade. AI-generated content can contain '
      'errors — verify important figures against primary sources.</div></div>')
    footer()


# ============================ ROUTER =====================================

def main():
    st.session_state.setdefault("nav", "Reports")
    st.session_state.setdefault("pair", "DXY")
    st.session_state.setdefault("reports", {})
    theme = inject_css()
    sidebar()
    navbar()
    view = st.session_state.get("nav") or "Reports"
    {"Reports": view_reports, "Dashboard": view_dashboard, "Archive": view_archive,
     "News": view_news, "About": view_about}.get(view, view_reports)(theme)


main()
