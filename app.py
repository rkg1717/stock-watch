import streamlit as st
import os
import json
import warnings
from datetime import datetime, timedelta
import requests
import pandas as pd
import matplotlib.pyplot as plt

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

class AlphaVantageClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"

    def get_daily_data(self, ticker):
        params = {"function": "TIME_SERIES_DAILY", "symbol": ticker.strip().upper(), "outputsize": "full", "apikey": self.api_key}
        try:
            resp_raw = requests.get(self.base_url, params=params, timeout=15)
            resp = resp_raw.json()
            if "Note" in resp:
                st.warning("⏳ Alpha Vantage Limit: Please wait 60 seconds.")
                return pd.DataFrame()
            if "Time Series (Daily)" not in resp: return pd.DataFrame()
            data = resp["Time Series (Daily)"]
            df = pd.DataFrame.from_dict(data, orient='index')
            df.columns = ["Open", "High", "Low", "Close", "Volume"]
            df.index = pd.to_datetime(df.index).date
            df = df.astype(float).sort_index()
            return df
        except: return pd.DataFrame()

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
st.title("📊 Alpha-SEC Event & Volume Analyzer")

with st.sidebar:
    st.header("Settings")
    av_key = st.secrets.get("AV_API_KEY", "")
    if av_key: st.success("API Key Active ✅")
    else: av_key = st.text_input("Alpha Vantage API Key", type="password")
    
    ticker = st.text_input("Ticker Symbol", value="VZ").upper()
    start_date_input = st.date_input("Historical Start Date", datetime.now() - timedelta(days=120))
    duration = st.number_input("Analysis Duration (Days)", min_value=1, value=30)
    run_button = st.button("Run Analysis", type="primary")
if run_button:
    status = st.empty()
    status.info(f"🚀 Running analysis for {ticker}...")
    sec = SECAnalyzer()
    av = AlphaVantageClient(av_key)
    ticker_map = sec.load_sec_map()
    hist = av.get_daily_data(ticker)
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
            curr_vol = float(hist.at[entry_date, 'Volume'])
            v_ratio = round(curr_vol / prior_vol, 2) if prior_vol > 0 else 1.0

            def get_ret(days):
                target = entry_date + timedelta(days=days)
                fut = [d for d in hist.index if d >= target]
                if not fut: return 0.0
                p_end = float(hist.at[min(fut), "Close"])
                return round(((p_end - p_start) / p_start) * 100, 2)

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
        if hist.empty: st.warning("Price data missing. Wait 60s for Alpha Vantage limit.")
        if not filings: st.warning(f"No qualifying filings found for {ticker} since {start_date_input}.")
