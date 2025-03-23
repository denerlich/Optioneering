import streamlit as st
import pandas as pd
import nest_asyncio
import logging
from DataIngestor import ingest_data
from LLMAdviser import get_grok_insight
from StreamlitUI import render_ui

# Setup
nest_asyncio.apply()
st.set_page_config(page_title="Options Bot", layout="wide")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Session state
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {}
if "tickers" not in st.session_state:
    st.session_state["tickers"] = []

# Upload config
st.sidebar.header("Upload Configuration File")
uploaded_file = st.sidebar.file_uploader("Upload Excel file with Tickers and API Codes", type=["xlsx"])
if uploaded_file:
    xl = pd.ExcelFile(uploaded_file)
    if "Tickers" in xl.sheet_names:
        tickers_df = pd.read_excel(uploaded_file, sheet_name="Tickers")
        st.session_state["tickers"] = tickers_df["Ticker"].dropna().tolist()
    if "APICodes" in xl.sheet_names:
        api_df = pd.read_excel(uploaded_file, sheet_name="APICodes")
        st.session_state["api_keys"] = dict(zip(api_df["API"], api_df["Secret"]))
    st.sidebar.success("File uploaded successfully!")

# Checkbox to use IBKR
use_ibkr = st.sidebar.checkbox("Use IBKR (via TWS)?", value=True)

# Thresholds
thresholds = {
    "Debt-to-Equity": st.sidebar.number_input("Max Debt-to-Equity Ratio", 0.0, 10.0, 0.5, 0.1),
    "Current Ratio": st.sidebar.number_input("Min Current Ratio", 0.0, 10.0, 1.5, 0.1),
    "ROE": st.sidebar.number_input("Min Return on Equity (%)", 0.0, 100.0, 15.0, 1.0),
    "RSI_low": st.sidebar.number_input("RSI Lower Bound", 0, 100, 40),
    "RSI_high": st.sidebar.number_input("RSI Upper Bound", 0, 100, 60),
}

# Main logic
def main():
    if not st.session_state["tickers"]:
        st.warning("Please upload a config file with tickers.")
        return

    ticker = st.selectbox("Select Ticker Symbol", st.session_state["tickers"])
    run_button = st.button("Run Analysis")

    if run_button and ticker:
        st.info(f"Analyzing {ticker}...")
        try:
            data = ingest_data(ticker, st.session_state["api_keys"], use_ibkr=use_ibkr)
        except Exception as e:
            st.error(f"Error ingesting data: {e}")
            return

        if not data or "fundamentals" not in data:
            st.error("Missing data for score calculation: 'fundamentals'")
            return

        try:
            grok_insight = get_grok_insight(ticker, data["fundamentals"], data["technicals"], st.session_state["api_keys"].get("GROQ_API_KEY", ""))
        except Exception:
            grok_insight = "No Grok insight available."

        render_ui(data, thresholds, grok_insight, ticker)

if __name__ == "__main__":
    main()
