"""
FX Monthly Tracker -- a personal dashboard for major USD pairs.

AI analysis is now targeted and highly thorough based on user-selected months.
Web search is OFF by default to keep it cheap (~1 cent); tick the box to add 
cited sources (~10-15 cents). Uses the cheaper Haiku model.

HOW TO RUN (needs internet -- run on your own Mac):
    pip3 install streamlit yfinance pandas requests anthropic
    export FINNHUB_API_KEY="your-finnhub-key"
    export FRED_API_KEY="your-fred-key"
    export ANTHROPIC_API_KEY="your-anthropic-key"
    streamlit run fx_tracker.py
"""

import os
import time
import datetime as dt
import requests
import pandas as pd
import streamlit as st
import yfinance as yf

PAIRS = {
    "DXY (US Dollar Index)": {"ticker": "DX-Y.NYB", "usd_is_base": True},
    "EUR/USD":               {"ticker": "EURUSD=X", "usd_is_base": False},
    "GBP/USD":               {"ticker": "GBPUSD=X", "usd_is_base": False},
    "AUD/USD":               {"ticker": "AUDUSD=X", "usd_is_base": False},
    "USD/IDR":               {"ticker": "USDIDR=X", "usd_is_base": True},
}

FRED_SERIES = {
    "Fed funds rate (%, level)": "FEDFUNDS",
    "CPI (index level)":         "CPIAUCSL",
    "Core CPI (index level)":    "CPILFESL",
    "Unemployment rate (%)":     "UNRATE",
    "Nonfarm payrolls (000s)":   "PAYEMS",
}

st.set_page_config(page_title="FX Monthly Tracker", layout="wide")
st.title("FX Monthly Tracker")
st.caption("Personal dashboard -- prices, news, and AI analysis for your pairs.")

with st.sidebar:
    st.subheader("Data sources")
    st.write("Prices (Yahoo): connected")
    for name, env in [("News (Finnhub)", "FINNHUB_API_KEY"),
                      ("US data (FRED)", "FRED_API_KEY"),
                      ("AI (Anthropic)", "ANTHROPIC_API_KEY")]:
        st.write(f"{name}: {'connected' if os.environ.get(env) else 'not set'}")


# ============================ PRICES =====================================
@st.cache_data(ttl=60 * 60, show_spinner=False)
def load_history(ticker: str, months_back: int = 14) -> pd.DataFrame:
    start = (dt.date.today() - dt.timedelta(days=months_back * 31)).isoformat()
    for attempt in range(3):
        try:
            df = yf.download(ticker, start=start, interval="1d",
                             progress=False, auto_adjust=False, threads=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df[["Close"]].dropna()
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return pd.DataFrame()


def monthly_summary(df: pd.DataFrame, usd_is_base: bool) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    grouped = df["Close"].groupby([df.index.year, df.index.month])
    rows = []
    for (year, month), series in grouped:
        first, last = float(series.iloc[0]), float(series.iloc[-1])
        pct = (last / first - 1) * 100
        usd_dir = ("stronger" if pct > 0 else "weaker") if usd_is_base else \
                  ("weaker" if pct > 0 else "stronger")
        rows.append({
            "Month": f"{year}-{month:02d}", "Open": round(first, 4),
            "Close": round(last, 4), "Change %": round(pct, 2),
            "High": round(float(series.max()), 4),
            "Low": round(float(series.min()), 4), "USD ended": usd_dir,
        })
    return pd.DataFrame(rows).sort_values("Month", ascending=False).reset_index(drop=True)


# ============================ NEWS =======================================
@st.cache_data(ttl=15 * 60, show_spinner=False)
def load_news(category: str = "forex", limit: int = 30) -> dict:
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


# ============================ US ECONOMIC DATA (FRED) ====================
@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def load_us_macro(months: int = 14) -> dict:
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
        return "(no US economic data -- add a FRED key to enable this)"
    lines = []
    for label, series in macro.get("data", {}).items():
        if series:
            lines.append(f"{label} -> " + ", ".join(f"{d}: {v}" for d, v in series[-6:]))
    return "\n".join(lines) or "(no US economic data returned)"


# ============================ AI ANALYSIS (Targeted & Thorough) ==========
@st.cache_data(ttl=30 * 60, show_spinner=False)
def analyze_with_ai(pair_name: str, price_context: str, macro_context: str, selected_months: list, use_search: bool) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"error": "no_key"}
    try:
        from anthropic import Anthropic
        client = Anthropic()
        
        if use_search:
            source_instr = (
                "CRITICAL: Use web search to uncover the exact key calendar dates, central-bank decisions (Fed, ECB, BoE, BI, etc.), "
                "and unexpected geopolitical or economic prints that occurred during these requested months. Attribute claims to sources."
            )
        else:
            source_instr = "Base your explanation contextually on the provided data matrices below; do not invent figures or events outside the timelines."

        months_str = ", ".join(selected_months)
        
        prompt = (
            f"You are a Senior Macro Forex Strategist. Provide a highly thorough, detailed, and institutional-grade deep dive analysis "
            f"ONLY for the following specific months: {months_str}.\n\n"
            f"For each requested month, your output must follow this exact structure:\n"
            f"### **[Month Year]** (e.g., ### **May 2026**)\n"
            f"- **Price Action Summary**: 1-2 sharp sentences tying together the open, close, and overall direction of the pair.\n"
            f"- **Main Key Dates & Macro Events**: Pinpoint specific key dates or high-impact release windows (e.g., FOMC meeting weeks, NFP/CPI drops, specific policy rate shifts) that dictated sentiment.\n"
            f"- **Fundamental Causal Analysis**: Thoroughly analyze exactly HOW those events, data surprises, or central bank actions fundamentally altered capital flows and directly impacted the strength/weakness of {pair_name}.\n\n"
            f"{source_instr}\n\n"
            f"PRICE TREND MATRIX FOR CONTEXT:\n{price_context}\n\n"
            f"US MACRO ECONOMIC DATA MATRIX FOR CONTEXT:\n{macro_context}"
        )

        kwargs = dict(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000, # Expanded token limit to allow thorough deep dives
            messages=[{"role": "user", "content": prompt}],
        )
        if use_search:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]
        
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
        return {"text": "".join(text_parts).strip(), "sources": sources}
    except Exception as e:
        return {"error": str(e)}


# ============================ UI =========================================
choice = st.selectbox("Choose a view", list(PAIRS.keys()) + ["Market News"])

if choice == "Market News":
    st.subheader("Market news (Finnhub free tier)")
    category = st.radio("Category", ["forex", "general", "crypto", "merger"], horizontal=True)
    result = load_news(category)
    if result.get("error") == "no_key":
        st.info('No Finnhub key found. Run: export FINNHUB_API_KEY="your-key"  then restart.')
    elif "error" in result:
        st.error(f"Could not load news: {result['error']}")
    elif not result.get("items"):
        st.write("No news returned right now -- try again shortly.")
    else:
        for n in result["items"]:
            ts = dt.datetime.fromtimestamp(n.get("datetime", 0)).strftime("%Y-%m-%d %H:%M")
            st.markdown(f"**[{n.get('headline', '(no title)')}]({n.get('url', '')})**")
            st.caption(f"{n.get('source', '')}  -  {ts}")
            if n.get("summary"):
                st.write(n["summary"])
            st.divider()
else:
    cfg = PAIRS[choice]
    with st.spinner(f"Loading {choice} prices from Yahoo..."):
        df = load_history(cfg["ticker"])

    if df.empty:
        st.warning("Couldn't load price data right now -- Yahoo Finance is temporarily "
                   "rate-limiting. Wait about a minute, then press R (or top-right menu > Rerun).")
    else:
        summary = monthly_summary(df, cfg["usd_is_base"])
        latest = summary.iloc[0]
        st.metric(label=f"{choice} -- {latest['Month']}", value=latest["Close"],
                  delta=f"{latest['Change %']}%  (USD ended {latest['USD ended']})")
        st.line_chart(df["Close"], height=260)
        
        st.subheader("Monthly summary")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        # ---- TARGETED AI ANALYSIS BLOCK ----
        st.divider()
        st.subheader("Targeted AI Analysis Deep-Dive")
        
        # Pull list of unique months directly from the data layout
        available_months = summary["Month"].tolist()
        
        selected_months = st.multiselect(
            "Select specific month(s) to analyze thoroughly:",
            options=available_months,
            default=[available_months[0]] if available_months else None,
            help="To maintain token efficiency and granular accuracy, choose only the target frames you want detailed event breakdowns for."
        )
        
        use_search = st.checkbox(
            "Search the web for historical macro calendars (~10-15c per click vs ~1c for rich, cited details)",
            value=False)
            
        if st.button(f"Analyze Selected Frames for {choice}"):
            if not selected_months:
                st.warning("Please tick at least one month frame to initiate analysis.")
            else:
                with st.spinner("Executing structural macro analysis... Please wait..."):
                    macro = load_us_macro()
                    
                    # Filter price summary down strictly to selected frames to minimize token waste
                    filtered_summary = summary[summary["Month"].isin(selected_months)]
                    price_context = filtered_summary.to_string(index=False)
                    macro_context = macro_to_text(macro)
                    
                    result = analyze_with_ai(choice, price_context, macro_context, selected_months, use_search)
                    
                if result.get("error") == "no_key":
                    st.info("Add your Anthropic API key (see setup notes) to turn this on.")
                elif "error" in result:
                    st.error(f"AI error: {result['error']}")
                else:
                    st.markdown(result["text"])
                    if result.get("sources"):
                        st.markdown("**Sources Uncovered**")
                        for title, url in result["sources"]:
                            st.markdown(f"- [{title}]({url})")
