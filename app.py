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

# --- SETUP ---
warnings.filterwarnings("ignore")
SEC_TICKER_MAP_FILE = "sec_company_tickers.json"
SEC_FORM_MAP = {
    "4": "Insider Trading", "10-Q": "Quarterly Report", "10-K": "Annual Report",
    "8-K": "Material Event", "S-1": "IPO/Registration", "SC 13G": "Passive Ownership"
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
                messages=[{"role": "system", "content": "Classify as Positive, Negative, or Neutral. One word only."},
                          {"role": "user", "content": text}],
                max_tokens=5
            )
            return resp.choices[0].message.content.strip()
        except: return "Error"

    def load_sec_map(self):
        if self.sec_ticker_map: return
        headers = {"User-Agent": "Researcher rkg1717@gmail.com"}
        resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
        self.sec_ticker_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in resp.json().values()}

    def fetch_filings(self, ticker, start_date):
        self.load_sec_map()
        cik = self.sec_ticker_map.get(ticker.upper())
        if not cik: return []
        headers = {"User-Agent": "Researcher rkg1717@gmail.com"}
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        data = requests.get(url, headers=headers).json()
        f = data.get("filings", {}).get("recent", {})
        
        results = []
        for form, fdate, desc in zip(f.get("form", []), f.get("filingDate", []), f.get("primaryDocDescription", [])):
            dt = datetime.strptime(fdate, "%Y-%m-%d")
            if dt >= start_date:
                results.append({"date": fdate, "type": SEC_FORM_MAP.get(form, f"Other ({form})"), "desc": desc})
        return results

# --- UI ---
st.set_page_config(page_title="SEC Watch", layout="wide")
st.title("📊 SEC Event Impact Tracker")

with st.sidebar:
    ticker = st.text_input("Ticker", "AAPL").upper()
    days_back = st.number_input("Lookback Days", 30, 365, 90)
    duration = st.slider("Impact Window", 1, 30, 10)
    run = st.button("Run Analysis")

if run:
    analyzer = EventAnalyzer(st.secrets.get("OPENAI_API_KEY"))
    start_dt = datetime.now() - timedelta(days=days_back)
    
    with st.spinner("Syncing Data..."):
        hist = yf.download(ticker, start=start_dt - timedelta(days=30), progress=False)
        hist.index = pd.to_datetime(hist.index).date
        filings = analyzer.fetch_filings(ticker, start_dt)
        
    if hist.empty or not filings:
        st.error("No data found.")
    else:
        rows = []
        impact_col = f"{duration}d %"
        
        for f in filings:
            f_date = datetime.strptime(f['date'], "%Y-%m-%d").date()
            trading_days = [d for d in hist.index if d >= f_date]
            if not trading_days: continue
            
            entry_date = min(trading_days)
            p_start = float(hist.loc[entry_date, "Close"])
            
            def get_ret(d):
                t = entry_date + timedelta(days=d)
                fut = [day for day in hist.index if day >= t]
                if not fut: return 0.0
                return round(((float(hist.loc[min(fut), "Close"]) - p_start) / p_start) * 100, 2)

            # SAFE VOLUME RATIO: Check if index exists before accessing
            prior_df = hist.loc[hist.index < entry_date].tail(10)
            avg_v = prior_df['Volume'].mean()
            cur_v = hist.loc[entry_date, 'Volume']
            # Ensure cur_v is a single number, not a series
            if isinstance(cur_v, pd.Series): cur_v = cur_v.iloc[0]
            v_ratio = round(float(cur_v) / float(avg_v), 2) if avg_v > 0 else 1.0

            rows.append({
                "Date": f['date'], "Event": f['type'], "Sentiment": analyzer.get_sentiment(f['desc']),
                "1d %": get_ret(1), "5d %": get_ret(5), impact_col: get_ret(duration),
                "Vol_Ratio": v_ratio, "Description": f['desc']
            })
            
        df = pd.DataFrame(rows)
        
        # --- SECTION 1: HISTORICAL CHART ---
        st.subheader("Historical Performance by Event")
        summary = df.groupby("Event")[[impact_col]].mean()
        st.bar_chart(summary)
        
        # --- SECTION 2: RECENCY CHART (The "Double Decker") ---
        st.divider()
        st.subheader("Recent Activity: Price & Volume")
        recent = hist.tail(10).copy()
        recent['Daily_Ret'] = recent['Close'].pct_change() * 100
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        dates_str = [d.strftime('%m-%d') for d in recent.index]
        
        ax1.bar(dates_str, recent['Daily_Ret'].fillna(0), color=['g' if x >= 0 else 'r' for x in recent['Daily_Ret'].fillna(0)])
        ax1.set_ylabel("Price %")
        ax2.bar(dates_str, recent['Volume'], color='gray', alpha=0.3)
        ax2.set_ylabel("Volume")

        # Mark filings on chart
        for r_date in df['Date']:
            d_obj = datetime.strptime(r_date, "%Y-%m-%d").date()
            if d_obj in recent.index:
                ax1.axvline(x=d_obj.strftime('%m-%d'), color='blue', linestyle='--')

        st.pyplot(fig)

        # --- SECTION 3: DATA TABLE ---
        st.divider()
        df['Signal'] = df.apply(lambda x: "🔥 Strong" if x['Vol_Ratio'] > 1.5 and abs(x[impact_col]) > 2 else "Neutral", axis=1)
        st.dataframe(df[["Date", "Event", "Sentiment", "Signal", impact_col, "Vol_Ratio", "Description"]])
