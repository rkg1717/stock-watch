import streamlit as st
import yfinance as yf
import pandas as pd
from edgar import set_identity, Company
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
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
# SEC Identity (Required)
set_identity("rkg1717@gmail.com")
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
        with st.status("Analyzing SEC events and price impact...", expanded=True) as status:
            try:
                # Fetch stock data
                st.write("📈 Fetching stock data...")
                stock = yf.Ticker(ticker)
                hist = stock.history(start=start_date, end=end_date + timedelta(days=30))
                # Fetch SEC filings
                st.write("📋 Fetching SEC filings...")
                company = Company(ticker)
                filings = company.get_filings(form=["4", "8-K"]).to_pandas()
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
                        st.subheader("📌 2. Most Recent SEC Events (Last 10 Days)")
                        recent_filings = filings[filings['filing_date'] >= (datetime.now() - timedelta(days=10)).date()]
                        if not recent_filings.empty:
                            recent_results = results_df[results_df['Date'].isin(recent_filings['filing_date'])]
                            if not recent_results.empty:
                                fig2, ax2 = plt.subplots(figsize=(12, 6))
                                recent_pivot = recent_results.groupby(['Form_Desc', 'Days'])['Return %'].mean().unstack()
                                recent_pivot.plot(kind='bar', ax=ax2, width=0.8, color=['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A'])
                                ax2.set_xlabel('SEC Event Type')
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
