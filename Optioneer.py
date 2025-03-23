# Optioneer.py
import streamlit as st
import pandas as pd
import asyncio
import nest_asyncio
from DataIngestor import ingest_data
from LLMAdviser import get_grok_insight
from StreamlitUI import render_ui

# Apply nest_asyncio
nest_asyncio.apply()

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
    else:
        st.sidebar.error("File must contain 'Tickers' and 'APICodes' tabs with valid data.")

# Scoring and recommendation logic
def is_missing(value):
    return value is None or (isinstance(value, float) and pd.isna(value))

def calculate_scores(fund, tech, thresholds):
    fund_score = 0
    if not is_missing(fund.get("Debt-to-Equity Ratio")) and fund["Debt-to-Equity Ratio"] <= thresholds["Debt-to-Equity"]:
        fund_score += 10
    if not is_missing(fund.get("Current Ratio")) and fund["Current Ratio"] >= thresholds["Current Ratio"]:
        fund_score += 10
    if not is_missing(fund.get("Free Cash Flow")) and fund["Free Cash Flow"] > 0:
        fund_score += 10
    if not is_missing(fund.get("Return on Equity (%)")) and fund["Return on Equity (%)"] >= thresholds["ROE"]:
        fund_score += 10
    fund_score = (fund_score / 40) * 10 * 0.6

    tech_score = 0
    rsi = tech.get("RSI", 0)
    if thresholds["RSI_low"] <= rsi <= thresholds["RSI_high"]:
        tech_score += 10
    if tech.get("MACD Histogram", 0) > 0:
        tech_score += 10
    for perf in ["7-day Perf (%)", "30-day Perf (%)", "60-day Perf (%)"]:
        value = tech.get(perf, 0)
        if value > 2:
            tech_score += 10
    tech_score = (tech_score / 40) * 10 * 0.4

    overall_score = fund_score + tech_score
    return fund_score, tech_score, overall_score

def get_option_recommendation(score, current_price):
    if score >= 8:
        return {"Expiration": "60 days", "Delta": 50, "Strike": current_price}
    elif score >= 6:
        return {"Expiration": "45 days", "Delta": 35, "Strike": current_price * 0.97}
    else:
        return {"Expiration": "30 days", "Delta": 20, "Strike": current_price * 0.90}

# Main orchestration
def main():
    if not st.session_state["tickers"]:
        render_ui(None, {}, "", "")
        return

    ticker_input = st.selectbox("Select Ticker Symbol", st.session_state["tickers"], index=0)
    run_button = st.button("Run Analysis")

    if run_button and ticker_input:
        ticker = ticker_input.upper()
        with st.spinner("Fetching data..."):
            data = ingest_data(ticker, st.session_state["api_keys"])
            thresholds = {"Debt-to-Equity": 0.5, "Current Ratio": 1.5, "ROE": 15.0, "RSI_low": 40, "RSI_high": 60}
            fund_score, tech_score, overall_score = calculate_scores(data["fundamentals"], data["technicals"], thresholds)
            option_rec = get_option_recommendation(overall_score, data["technicals"]["Current Price"])
            data.update({"fund_score": fund_score, "tech_score": tech_score, "overall_score": overall_score, "option_rec": option_rec})
            grok_insight = get_grok_insight(ticker, data["fundamentals"], data["technicals"], st.session_state["api_keys"].get("GROQ_API_KEY", ""))
            render_ui(data, thresholds, grok_insight, ticker)

if __name__ == "__main__":
    main()
