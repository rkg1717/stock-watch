import streamlit as st
import yfinance as yf
import pandas as pd
from edgar import set_identity, Company
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# SEC Identity (Required)
set_identity("rkg1717@gmail.com")

st.set_page_config(page_title="Insider/Form 4 Watch", layout="wide")
st.title("📈 Stock Performance vs. SEC Filings")

# Sidebar Inputs
with st.sidebar:
    ticker = st.text_input("Enter Ticker", value="TSLA").upper()
    duration = st.slider("Days to track after filing", 1, 30, 5)
    st.info("Tracking Form 4 (Insider Trading) and 8-K (Current Events)")
    
    st.divider()
    st.subheader("📊 Historical Price Analysis")
    start_date = st.date_input("Analysis Start Date", value=datetime.now() - timedelta(days=90))
    analysis_days = st.number_input("Days After Start to Analyze", min_value=1, max_value=365, value=30)
    run_analysis = st.button("Run Historical Analysis")

if run_analysis:
    with st.status("Running historical analysis...", expanded=True) as h_status:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, period=min(analysis_days + 1, 365))
            
            if not hist.empty:
                hist['Daily Return %'] = hist['Close'].pct_change() * 100
                hist['Volume'] = hist['Volume'].astype(int)
                
                st.subheader(f"Price Action: {start_date} to {start_date + timedelta(days=analysis_days)}")
                st.dataframe(hist[['Open', 'High', 'Low', 'Close', 'Daily Return %', 'Volume']], use_container_width=True)
                
                avg_return = hist['Daily Return %'].mean()
                st.metric("Average Daily Return %", f"{avg_return:.2f}%")
                
                h_status.update(label="Analysis Complete!", state="complete")
            else:
                st.error("No data found for selected date range")
        except Exception as e:
            st.error(f"Error: {str(e)}")

if ticker:
    with st.status(f"Analyzing {ticker}...", expanded=True) as status:
        # 1. Fetch Stock Data
        st.write("Fetching market data...")
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        
        # 2. Fetch SEC Filings
        st.write("Searching SEC EDGAR...")
        try:
            company = Company(ticker)
            filings = company.get_filings(form=["4", "8-K"]).to_pandas()
            # Filter for recent filings
            filings['filing_date'] = pd.to_datetime(filings['filing_date'])
            filings = filings[filings['filing_date'] > (datetime.now() - timedelta(days=365))]
        except:
            filings = pd.DataFrame()

        rows = []
        if not hist.empty and not filings.empty:
            st.write("Mapping filings to price action...")
            
            for _, filing in filings.iterrows():
                f_date = filing['filing_date'].date()
                
                # Find the closest trading day on or after filing
                trading_days = hist.index[hist.index.date >= f_date]
                
                if len(trading_days) > duration:
                    start_date = trading_days[0]
                    end_date = trading_days[duration]
                    
                    start_price = hist.loc[start_date, 'Close']
                    end_price = hist.loc[end_date, 'Close']
                    pc_change = ((end_price - start_price) / start_price) * 100
                    
                    rows.append({
                        "Date": f_date,
                        "Form": filing['form'],
                        "Price at Filing": round(start_price, 2),
                        "Price After": round(end_price, 2),
                        f"% Change ({duration}d)": round(pc_change, 2),
                        "Event": f"{filing['form']} Filing"
                    })

        status.update(label="Analysis Complete!", state="complete", expanded=False)

        # --- DISPLAY RESULTS ---
        if rows:
            df = pd.DataFrame(rows)
            impact_col = f"% Change ({duration}d)"
            
            st.subheader(f"1. Average Performance ({duration} Days Post-Filing)")
            chart_data = df.groupby("Event")[[impact_col]].mean()
            st.bar_chart(chart_data)
            
            st.divider()
            
            st.subheader("2. Recency Check: Last 10 Trading Days")
            recent = hist.tail(10).copy()
            recent['Chg'] = (recent['Close'].pct_change() * 100).fillna(0)
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
            x_labs = [d.strftime('%m-%d') for d in recent.index]
            
            ax1.bar(x_labs, recent['Chg'], color=['g' if x >= 0 else 'r' for x in recent['Chg']])
            ax1.set_ylabel("Price %")
            ax1.set_title(f"{ticker} Recent Momentum")
            
            ax2.bar(x_labs, recent['Volume'], color='gray', alpha=0.4)
            ax2.set_ylabel("Volume")
            
            plt.xticks(rotation=45)
            st.pyplot(fig)
            
            st.divider()
            
            st.subheader("3. Historical Data Log")
            st.dataframe(df, use_container_width=True)
        else:
            if not filings.empty:
                st.warning("No trading data matches these filing dates (might be too recent).")
            elif hist.empty:
                st.error(f"Could not find stock data for {ticker}.")
            else:
                st.warning(f"No Form 4 or 8-K filings found for {ticker} in the last year.")
else:
    st.info("Enter a stock ticker in the sidebar to begin.")

