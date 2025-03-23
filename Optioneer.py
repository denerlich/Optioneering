import streamlit as st
import pandas as pd
import asyncio
import nest_asyncio
import logging
from DataIngestor import ingest_data
from LLMAdviser import get_grok_insight
from StreamlitUI import render_ui

# Apply nest_asyncio
nest_asyncio.apply()

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Set page config as the first Streamlit command
st.set_page_config(page_title="AI Options Selling Bot with Grok", layout="wide")

# Session state initialization
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {}
if "tickers" not in st.session_state:
    st.session_state["tickers"] = []

# Sidebar for file upload
st.sidebar.header("Upload Configuration File")
uploaded_file = st.sidebar.file_uploader("Upload Excel file with Tickers and API Codes", type=["xlsx"])

if uploaded_file:
    xl = pd.ExcelFile(uploaded_file)
    if "Tickers" in xl.sheet_names:
        tickers_df = pd.read_excel(uploaded_file, sheet_name="Tickers")
        st.session_state["tickers"] = tickers_df["Ticker"].dropna().tolist()[:200]
    if "APICodes" in xl.sheet_names:
        api_df = pd.read_excel(uploaded_file, sheet_name="APICodes")
        st.session_state["api_keys"] = dict(zip(api_df["API"], api_df["Secret"]))
    if st.session_state["tickers"] and st.session_state["api_keys"]:
        st.sidebar.success("File uploaded successfully!")
        logger.info("Configuration file uploaded and processed successfully.")
    else:
        st.sidebar.error("File must contain 'Tickers' and 'APICodes' tabs with valid data.")
        logger.error("Configuration file is missing required tabs or data.")

# Scoring function included directly here (enhanced implementation)
def calculate_scores(fundamentals, technicals, thresholds):
    fund_score = 0
    tech_score = 0

    # Fundamental Scoring
    if fundamentals.get("Debt-to-Equity", float('inf')) <= thresholds["Debt-to-Equity"]:
        fund_score += 1
    if fundamentals.get("Current Ratio", 0) >= thresholds["Current Ratio"]:
        fund_score += 1
    if fundamentals.get("ROE", 0) >= thresholds["ROE"]:
        fund_score += 1

    # Technical Scoring
    rsi = technicals.get("RSI", 50)
    if thresholds["RSI_low"] <= rsi <= thresholds["RSI_high"]:
        tech_score += 1
    if technicals.get("Price_vs_SMA50", 0) >= 0:
        tech_score += 1
    if technicals.get("MACD", 0) > technicals.get("MACD_signal", 0):
        tech_score += 1

    overall_score = fund_score + tech_score
    return fund_score, tech_score, overall_score

# Main function
def main():
    if not st.session_state["tickers"]:
        st.warning("Please upload an Excel file with tickers and API keys to proceed.")
        logger.warning("No tickers available. Awaiting file upload.")
        return

    ticker_input = st.selectbox("Select Ticker Symbol", st.session_state["tickers"], index=0)
    run_button = st.button("Run Analysis")

    if run_button and ticker_input:
        ticker = ticker_input.upper()
        logger.info(f"Initiating analysis for ticker: {ticker}")

        # Fetch data
        try:
            data = ingest_data(ticker, st.session_state["api_keys"])
            logger.debug(f"Data fetched for {ticker}: {data}")
        except Exception as e:
            st.error(f"Error fetching data for {ticker}: {e}")
            logger.exception(f"Exception during data ingestion for {ticker}")
            return

        # Define thresholds
        thresholds = {
            "Debt-to-Equity": st.sidebar.number_input("Max Debt-to-Equity Ratio", min_value=0.0, value=0.5, step=0.1),
            "Current Ratio": st.sidebar.number_input("Min Current Ratio", min_value=0.0, value=1.5, step=0.1),
            "ROE": st.sidebar.number_input("Min Return on Equity (%)", value=15.0, step=1.0),
            "RSI_low": st.sidebar.number_input("RSI Lower Bound", min_value=0, max_value=100, value=40, step=1),
            "RSI_high": st.sidebar.number_input("RSI Upper Bound", min_value=0, max_value=100, value=60, step=1),
        }

        # Calculate scores
        try:
            fund_score, tech_score, overall_score = calculate_scores(
                data["fundamentals"], data["technicals"], thresholds
            )
            logger.info(f"Scores calculated - Fundamental: {fund_score}, Technical: {tech_score}, Overall: {overall_score}")
        except KeyError as e:
            st.error(f"Missing data for score calculation: {e}")
            logger.error(f"KeyError during score calculation: {e}")
            return

        # Option recommendation (make sure this function is available)
        try:
            option_rec = get_option_recommendation(overall_score, data["technicals"]["Current Price"])
            logger.info(f"Option recommendation: {option_rec}")
        except KeyError as e:
            st.error(f"Technical data missing: Unable to retrieve 'Current Price'. Check data source.")
            logger.error(f"KeyError: 'Current Price' not found in technical data for {ticker}")
            return

        # Get Grok insight
        try:
            grok_insight = get_grok_insight(ticker, data["fundamentals"], data["technicals"], st.session_state["api_keys"].get("GROQ_API_KEY", ""))
            logger.info(f"Grok insight retrieved for {ticker}")
        except Exception as e:
            st.error(f"Error retrieving Grok insight: {e}")
            logger.exception(f"Exception during Grok insight retrieval for {ticker}")
            grok_insight = "Grok analysis unavailable."

        # Render UI
        render_ui(data, thresholds, grok_insight, ticker)

if __name__ == "__main__":
    main()
