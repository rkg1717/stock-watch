import streamlit as st
import os
import json
import warnings
from datetime import datetime, timedelta
import requests
import pandas as pd
import yfinance as yf
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
    def __init__(self):
        self.sec_ticker_map = None

    def load_sec_ticker_map(self):
        if self.sec_ticker_map: return
        if os.path.exists(SEC_TICKER_MAP_FILE):
            with open(SEC_TICKER_MAP_FILE, "r") as f: self.sec_ticker_map = json.load(f)
            return
        headers = {"User-Agent": "Financial Researcher rkg1717@gmail.com"} 
        try:
            resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
            self.sec_ticker_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in resp.json().values()}
            with open(SEC_TICKER_MAP_FILE, "w") as f: json.dump(self.sec_ticker_map, f)
        except: st.error("SEC Ticker Map could not be loaded.")

    def classify_event(self, form, description):
        desc = (description or "").upper()
        event_label = SEC_FORM_MAP.get(form, f"Other ({form})")
        if form == "8-K":
            if "ITEM 2.02" in desc: return "Material Event: Earnings"
            if "ITEM 5.02" in desc: return "Material Event: Leadership"
            if "ITEM 1.01" in desc: return "Material Event: Agreement"
            return "Material Event (General)"
        return event_label

    def fetch_sec_filings(self, ticker, start_date):
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
                if dt >= start_date:
                    etype = self.classify_event(form, desc)
                    if etype in EXCLUDE_EVENTS: continue
                    events.append({"date": fdate, "type": etype, "desc": desc or form, "dt_obj": dt})
            return events
        except: return []

# --- STREAMLIT UI ---
st.set_page_config(page_title="SEC Watch", layout="wide")
st.title("📊 SEC Event & Volume Analyzer")

with st.sidebar:
    st.header("Settings")
    ticker = st.text_input("Ticker Symbol", value="AAPL").upper()
    start_date_input = st.date_input("Historical Start Date", datetime.now() - timedelta(days=90))
    duration = st.number_input("Analysis Duration (Days)", min_value=1, value=30)
    run_button = st.button("Run Analysis")

if run_button:
    analyzer = EventPriceAnalyzer()
    start_dt = datetime.combine(start_date_input, datetime.min.time())
    
    with st.spinner(f"Analyzing {ticker}..."):
        # Download data with enough padding for volume averaging
        full_hist = yf.download(ticker, start=start_dt - timedelta(days=30), progress=False)
        filings = analyzer.fetch_sec_filings(ticker, start_dt)
        
    if full_hist.empty or not filings:
        st.error("Data retrieval failed. Check ticker or date range.")
    else:
        full_hist.index = pd.to_datetime(full_hist.index).date
        rows = []
        impact_col = f"pct_{duration}d"

        for ev in filings:
            f_date = ev['dt_obj'].date()
            trading_days = [d for d in full_hist.index if d >= f_date]
            if not trading_days: continue
            
            entry_date = min(trading_days)
            
            # --- CRITICAL SAFETY: Ensure single value extraction ---
            def safe_val(series_or_val):
                if isinstance(series_or_val, pd.Series): return float(series_or_val.iloc[0])
                return float(series_or_val)

            p_start = safe_val(full_hist.loc[entry_date, "Close"])

            # Volume Logic
            prior_vol = full_hist.loc[full_hist.index < entry_date].tail(10)['Volume'].mean()
            curr_vol = safe_val(full_hist.loc[entry_date, 'Volume'])
            v_ratio = round(curr_vol / prior_vol, 2) if prior_vol > 0 else 1.0

            def get_ret(days):
                target = entry_date + timedelta(days=days)
                fut = [d for d in full_hist.index if d >= target]
                if not fut: return 0.0
                p_end = safe_val(full_hist.loc[min(fut), "Close"])
                return round(((p_end - p_start) / p_start) * 100, 2)

            rows.append({
                "Date": ev["date"], "Event": ev["type"], "Vol_Ratio": v_ratio,
                "pct_1d": get_ret(1), "pct_5d": get_ret(5), "pct_10d": get_ret(10),
                impact_col: get_ret(duration), "Desc": ev["desc"]
            })
            
        df = pd.DataFrame(rows)

        # --- SECTION 1: HISTORICAL CHART ---
        st.subheader(f"1. Average Performance by Event ({duration} Days)")
        plot_cols = ["pct_1d", "pct_5d", "pct_10d", impact_col]
        summary = df.groupby("Event")[plot_cols].mean().reindex(columns=plot_cols)
        
        fig1, ax1 = plt.subplots(figsize=(10, 4))
        summary.plot(kind="bar", ax=ax1, edgecolor='black')
        ax1.axhline(0, color='black', linewidth=1)
        plt.xticks(rotation=45, ha="right")
        st.pyplot(fig1)

        # --- SECTION 2: 10-DAY RECENCY ---
        st.divider()
        st.subheader("2. Recency Check: Last 10 Trading Days")
        recent = full_hist.tail(10).copy()
        recent['Daily_Chg'] = recent['Close'].pct_change() * 100
        
        fig2, (ax_p, ax_v) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        d_labels = [d.strftime('%m-%d') for d in recent.index]
        
        ax_p.bar(d_labels, recent['Daily_Chg'].fillna(0), color=['g' if x >= 0 else 'r' for x in recent['Daily_Chg'].fillna(0)])
        ax_p.set_ylabel("Price %")
        ax_p.axhline(0, color='black', linewidth=0.8)

        ax_v.bar(d_labels, recent['Volume'], color='gray', alpha=0.4)
        ax_v.set_ylabel("Volume")

        # Map filings to the 10-day chart
        for r_date in df['Date']:
            dt_obj = datetime.strptime(r_date, "%Y-%m-%d").date()
            if dt_obj in recent.index:
                ax_p.axvline(x=dt_obj.strftime('%m-%d'), color='blue', linestyle='--', alpha=0.7)
        
        plt.xticks(rotation=45)
        st.pyplot(fig2)

        # --- SECTION 3: DATA LOG ---
        st.divider()
        st.subheader("3. Historical Data Log")
        st.dataframe(df)
