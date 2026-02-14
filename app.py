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
import matplotlib.patches as mpatches

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
    def __init__(self, api_key):
        self.openai_key = api_key
        self.sec_ticker_map = None
        self.client = openai.OpenAI(api_key=self.openai_key) if self.openai_key else None

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

    def get_market_context(self, ticker, date_obj):
        try:
            data = yf.download(ticker, start=date_obj - timedelta(days=12), end=date_obj + timedelta(days=2), progress=False)
            if data.empty: return 0, 0
            avg_vol = data['Volume'].iloc[:-1].mean()
            curr_vol = data['Volume'].iloc[-1]
            vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 0
            day_data = data.iloc[-1]
            daily_range = round(((day_data['High'] - day_data['Low']) / day_data['Close']) * 100, 2)
            return vol_ratio, daily_range
        except: return 0, 0

    def get_price_reactions(self, ticker, date_str):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            data = yf.download(ticker, start=dt-timedelta(days=5), end=dt+timedelta(days=50), progress=False)
            if data.empty: return {k: 0 for k in ["event", "d1", "d5", "d10", "d30"]}
            data.index = data.index.date
            def get_p(d):
                avail = [idx for idx in data.index if idx >= d]
                return float(data.loc[min(avail), "Close"]) if avail else 0
            return {
                "event": get_p(dt), "d1": get_p(dt+timedelta(days=1)), 
                "d5": get_p(dt+timedelta(days=5)), "d10": get_p(dt+timedelta(days=10)),
                "d30": get_p(dt+timedelta(days=30))
            }
        except: return {k: 0 for k in ["event", "d1", "d5", "d10", "d30"]}

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
    api_key = st.text_input("OpenAI API Key", type="password")
    ticker = st.text_input("Ticker Symbol", value="AAPL").upper()
    start_date_input = st.date_input("Start Date", datetime.now() - timedelta(days=90))
    duration = st.number_input("Duration (Days)", min_value=1, value=30)
    run_button = st.button("Run Analysis")

if run_button:
    if not api_key:
        st.error("Please provide an OpenAI API Key.")
    else:
        analyzer = EventPriceAnalyzer(api_key)
        start_dt = datetime.combine(start_date_input, datetime.min.time())
        end_dt = start_dt + timedelta(days=duration)
        
        with st.spinner(f"Fetching events for {ticker}..."):
            events = analyzer.fetch_sec_filings(ticker, start_dt, end_dt)
        
        if not events:
            st.warning(f"No relevant events found for {ticker}.")
        else:
            rows = []
            progress_bar = st.progress(0)
            for i, ev in enumerate(events):
                p = analyzer.get_price_reactions(ticker, ev["date"])
                vol_ratio, day_vol = analyzer.get_market_context(ticker, ev["dt_obj"])
                def chg(p1, p2): return round(((p2 - p1) / p1) * 100, 2) if p1 > 0 and p2 > 0 else 0
                
                rows.append({
                    "Date": ev["date"], "Event": ev["type"], "Sentiment": analyzer.get_sentiment(ev["desc"]),
                    "Vol_Ratio": vol_ratio, "Day_Volatility_%": day_vol, "Price": p["event"], 
                    "pct_1d": chg(p["event"], p["d1"]), "pct_5d": chg(p["event"], p["d5"]), 
                    "pct_10d": chg(p["event"], p["d10"]), "pct_30d": chg(p["event"], p["d30"]),
                    "Desc": ev["desc"]
                })
                progress_bar.progress((i + 1) / len(events))

            df = pd.DataFrame(rows)

            # --- DISPLAY RESULTS ---
            col1, col2 = st.columns(2)
            summary_30d = df.groupby("Event")["pct_30d"].mean()
            
            with col1:
                st.subheader("Performance Summary (30d)")
                st.success(f"🚀 Best: {summary_30d.idxmax()} ({summary_30d.max()}% avg)")
                st.error(f"📉 Worst: {summary_30d.idxmin()} ({summary_30d.min()}% avg)")
            
            # --- CHART ---
            fig, ax = plt.subplots(figsize=(10, 5))
            plot_cols = ["pct_1d", "pct_5d", "pct_10d", "pct_30d"]
            summary_data = df.groupby("Event")[plot_cols].mean().reindex(columns=plot_cols)
            colors = ['#e31a1c', '#1f78b4', '#ff7f00', '#636363'] 
            summary_data.plot(kind="bar", ax=ax, color=colors, edgecolor='black', linewidth=0.7)
            ax.set_title(f"{ticker} Avg Event Reaction")
            ax.axhline(0, color='black', linewidth=1)
            plt.xticks(rotation=45, ha="right")
            st.pyplot(fig)

            # --- DATA TABLE ---
            st.subheader("Detailed Report")
            st.dataframe(df)
            
            # CSV Download
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV Report", data=csv, file_name=f"{ticker}_report.csv", mime='text/csv')