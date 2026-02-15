import streamlit as st
import os
import json
import warnings
from datetime import datetime, timedelta
import requests
import pandas as pd
import yfinance as yf
import openai
import matplotlib.pyplot as plt

# --- SETUP & CONFIG ---
warnings.filterwarnings("ignore", category=FutureWarning)
SEC_TICKER_MAP_FILE = "sec_company_tickers.json"
SEC_FORM_MAP = {
    "4": "Insider Trading", "5": "Insider Trading (Annual)", "144": "Intent to Sell Stock",
    "10-Q": "Quarterly Financial Report", "10-K": "Annual Financial Report",
    "8-K": "Material Event Report", "S-1": "Registration Statement (IPO)",
    "S-3": "Registration Statement (Secondary)", "S-4": "Registration Statement (Merger/Exchange)",
    "SC 13G": "Passive Ownership Change", "SC 13D": "Active Ownership Change",
    "DEFA14A": "Proxy Solicitation", "DEF 14A": "Official Proxy Statement",
    "6-K": "Foreign Issuer Material Event"
}
EXCLUDE_EVENTS = ["Insider Trading", "Insider Trading (Annual)", "Employee Stock Plan"]

class EventPriceAnalyzer:
    def __init__(self, api_key=None):
        self.sec_ticker_map = None
        self.client = openai.OpenAI(api_key=api_key) if api_key else None

    def get_sentiment(self, text):
        if not self.client or not text: return "N/A"
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Classify SEC filing sentiment as 'Positive', 'Negative', or 'Neutral'. Return one word."},
                    {"role": "user", "content": text}
                ],
                max_tokens=10
            )
            return response.choices[0].message.content.strip().replace(".", "")
        except: return "Error"

    def load_sec_ticker_map(self):
        if self.sec_ticker_map: return
        if os.path.exists(SEC_TICKER_MAP_FILE):
            with open(SEC_TICKER_MAP_FILE, "r") as f: self.sec_ticker_map = json.load(f)
            return
        headers = {"User-Agent": "Financial Researcher rkg1717@gmail.com"} 
        resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
        self.sec_ticker_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in resp.json().values()}
        with open(SEC_TICKER_MAP_FILE, "w") as f: json.dump(self.sec_ticker_map, f)

    def classify_event(self, form: str, description: str) -> str:
        desc = (description or "").upper()
        event_label = SEC_FORM_MAP.get(form, f"Other SEC Filing ({form})")
        if form == "8-K":
            item_map = {
                "ITEM 1.01": "Material Agreement", "ITEM 2.02": "Earnings Release",
                "ITEM 5.02": "Leadership/Director Change", "ITEM 8.01": "General Material Event",
                "ITEM 7.01": "Reg FD Disclosure", "ITEM 1.02": "Agreement Termination"
            }
            for code, label in item_map.items():
                if code in desc: return f"Material Event: {label}"
            return "Material Event (General)"
        return event_label

    def get_price_reactions(self, ticker, date_str, custom_days):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            data = yf.download(ticker, start=dt-timedelta(days=15), end=dt+timedelta(days=custom_days+5), progress=False)
            if data.empty: return {k: 0 for k in ["event", "d1", "d5", "d10", "custom", "vol_ratio"]}
            data.index = data.index.date
            
            # Volume Ratio Calculation
            prior_data = data.loc[data.index < dt].tail(10)
            avg_vol = prior_data['Volume'].mean()
            event_vol = data['Volume'].get(dt, 0)
            vol_ratio = round(event_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            def get_p(d):
                avail = [idx for idx in data.index if idx >= d]
                return float(data.loc[min(avail), "Close"]) if avail else 0
            
            return {
                "event": get_p(dt), "d1": get_p(dt+timedelta(days=1)), 
                "d5": get_p(dt+timedelta(days=5)), "d10": get_p(dt+timedelta(days=10)),
                "custom": get_p(dt+timedelta(days=custom_days)),
                "vol_ratio": vol_ratio
            }
        except: return {k: 0 for k in ["event", "d1", "d5", "d10", "custom", "vol_ratio"]}

    def fetch_sec_filings(self, ticker, start_date, end_date):
        self.load_sec_ticker_map()
        cik = self.sec_ticker_map.get(ticker.upper())
        if not cik: return []
        headers = {"User-Agent": "Financial Researcher rkg1717@gmail.com"} 
        try:
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            data = requests.get(url, headers=headers).json()
            f = data.get("filings", {}).get("recent", {})
            events = []
            for form, fdate, desc in zip(f.get("form", []), f.get("filingDate", []), f.get("primaryDocDescription", [])):
                dt = datetime.strptime(fdate, "%Y-%m-%d")
                if start_date <= dt <= end_date:
                    etype = self.classify_event(form, desc)
                    if etype in EXCLUDE_EVENTS: continue
                    events.append({"date": fdate, "type": etype, "desc": desc or form, "dt_obj": dt})
            return events
        except: return []

# --- STREAMLIT UI ---
st.set_page_config(page_title="SEC Event Price Analyzer", layout="wide")
st.title("📊 SEC Event Price Analyzer")

with st.sidebar:
    st.header("Settings")
    ticker = st.text_input("Ticker Symbol", value="AAPL").upper()
    start_date_input = st.date_input("Historical Start Date", datetime.now() - timedelta(days=365))
    duration = st.number_input("Analysis Duration (Days)", min_value=1, value=30)
    run_button = st.button("Run Analysis")

if run_button:
    api_key = st.secrets.get("OPENAI_API_KEY")
    analyzer = EventPriceAnalyzer(api_key)
    
    start_dt = datetime.combine(start_date_input, datetime.min.time())
    end_dt = datetime.now()
    custom_col = f"pct_{duration}d"
    
    with st.spinner(f"Analyzing {ticker}..."):
        events = analyzer.fetch_sec_filings(ticker, start_dt, end_dt)
    
    if not events:
        st.warning(f"No relevant events found for {ticker}.")
    else:
        rows = []
        progress_bar = st.progress(0)
        for i, ev in enumerate(events):
            p = analyzer.get_price_reactions(ticker, ev["date"], duration)
            def chg(p1, p2): return round(((p2 - p1) / p1) * 100, 2) if p1 > 0 and p2 > 0 else 0
            
            rows.append({
                "Date": ev["date"], "Event": ev["type"], "Sentiment": analyzer.get_sentiment(ev["desc"]),
                "pct_1d": chg(p["event"], p["d1"]), "pct_5d": chg(p["event"], p["d5"]), 
                "pct_10d": chg(p["event"], p["d10"]), 
                custom_col: chg(p["event"], p["custom"]),
                "Vol_Ratio": p["vol_ratio"],
                "Desc": ev["desc"]
            })
            progress_bar.progress((i + 1) / len(events))

        df = pd.DataFrame(rows)

        # --- SECTION 1: HISTORICAL AVERAGE ---
        st.subheader(f"1. Historical Event Reactions ({duration} Day Impact)")
        fig1, ax1 = plt.subplots(figsize=(10, 4))
        plot_cols = ["pct_1d", "pct_5d", "pct_10d", custom_col]
        summary_data = df.groupby("Event")[plot_cols].mean()
        summary_data.plot(kind="bar", ax=ax1, color=['#e31a1c', '#1f78b4', '#ff7f00', '#636363'], edgecolor='black')
        ax1.set_title(f"Average Performance by Event Type (Historical)")
        ax1.axhline(0, color='black', linewidth=1)
        plt.xticks(rotation=45, ha="right")
        st.pyplot(fig1)

        # --- SECTION 2: RECENCY CHECK ---
        st.divider()
        st.subheader("2. Recency Check: Last 10 Days Performance")
        
        recent_data = yf.download(ticker, period="15d", progress=False)
        if not recent_data.empty:
            recent_data['Daily_Chg'] = recent_data['Close'].pct_change() * 100
            last_10 = recent_data.tail(10)
            
            # Matplotlib data cleaning to prevent TypeErrors
            x_labels = list(last_10.index.strftime('%m-%d'))
            price_changes = [float(x) for x in last_10['Daily_Chg'].fillna(0)]
            volume_vals = [float(x) for x in last_10['Volume'].fillna(0)]

            fig2, (ax_p, ax_v) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
            
            # Price Bars
            colors = ['#2ca02c' if x > 0 else '#d62728' for x in price_changes]
            ax_p.bar(x_labels, price_changes, color=colors)
            ax_p.set_ylabel("Price Change %")
            ax_p.axhline(0, color='black', linewidth=0.8)

            # Volume Bars
            ax_v.bar(x_labels, volume_vals, color='gray', alpha=0.5)
            ax_v.set_ylabel("Volume")
            
            # Logic for overlays and signal strength
            recent_events = [e for e in events if datetime.strptime(e['date'], "%Y-%m-%d") >= (datetime.now() - timedelta(days=10))]
            
            for rev in recent_events:
                ev_date_fmt = datetime.strptime(rev['date'], "%Y-%m-%d").strftime('%m-%d')
                if ev_date_fmt in x_labels:
                    ax_p.axvline(x=ev_date_fmt, color='black', linestyle='--', alpha=0.7)
                    ax_p.text(ev_date_fmt, ax_p.get_ylim()[1]*0.7, rev['type'], color='black', rotation=90, fontweight='bold', fontsize=8)
                    ax_v.axvline(x=ev_date_fmt, color='black', linestyle='--', alpha=0.7)
            
            plt.xticks(rotation=45)
            st.pyplot(fig2)
            
            if recent_events:
                st.write("**Recent Filing Signal Analysis:**")
                recent_table_data = []
                for re in recent_events:
                    hist_avg = df[df['Event'] == re['type']][custom_col].mean() if not df.empty else 0
                    actual_day_move = last_10['Daily_Chg'].get(re['date'], 0)
                    
                    # Signal Strength Logic
                    if abs(actual_day_move) > 2.0:
                        strength = "Strong"
                    elif abs(actual_day_move) > 0.5:
                        strength = "Moderate"
                    else:
                        strength = "Weak"

                    recent_table_data.append({
                        "Date": re['date'],
                        "Type": re['type'],
                        "Sentiment": analyzer.get_

