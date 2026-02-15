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
                    event_label = SEC_FORM_MAP.get(form, f"Other ({form})")
                    if event_label in EXCLUDE_EVENTS: continue
                    events.append({"date": fdate, "type": event_label, "desc": desc or form, "dt_obj": dt})
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
    
    with st.spinner(f"Analyzing {ticker}..."):
        full_hist = yf.download(ticker, start=start_dt - timedelta(days=30), end=datetime.now(), progress=False)
        filings = analyzer.fetch_sec_filings(ticker, start_dt, datetime.now())

    if full_hist.empty or not filings:
        st.error("Data retrieval failed. Please check the ticker symbol.")
    else:
        full_hist.index = pd.to_datetime(full_hist.index).date
        rows = []
        custom_col = f"pct_{duration}d"

        for ev in filings:
            ev_date = ev['dt_obj'].date()
            trading_days = [d for d in full_hist.index if d >= ev_date]
            if not trading_days: continue
            
            start_date = min(trading_days)
            p_start = float(full_hist.loc[start_date, "Close"])

            def get_stats(days_out):
                target = start_date + timedelta(days=days_out)
                future = [d for d in full_hist.index if d >= target]
                if not future: return 0.0
                p_end = float(full_hist.loc[min(future), "Close"])
                return round(((p_end - p_start) / p_start) * 100, 2)

            # Volume Ratio
            prior_vol = full_hist.loc[full_hist.index < start_date].tail(10)['Volume'].mean()
            curr_vol = full_hist.loc[start_date, 'Volume']
            v_ratio = round(float(curr_vol) / float(prior_vol), 2) if prior_vol > 0 else 1.0

            rows.append({
                "Date": ev["date"], "Event": ev["type"], "Sentiment": analyzer.get_sentiment(ev["desc"]),
                "pct_1d": get_stats(1), "pct_5d": get_stats(5), "pct_10d": get_stats(10),
                custom_col: get_stats(duration), "Vol_Ratio": v_ratio, "Desc": ev["desc"]
            })

        df = pd.DataFrame(rows)

        # --- SECTION 1: HISTORICAL ---
        st.subheader(f"1. Historical Event Impacts ({duration} Days)")
        summary = df.groupby("Event")[[ "pct_1d", "pct_5d", "pct_10d", custom_col]].mean()
        st.bar_chart(summary)

        # --- SECTION 2: RECENCY ---
        st.divider()
        st.subheader("2. Recency Check: Last 10 Trading Days")
        recent = full_hist.tail(10).copy()
        recent['Chg'] = recent['Close'].pct_change() * 100
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        x_axis = [d.strftime('%m-%d') for d in recent.index]
        
        ax1.bar(x_axis, recent['Chg'].fillna(0), color=['g' if x >= 0 else 'r' for x in recent['Chg'].fillna(0)])
        ax1.set_ylabel("Price %")
        ax1.axhline(0, color='black', linewidth=0.8)
        
        ax2.bar(x_axis, recent['Volume'], color='gray', alpha=0.4)
        ax2.set_ylabel("Volume")

        # Map filings to Chart 2
        for r in rows:
            r_dt = datetime.strptime(r['Date'], "%Y-%m-%d").date()
            if r_dt in recent.index:
                ax1.axvline(x=r_dt.strftime('%m-%d'), color='blue', linestyle='--')

        plt.xticks(rotation=45)
        st.pyplot(fig)

        # --- SECTION 3: TABLE ---
        st.divider()
        st.subheader("3. Detailed Filing Log")
        # Add Signal logic only at the table level to keep it clean
        df['Signal'] = df.apply(lambda x: "Strong" if abs(x[custom_col]) > 2.5 else "Neutral", axis=1)
        st.dataframe(df[["Date", "Event", "Sentiment", "Signal", custom_col, "Vol_Ratio", "Desc"]])
