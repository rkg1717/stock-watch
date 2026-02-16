import streamlit as st
import yfinance as yf
import pandas as pd
from edgar import Company
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
# Ticker to (Company Name, CIK) mapping
TICKER_TO_CIK = {
    'TSLA': ('Tesla Inc', '0001318605'),
    'AAPL': ('Apple Inc', '0000320193'),
    'MSFT': ('Microsoft Corporation', '0000789019'),
    'GOOGL': ('Alphabet Inc', '0001652044'),
    'AMZN': ('Amazon.com Inc', '0001018724'),
    'NVDA': ('NVIDIA Corporation', '0001045810'),
    'META': ('Meta Platforms Inc', '0001326801'),
    'NFLX': ('Netflix Inc', '0001065280'),
    'JPM': ('JPMorgan Chase & Co', '0000019617'),
    'BAC': ('Bank of America Corporation', '0000070858'),
    'WMT': ('Walmart Inc', '0000104169'),
    'DIS': ('The Walt Disney Company', '0001018724'),
    'VZ': ('Verizon Communications Inc', '0000732733'),
    'PG': ('The Procter & Gamble Company', '0000080424'),
    'JNJ': ('Johnson & Johnson', '0000200406'),
    'INTC': ('Intel Corporation', '0000050104'),
    'AMD': ('Advanced Micro Devices Inc', '0000002488'),
    'CSCO': ('Cisco Systems Inc', '0000858877'),
    'CRM': ('Salesforce Inc', '0001108524'),
    'ADBE': ('Adobe Inc', '0000884896'),
    'PYPL': ('PayPal Holdings Inc', '0001633917'),
    'UBER': ('Uber Technologies Inc', '0001543151'),
    'LYFT': ('Lyft Inc', '0001759816'),
    'SPOT': ('Spotify Technology S.A.', '0001564408'),
    'TSLA': ('Tesla Inc', '0001318605'),
    'F': ('Ford Motor Company', '0000037996'),
    'GM': ('General Motors Company', '0001467858'),
    'TM': ('Toyota Motor Corporation', '0000912057'),
    'GE': ('General Electric Company', '0000040545'),
    'IBM': ('International Business Machines Corporation', '0000051143'),
    'HPQ': ('HP Inc', '0000047217'),
}
st.set_page_config(page_title="SEC Event Price Impact Analyzer", layout="wide")
st.title("📊 SEC Event Price Impact Analysis")
# Sidebar Inputs
with st.sidebar:
    ticker = st.text_input("Enter Ticker", value="TSLA").upper()
    if ticker:
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Analysis Start Date", value=datetime(datetime.now().year - 1, 10, 1))
        with col2:
            end_date = st.date_input("Analysis End Date", value=datetime.now())
        run_analysis = st.button("Run SEC Event Analysis", use_container_width=True)
if ticker:
    if run_analysis:
        # Check if ticker is in our database
        if ticker.upper() not in TICKER_TO_CIK:
            st.error(f"❌ Ticker '{ticker}' not found in database.")
            st.info(f"📋 Available tickers: {', '.join(sorted(TICKER_TO_CIK.keys()))}")
            st.stop()
        company_name, cik = TICKER_TO_CIK[ticker.upper()]
        with st.status("Analyzing SEC events and price impact...", expanded=True) as status:
            try:
                # Fetch stock data
                st.write("📈 Fetching stock data...")
                stock = yf.Ticker(ticker)
                hist = stock.history(start=start_date, end=end_date + timedelta(days=30))
                # Fetch SEC filings
                st.write(f"📋 Fetching SEC filings for {company_name}...")
                company = Company(company_name, cik)
                # Fetch SEC filings
                st.write(f"📋 Fetching SEC filings for {company_name}...")
                company = Company(company_name, cik)
                # Get both Form 4 and Form 8-K filings
                filings_4 = company.get_all_filings(filing_type="4")
                filings_8k = company.get_all_filings(filing_type="8-K")
                # Combine them
                if filings_4 is not None:
                    filings_4 = filings_4.to_pandas()
                else:
                    filings_4 = pd.DataFrame()
                if filings_8k is not None:
                    filings_8k = filings_8k.to_pandas()
                else:
                    filings_8k = pd.DataFrame()
                filings = pd.concat([filings_4, filings_8k], ignore_index=True)
                filings['filing_date'] = pd.to_datetime(filings['filing_date']).dt.date
                filings = filings[(filings['filing_date'] >= start_date) & (filings['filing_date'] <= end_date)]
                filings['filing_date'] = pd.to_datetime(filings['filing_date']).dt.date
                filings = filings[(filings['filing_date'] >= start_date) & (filings['filing_date'] <= end_date)]
                if hist.empty or filings.empty:
                    st.error("No data found for this date range")
                else:
                    # Calculate price changes at different intervals
                    results = []
                    days_to_track = [1, 3, 10, 30]
                    for _, filing in filings.iterrows():
                        f_date = filing['filing_date']
                        form_type = filing['form']
                        # Find trading days after filing
                        trading_days = hist.index[hist.index.date >= f_date]
                        if len(trading_days) > 0:
                            filing_price = hist.loc[trading_days[0], 'Close']
                            for days in days_to_track:
                                if len(trading_days) > days:
                                    future_price = hist.loc[trading_days[days], 'Close']
                                    pct_change = ((future_price - filing_price) / filing_price) * 100
                                    results.append({
                                        'Date': f_date,
                                        'Form': form_type,
                                        'Days': days,
                                        'Return %': round(pct_change, 2)
                                    })
                    if results:
                        results_df = pd.DataFrame(results)
                        status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
                        # --- DISPLAY CHARTS ---
                        st.markdown("---")
                        st.subheader("📊 1. Historical SEC Event Price Impact")
                        # Pivot data for charting
                        pivot_data = results_df.groupby(['Form', 'Days'])['Return %'].mean().unstack()
                        fig, ax = plt.subplots(figsize=(12, 6))
                        pivot_data.plot(kind='bar', ax=ax, width=0.8)
                        ax.set_xlabel('SEC Form Type')
                        ax.set_ylabel('Average Return %')
                        ax.set_title(f'{ticker} - Average Price Change After SEC Filings (Historical)')
                        ax.legend(title='Days After Filing', labels=['1 Day', '3 Days', '10 Days', '30 Days'])
                        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
                        ax.grid(axis='y', alpha=0.3)
                        plt.xticks(rotation=45)
                        plt.tight_layout()
                        st.pyplot(fig)
                        # --- CURRENT EVENTS ---
                        st.markdown("---")
                        st.subheader("📌 2. Most Recent SEC Events (Last 10 Days)")
                        recent_filings = filings[filings['filing_date'] >= (datetime.now() - timedelta(days=10)).date()]
                        if not recent_filings.empty:
                            recent_results = results_df[results_df['Date'].isin(recent_filings['filing_date'].dt.date)]
                            if not recent_results.empty:
                                fig2, ax2 = plt.subplots(figsize=(12, 6))
                                recent_pivot = recent_results.groupby(['Form', 'Days'])['Return %'].mean().unstack()
                                recent_pivot.plot(kind='bar', ax=ax2, width=0.8, color=['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A'])
                                ax2.set_xlabel('SEC Form Type')
                                ax2.set_ylabel('Average Return %')
                                ax2.set_title(f'{ticker} - Recent SEC Event Price Impact (Last 10 Days)')
                                ax2.legend(title='Days After Filing', labels=['1 Day', '3 Days', '10 Days', '30 Days'])
                                ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
                                ax2.grid(axis='y', alpha=0.3)
                                plt.xticks(rotation=45)
                                plt.tight_layout()
                                st.pyplot(fig2)
                            else:
                                st.info("No price data available yet for recent filings")
                        else:
                            st.info("No SEC filings in the last 10 days")
                        # --- AI INTERPRETATION ---
                        st.markdown("---")
                        st.subheader("🤖 3. AI Sentiment Analysis")
                        # Calculate summary statistics
                        avg_1day = results_df[results_df['Days'] == 1]['Return %'].mean()
                        avg_3day = results_df[results_df['Days'] == 3]['Return %'].mean()
                        avg_10day = results_df[results_df['Days'] == 10]['Return %'].mean()
                        avg_30day = results_df[results_df['Days'] == 30]['Return %'].mean()
                        form_4_avg = results_df[results_df['Form'] == '4'][['Days', 'Return %']].groupby('Days')['Return %'].mean()
                        form_8k_avg = results_df[results_df['Form'] == '8-K'][['Days', 'Return %']].groupby('Days')['Return %'].mean()
                        analysis_text = f"""Based on analysis of {len(filings)} SEC filings from {start_date} to {end_date}:
**Form 4 (Insider Trading):**
- 1 Day Impact: {form_4_avg.get(1, 0):.2f}%
- 30 Day Impact: {form_4_avg.get(30, 0):.2f}%
**Form 8-K (Current Events):**
- 1 Day Impact: {form_8k_avg.get(1, 0):.2f}%
- 30 Day Impact: {form_8k_avg.get(30, 0):.2f}%
**Overall Trend:**
- 1 Day: {avg_1day:.2f}% | 3 Day: {avg_3day:.2f}% | 10 Day: {avg_10day:.2f}% | 30 Day: {avg_30day:.2f}%"""
                        # Determine sentiment
                        if avg_30day > 2:
                            sentiment = "✅ POSITIVE"
                            interpretation = "SEC events are generally followed by positive price movement over the long term."
                        elif avg_30day < -2:
                            sentiment = "❌ NEGATIVE"
                            interpretation = "SEC events are generally followed by negative price movement over the long term."
                        else:
                            sentiment = "⚪ NEUTRAL"
                            interpretation = "SEC events show mixed or minimal price impact over time."
                        st.write(f"**Sentiment: {sentiment}**")
                        st.write(interpretation)
                        st.code(analysis_text, language="text")
                        # --- DATA TABLES ---
                        st.markdown("---")
                        st.subheader("📊 4. Detailed Data")
                        st.write("**All SEC Events with Price Impact:**")
                        st.dataframe(results_df, use_container_width=True)
                        st.write("**SEC Filings in Period:**")
                        st.dataframe(filings[['filing_date', 'form']].rename(columns={'filing_date': 'Date', 'form': 'Form Type'}), use_container_width=True)
                    else:
                        st.error("No matching trading data for SEC filings")
            except Exception as e:
                st.error(f"Error: {str(e)}")
                import traceback
                st.write(traceback.format_exc())
    else:
        st.info("👈 Enter a stock ticker in the sidebar to begin")

