import streamlit as st
import os
import json
import warnings
from datetime import datetime, timedelta
import requests
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# --- SETUP & CONFIG ---
warnings.filterwarnings("ignore")
SEC_FORM_MAP = {
    "4": "Insider Trading", "5": "Insider Trading (Annual)", "144": "Intent to Sell Stock",
    "10-Q": "Quarterly Financial Report", "10-K": "Annual Financial Report",
    "8-K": "Material Event Report", "S-1": "Registration Statement (IPO)",
    "S-3": "Registration Statement (Secondary)", "S-4": "Registration Statement (Merger/Exchange)",
    "SC 13G": "Passive Ownership Change", "SC 13D": "Active Ownership Change",
    "DEFA14A": "Proxy Solicitation", "DEF 14A": "Official Proxy Statement"
}
EXCLUDE_EVENTS = ["Insider Trading", "Insider Trading (Annual)", "Employee Stock Plan"]

class StockDataClient:
    def get_daily_data(self, ticker):
        try:
            # Fetching 1 year of data for context
            df = yf.download(ticker.strip().upper(), period="1y", progress=False)
            if df.empty:
                return pd.DataFrame()
            
            # Clean up multi-index columns if they exist
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            df.index = pd.to_datetime(df.index).date
            return df.astype(float).sort_index()
        except Exception as e:
            st.error(f"Stock Data Error: {e}")
            return pd.DataFrame()

class SECAnalyzer:
    def load_sec_map(self):
        headers = {"User-Agent": "Researcher rkg1717@gmail.com"}
        try:
            resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
            return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in resp.json().values()}
        except: return {}

    def fetch_filings(self, ticker, start_date, ticker_map):
        cik = ticker_map.get(ticker.upper())
        if not cik: return []
        headers = {"User-Agent": "Researcher rkg1717@gmail.com"}
        try:
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            data = requests.get(url, headers=headers).json()
            f = data.get("filings", {}).get("recent", {})
            events = []
            target_dt = start_date.date() if isinstance(start_date, datetime) else start_date
            for form, fdate, desc in zip(f.get("form", []), f.get("filingDate", []), f.get("primaryDocDescription", [])):
                dt_obj = datetime.strptime(fdate, "%Y-%m-%d").date()
                if dt_obj >= target_dt:
                    etype = SEC_FORM_MAP.get(form, f"Other ({form})")
                    if etype in EXCLUDE_EVENTS: continue
                    events.append({"date": fdate, "type": etype, "desc": desc or form, "dt_obj": dt_obj})
            return events
        except: return []
            # --- UI ---
st.set_page_config(page_title="SEC Watch", layout="wide")
st.title("📊 SEC Event & Volume Analyzer (No-API Version)")

with st.sidebar:
    st.header("Settings")
    ticker = st.text_input("Ticker Symbol", value="VZ").upper()
    start_date_input = st.date_input("Historical Start Date", datetime.now() - timedelta(days=120))
    duration = st.number_input("Analysis Duration (Days)", min_value=1, value=30)
    run_button = st.button("Run Analysis", type="primary")
if run_button:
    status = st.empty()
    status.info(f"🚀 Analyzing {ticker}...")
    sec = SECAnalyzer()
    client = StockDataClient()
    ticker_map = sec.load_sec_map()
    hist = client.get_daily_data(ticker)
    filings = sec.fetch_filings(ticker, start_date_input, ticker_map)
    
    if not hist.empty and filings:
        status.empty()
        rows = []
        impact_col = f"pct_{duration}d"
        for ev in filings:
            f_date = ev['dt_obj']
            trading_days = [d for d in hist.index if d >= f_date]
            if not trading_days: continue
            entry_date = min(trading_days)
            p_start = float(hist.at[entry_date, "Close"])
            prior_vol = hist.loc[hist.index < entry_date].tail(10)['Volume'].mean()
            v_ratio = round(float(hist.at[entry_date, 'Volume']) / prior_vol, 2) if prior_vol > 0 else 1.0

            def get_ret(days):
                target = entry_date + timedelta(days=days)
                fut = [d for d in hist.index if d >= target]
                if not fut: return 0.0
                return round(((float(hist.at[min(fut), "Close"]) - p_start) / p_start) * 100, 2)

            rows.append({"Date": ev["date"], "Event": ev["type"], "Vol_Ratio": v_ratio, 
                         "pct_1d": get_ret(1), "pct_5d": get_ret(5), impact_col: get_ret(duration)})
            
        df = pd.DataFrame(rows)
        st.subheader(f"1. Average Performance ({duration} Days)")
        st.bar_chart(df.groupby("Event")[[impact_col]].mean())
        st.divider()
        st.subheader("2. Recency Check: Last 10 Trading Days")
        recent = hist.tail(10).copy()
        recent['Chg'] = (recent['Close'].pct_change() * 100).fillna(0)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        x_labs = [d.strftime('%m-%d') for d in recent.index]
        ax1.bar(x_labs, recent['Chg'], color=['g' if x >= 0 else 'r' for x in recent['Chg']])
        ax1.set_ylabel("Price %")
        ax2.bar(x_labs, recent['Volume'], color='gray', alpha=0.4)
        ax2.set_ylabel("Volume")
        st.pyplot(fig)
        st.divider()
        st.subheader("3. Historical Data Log")
        st.dataframe(df, use_container_width=True)
    else:
        status.empty()
        if hist.empty:
            st.warning("Stock data could not be retrieved. Ticker might be invalid.")
        if not filings:
            st.warning(f"No qualifying filings found for {ticker} since {start_date_input}.")
