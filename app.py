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
SEC_TICKER_MAP_FILE = "sec_company_tickers.json"
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
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "outputsize": "full",
            "apikey": self.api_key
        }
        try:
            resp = requests.get(self.base_url, params=params).json()
            
            # THE "OTHER DETECT" LOGIC
            if "Note" in resp:
                st.warning("⏳ Alpha Vantage Limit Reached: Please wait 60 seconds and try again.")
                return pd.DataFrame()
            if "Error Message" in resp:
                st.error(f"❌ Ticker '{ticker}' not found. Please check the symbol.")
                return pd.DataFrame()
            if "Time Series (Daily)" not in resp:
                return pd.DataFrame()
            
            data = resp["Time Series (Daily)"]
            df = pd.DataFrame.from_dict(data, orient='index')
            df.columns = ["Open", "High", "Low", "Close", "Volume"]
            df.index = pd.to_datetime(df.index).date
            df = df.astype(float).sort_index()
            return df
        except Exception as e:
            st.error(f"Connection Error: {e}")
            return pd.DataFrame()

class SECAnalyzer:
    def __init__(self):
        self.sec_ticker_map = None

    def load_sec_map(self):
        if self.sec_ticker_map: return
        headers = {"User-Agent": "Researcher rkg1717@gmail.com"}
        try:
            resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
            self.sec_ticker_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in resp.json().values()}
        except: st.error("SEC Ticker Map could not be loaded.")

    def fetch_filings(self, ticker, start_date):
        self.load_sec_map()
        cik = self.sec_ticker_map.get(ticker.upper())
        if not cik: return []
        headers = {"User-Agent": "Researcher rkg1717@gmail.com"}
        try:
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            data = requests.get(url, headers=headers).json()
            f = data.get("filings", {}).get("recent", {})
            events = []
            for form, fdate, desc in zip(f.get("form", []), f.get("filingDate", []), f.get("primaryDocDescription", [])):
                dt = datetime.strptime(fdate, "%Y-%m-%d")
                if dt >= start_date:
                    etype = SEC_FORM_MAP.get(form, f"Other ({form})")
                    if etype in EXCLUDE_EVENTS: continue
                    events.append({"date": fdate, "type": etype, "desc": desc or form, "dt_obj": dt})
            return events
        except: return []

# --- STREAMLIT UI ---
st.set_page_config(page_title="SEC Watch", layout="wide")
st.title("📊 Alpha-SEC Event & Volume Analyzer")

with st.sidebar:
    st.header("Settings")
    if "AV_API_KEY" in st.secrets:
        av_key = st.secrets["AV_API_KEY"]
        st.info("Using Key from Secrets ✅")
    else:
        av_key = st.text_input("Alpha Vantage API Key", type="password")
    
    ticker = st.text_input("Ticker Symbol", value="AAPL").upper()
    start_date_input = st.date_input("Historical Start Date", datetime.now() - timedelta(days=90))
    duration = st.number_input("Analysis Duration (Days)", min_value=1, value=30)
    run_button = st.button("Run Analysis")

if run_button:
    if not av_key:
        st.error("Please provide an Alpha Vantage API Key.")
    else:
        sec = SECAnalyzer()
        av = AlphaVantageClient(av_key)
        start_dt = datetime.combine(start_date_input, datetime.min.time())
        
        with st.spinner(f"Analyzing {ticker}..."):
            hist = av.get_daily_data(ticker)
            filings = sec.fetch_filings(ticker, start_dt)
            
        if not hist.empty and filings:
            rows = []
            impact_col = f"pct_{duration}d"

            for ev in filings:
                f_date = ev['dt_obj'].date()
                trading_days = [d for d in hist.index if d >= f_date]
                if not trading_days: continue
                entry_date = min(trading_days)
                
                # Scalar Enforcement
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

                rows.append({
                    "Date": ev["date"], "Event": ev["type"], "Vol_Ratio": v_ratio,
                    "pct_1d": get_ret(1), "pct_5d": get_ret(5), impact_col: get_ret(duration),
                    "Desc": ev["desc"]
                })
                
            df = pd.DataFrame(rows)
            
            # --- CHARTS ---
            st.subheader(f"1. Average Performance ({duration} Days)")
            st.bar_chart(df.groupby("Event")[[impact_col]].mean())

            st.divider()
            st.subheader("2. Recency Check: Last 10 Trading Days")
            recent = hist.tail(10).copy()
            recent['Chg'] = recent['Close'].pct_change() * 100
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
            x_labs = [d.strftime('%m-%d') for d in recent.index]
            ax1.bar(x_labs, recent['Chg'].fillna(0), color=['g' if x >= 0 else 'r' for x in recent['Chg'].fillna(0)])
            ax2.bar(x_labs, recent['Volume'], color='gray', alpha=0.4)
            st.pyplot(fig)

            st.divider()
            st.subheader("3. Historical Data Log")
            st.dataframe(df)
        elif hist.empty:
            # Error is handled inside get_daily_data
            pass
        else:
            st.warning("No SEC filings found for this period.")
