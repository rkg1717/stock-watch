import streamlit as st
import os
import json
import warnings
from datetime import datetime, timedelta
import requests
import pandas as pd
import yfinance as yf
import openai

# --- SETUP ---
warnings.filterwarnings("ignore")
SEC_TICKER_MAP_FILE = "sec_company_tickers.json"
SEC_FORM_MAP = {
    "4": "Insider Trading", "10-Q": "Quarterly Report", "10-K": "Annual Report",
    "8-K": "Material Event", "S-1": "IPO/Registration", "SC 13G": "Passive Ownership",
    "DEFA14A": "Proxy Statement", "424B3": "Prospectus"
}

class EventAnalyzer:
    def __init__(self, api_key=None):
        self.sec_ticker_map = None
        self.client = openai.OpenAI(api_key=api_key) if api_key else None

    def get_sentiment(self, text):
        if not self.client: return "N/A"
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "Classify sentiment as Positive, Negative, or Neutral. One word only."},
                          {"role": "user", "content": text}],
                max_tokens=5
            )
            return resp.choices[0].message.content.strip()
        except: return "Error"

    def load_sec_map(self):
        if self.sec_ticker_map: return
        headers = {"User-Agent": "Researcher rkg1717@gmail.com"}
        try:
            resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
            self.sec_ticker_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in resp.json().values()}
        except:
            st.error("Could not load SEC ticker map.")

    def fetch_filings(self, ticker, start_date):
        self.load_sec_map()
        cik = self.sec_ticker_map.get(ticker.upper())
        if not cik: return []
        headers = {"User-Agent": "Researcher rkg1717@gmail.com"}
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            data = requests.get(url, headers=headers).json()
            f = data.get("filings", {}).get("recent", {})
            results = []
            for form, fdate, desc in zip(f.get("form", []), f.get("filingDate", []), f.get("primaryDocDescription", [])):
                dt = datetime.strptime(fdate, "%Y-%m-%d")
                if dt >= start_date:
                    results.append({"date": fdate, "type": SEC_FORM_MAP.get(form, f"Other ({form})"), "desc": desc})
            return results
        except: return []

# --- UI ---
st.set_page_config(page_title="SEC Watch", layout="wide")
st.title("📊 SEC Event Impact Tracker")

with st.sidebar:
    st.header("Parameters")
    ticker = st.text_input("Ticker Symbol", "AAPL").upper()
    days_back = st.number_input("Lookback Period (Days)", 30, 730, 180)
    duration = st.slider("Analysis Window (Days)", 1, 60, 14)
    run = st.button("Analyze Impact")

if run:
    analyzer = EventAnalyzer(st.secrets.get("OPENAI_API_KEY"))
    start_dt = datetime.now() - timedelta(days=days_back)
    
    with st.spinner(f"Processing {ticker}..."):
        # 1. Download History (Expanded slightly to catch windows)
        hist = yf.download(ticker, start=start_dt - timedelta(days=30), progress=False)
        if not hist.empty:
            hist.index = pd.to_datetime(hist.index).date
        
        # 2. Get Filings
        filings = analyzer.fetch_filings(ticker, start_dt)
        
    if hist.empty or not filings:
        st.error("No data found for this ticker or period.")
    else:
        rows = []
        impact_col = f"{duration}d Impact %"
        
        for f in filings:
            f_date = datetime.strptime(f['date'], "%Y-%m-%d").date()
            # Find the actual trading day (on or after filing)
            trading_days = [d for d in hist.index if d >= f_date]
            if not trading_days: continue
            
            entry_date = min(trading_days)
            p_start = float(hist.loc[entry_date, "Close"])
            
            def calculate_return(days_ahead):
                target = entry_date + timedelta(days=days_ahead)
                future_days = [d for d in hist.index if d >= target]
                if not future_days: return 0.0
                p_end = float(hist.loc[min(future_days), "Close"])
                return round(((p_end - p_start) / p_start) * 100, 2)

            rows.append({
                "Date": f['date'],
                "Event": f['type'],
                "Sentiment": analyzer.get_sentiment(f['desc']),
                "1d %": calculate_return(1),
                "5d %": calculate_return(5),
                impact_col: calculate_return(duration),
                "Description": f['desc']
            })
            
        df = pd.DataFrame(rows)
        
        # --- OUTPUTS ---
        # 1. Historical Performance Chart
        st.subheader(f"Historical Average: {duration}-Day Impact by Event")
        summary = df.groupby("Event")[[impact_col]].mean()
        st.bar_chart(summary)
        
        # 2. Detailed Data Table
        st.divider()
        st.subheader("Filing History & Performance")
        st.dataframe(df, use_container_width=True)

        # 3. Simple Summary Text
        best_event = summary[impact_col].idxmax()
        best_val = summary[impact_col].max()
        st.info(f"Historical Winner: **{best_event}** usually leads to a **{best_val}%** move over {duration} days.")
