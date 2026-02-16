import streamlit as st
import yfinance as yf
import pandas as pd
from edgar import Company
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import requests
# SEC Form Type Descriptions - Most Impactful Forms
SEC_FORM_DESCRIPTIONS = {
    '3': 'Initial Insider Filing',
    '4': 'Insider Trading',
    '5': 'Annual Insider Report',
    '8-K': 'Current Events',
    '10-K': 'Annual Report',
    '10-Q': 'Quarterly Report',
    '10-K/A': 'Annual Amendment',
    '10-Q/A': 'Quarterly Amendment',
    '13D': 'Major Shareholder Filing',
    '13G': 'Large Holding Notice',
    '13D/A': 'Major Shareholder Amendment',
    '13G/A': 'Large Holding Amendment',
    '14A': 'Proxy Statement',
    '14D-1': 'Tender Offer',
    '14D-9': 'Tender Response',
    '14E': 'Tender Offer Rules',
    '20-F': 'Foreign Annual Report',
    '20-F/A': 'Foreign Amendment',
    '6-K': 'Foreign Periodic Report',
    'S-1': 'IPO Registration',
    'S-3': 'Short Form Registration',
    'S-4': 'Merger Registration',
    'F-1': 'Foreign IPO',
    'F-3': 'Foreign Short Form',
    'F-4': 'Foreign Merger',
    '424B5': 'Final Prospectus',
    'DEF14A': 'Definitive Proxy',
    'DEFM14A': 'Merger Proxy',
}
def get_form_description(form_code):
    return SEC_FORM_DESCRIPTIONS.get(form_code, form_code)
st.set_page_config(page_title="SEC Event Price Impact Analyzer", layout="wide")
st.title("📊 SEC Event Price Impact Analysis")
# Sidebar Inputs
with st.sidebar:
    ticker = st.text_input("Enter Ticker", value="TSLA").upper()
    if ticker:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Analysis Start Date", value=datetime(datetime.now().year - 1, 10, 1))
        with col2:
            end_date = st.date_input("Analysis End Date", value=datetime.now())
        col3, col4 = st.columns(2)
        with col3:
            st.caption("Recent Event Period:")
        with col4:
            current_event_days = st.number_input("Days After Event", min_value=1, max_value=365, value=30)
        run_analysis = st.button("Run SEC Event Analysis", use_container_width=True)
if ticker and run_analysis:
    with st.status("Analyzing SEC events and price impact...", expanded=True) as status:
        try:
            # Fetch stock data
            st.write("📈 Fetching stock data...")
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date + timedelta(days=30))
            # Fetch SEC filings
            st.write("📋 Fetching SEC filings...")
            # Look up CIK from SEC using ticker
            sec_cik_url = "https://www.sec.gov/files/company_tickers.json"
            # SEC requires a User-Agent header
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(sec_cik_url, headers=headers, timeout=10)
            response.raise_for_status()
            companies = response.json()
            # Search for matching company by ticker
            cik = None
            company_name = None
            for cik_data in companies.values():
                if cik_data['ticker'].upper() == ticker.upper():
                    cik = str(cik_data['cik_str']).zfill(10)
                    company_name = cik_data['title']
                    break
            if not cik or not company_name:
                st.error(f"Could not find company for ticker {ticker}. Please verify the ticker is correct.")
                st.stop()
            st.write(f"Found: {company_name} (CIK: {cik})")
            # Now fetch SEC filings
            company = Company(company_name, cik)
            filings = company.get_filings(form=["4", "8-K"]).to_pandas()
            filings['filing_date'] = pd.to_datetime(filings['filing_date']).dt.date
            filings = filings[(filings['filing_date'] >= start_date) & (filings['filing_date'] <= end_date)]
            if hist.empty or filings.empty:
                st.error("No data found for this date range")
            else:
                # Calculate price changes at different intervals for historical
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
                    st.subheader(f"📊 1. Historical SEC Event Price Impact ({start_date} to {end_date})")
                    # Map form codes to descriptions and count occurrences
                    results_df['Form_Desc'] = results_df['Form'].apply(get_form_description)
                    pivot_data = results_df.groupby(['Form_Desc', 'Days'])['Return %'].mean().unstack()
                    # Get counts for each form type
                    form_counts = results_df.groupby('Form_Desc').size()
                    fig, ax = plt.subplots(figsize=(12, 6))
                    pivot_data.plot(kind='bar', ax=ax, width=0.8)
                    # Add count labels on top of bars
                    for i, (form_desc, count) in enumerate(form_counts.items()):
                        ax.text(i, ax.get_ylim()[1] * 0.95, f'n={count}', ha='center', va='top', fontsize=9, fontweight='bold')
                    ax.set_xlabel('SEC Event Type')
                    ax.set_ylabel('Average Return %')
                    ax.set_title(f'{ticker} - Average Price Change After SEC Events')
                    ax.legend(title='Days After Filing', labels=['1 Day', '3 Days', '10 Days', '30 Days'])
                    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
                    ax.grid(axis='y', alpha=0.3)
                    plt.xticks(rotation=45)
                    plt.tight_layout()
                    st.pyplot(fig)
                    # --- CURRENT EVENTS ---
                    st.markdown("---")
                    recent_cutoff = datetime.now().date() - timedelta(days=current_event_days)
                    st.subheader(f"📌 2. Recent SEC Events (Last {current_event_days} Days)")
                    recent_filings = filings[filings['filing_date'] >= recent_cutoff]
                    if not recent_filings.empty:
                        # Re-calculate with current_event_days
                        recent_results = []
                        for _, filing in recent_filings.iterrows():
                            f_date = filing['filing_date']
                            form_type = filing['form']
                            trading_days = hist.index[hist.index.date >= f_date]
                            if len(trading_days) > 0:
                                filing_price = hist.loc[trading_days[0], 'Close']
                                for days in [0, 3, 10, 30]:
                                    if days == 0:
                                        pct_change = 0
                                    elif len(trading_days) > days:
                                        future_price = hist.loc[trading_days[days], 'Close']
                                        pct_change = ((future_price - filing_price) / filing_price) * 100
                                    else:
                                        continue
                                    recent_results.append({
                                        'Date': f_date,
                                        'Form': form_type,
                                        'Days': days,
                                        'Return %': round(pct_change, 2)
                                    })
                        if recent_results:
                            recent_results_df = pd.DataFrame(recent_results)
                            recent_results_df['Form_Desc'] = recent_results_df['Form'].apply(get_form_description)
                            fig2, ax2 = plt.subplots(figsize=(12, 6))
                            recent_pivot = recent_results_df.groupby(['Form_Desc', 'Days'])['Return %'].mean().unstack()
                            # Get counts for recent events
                            recent_form_counts = recent_results_df.groupby('Form_Desc').size()
                            recent_pivot.plot(kind='bar', ax=ax2, width=0.8, color=['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A'])
                            # Add count labels on top
                            for i, (form_desc, count) in enumerate(recent_form_counts.items()):
                                ax2.text(i, ax2.get_ylim()[1] * 0.95, f'n={count}', ha='center', va='top', fontsize=9, fontweight='bold')
                            ax2.set_xlabel('SEC Event Type')
                            ax2.set_ylabel('Average Return %')
                            ax2.set_title(f'{ticker} - Recent SEC Event Price Impact (Last {current_event_days} Days)')
                            ax2.legend(title='Days After Filing', labels=['0 Days', '3 Days', '10 Days', '30 Days'])
                            ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
                            ax2.grid(axis='y', alpha=0.3)
                            plt.xticks(rotation=45)
                            plt.tight_layout()
                            st.pyplot(fig2)
                        else:
                            st.info("No price data available yet for recent filings")
                    else:
                        st.info(f"No SEC filings in the last {current_event_days} days")
                    # --- AI INTERPRETATION ---
                    st.markdown("---")
                    st.subheader("🤖 3. AI Sentiment Analysis")
                    # Calculate summary statistics
                    avg_1day = results_df[results_df['Days'] == 1]['Return %'].mean()
                    avg_3day = results_df[results_df['Days'] == 3]['Return %'].mean()
                    avg_10day = results_df[results_df['Days'] == 10]['Return %'].mean()
                    avg_30day = results_df[results_df['Days'] == 30]['Return %'].mean()
                    form_4_data = results_df[results_df['Form'] == '4']
                    form_8k_data = results_df[results_df['Form'] == '8-K']
                    form_4_avg_30 = form_4_data[form_4_data['Days'] == 30]['Return %'].mean() if not form_4_data.empty else 0
                    form_8k_avg_30 = form_8k_data[form_8k_data['Days'] == 30]['Return %'].mean() if not form_8k_data.empty else 0
                    analysis_text = f"""Based on analysis of {len(filings)} SEC filings from {start_date} to {end_date}:
Form 4 (Insider Trading):
- 30 Day Average Impact: {form_4_avg_30:.2f}%
Form 8-K (Current Events):
- 30 Day Average Impact: {form_8k_avg_30:.2f}%
Overall Trend (All Events):
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
                    filings_display = filings[['filing_date', 'form']].rename(columns={'filing_date': 'Date', 'form': 'Form Type'})
                    st.dataframe(filings_display, use_container_width=True)
                else:
                    st.error("No matching trading data for SEC filings")
        except Exception as e:
            st.error(f"Error: {str(e)}")
            import traceback
            st.write(traceback.format_exc())
else:
    if ticker:
        st.info("👈 Click 'Run SEC Event Analysis' to start")
    else:
        st.info("👈 Enter a stock ticker in the sidebar to begin")
