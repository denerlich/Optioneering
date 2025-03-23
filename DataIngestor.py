import streamlit as st
import pandas as pd
import numpy as np
import requests
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

# Helper Functions
def fetch_fmp_ratios(ticker, api_key):
    url = f'https://financialmodelingprep.com/api/v3/ratios/{ticker}?apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if response.ok and data:
            latest = data[0]
            return {
                'Debt-to-Equity Ratio (FMP)': latest.get('debtEquityRatio'),
                'Current Ratio': latest.get('currentRatio'),
                'ROE (%)': latest.get('returnOnEquity') * 100 if latest.get('returnOnEquity') else None,
            }
    except Exception as e:
        logger.error(f"Error fetching FMP Ratios for {ticker}: {e}")
    return {}

def fetch_fmp_key_metrics(ticker, api_key):
    url = f'https://financialmodelingprep.com/api/v3/key-metrics/{ticker}?apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            data = response.json()
            if data:
                return {'Free Cash Flow per Share': data[0].get('freeCashFlowPerShare')}
    except Exception as e:
        logger.error(f"Error fetching FMP Key Metrics for {ticker}: {e}")
    return {}

def fetch_alpha_vantage_overview(ticker, api_key):
    url = f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            data = response.json()
            return {
                'Debt-to-Equity Ratio': float(data.get('DebtToEquity', np.nan)),
                'Current Ratio': float(data.get('CurrentRatio', np.nan)),
                'ROE (%)': float(data.get('ReturnOnEquityTTM', np.nan)),
            }
    except Exception as e:
        logger.error(f"Alpha Vantage error for {ticker}: {e}")
    return {}

def get_yfinance_fundamentals(ticker):
    ticker_obj = yf.Ticker(ticker)
    info = ticker_obj.info
    return {
        "Debt-to-Equity Ratio": info.get("debtToEquity"),
        "Current Ratio": info.get("currentRatio"),
        "Free Cash Flow": info.get("freeCashFlow"),
        "ROE (%)": info.get("returnOnEquity") * 100 if info.get("returnOnEquity") else np.nan
    }

def calculate_technical_indicators(hist):
    if hist.empty:
        return {}
    close = hist['Close']
    rsi_period = 14
    delta = hist['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
    ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_histogram = macd_line - signal_line

    latest_close = hist['Close'].iloc[-1]
    perf_7d = (latest_close / hist['Close'].iloc[-7] - 1) * 100
    perf_30d = (latest_close / hist['Close'].iloc[-30] - 1) * 100
    perf_60d = (latest_close / hist['Close'].iloc[-60] - 1) * 100
    
    return {
        "Current Price": latest_close,
        "RSI": rsi.iloc[-1],
        "MACD Histogram": (ema12 - ema26).iloc[-1],
        "7-day Perf (%)": perf_7d,
        "30-day Perf (%)": perf_30d,
        "60-day Perf (%)": perf_60d
    }

# Main explicit ingest_data function:
def ingest_data(ticker, api_keys):
    ticker = ticker.upper()
    
    yf_ticker = yf.Ticker(ticker)
    hist = yf_ticker.history(period="1y")
    if hist.empty:
        logger.error(f"No historical data found for {ticker}.")
        return {}

    # Fundamental data explicitly listed from each source
    yf_fundamentals = get_fundamental_data(ticker)
    fmp_ratios = fetch_fmp_ratios(ticker, api_keys.get('FMP_API_KEY', ''))
    fmp_metrics = fetch_fmp_key_metrics(ticker, api_keys.get('FMP_API_KEY', ''))
    alpha_overview = fetch_alpha_vantage_overview(ticker, api_keys.get('ALPHA_VANTAGE_API_KEY', ''))

    combined_fundamentals = {
        "Debt-to-Equity Ratio (Yahoo)": yf_ticker.info.get("debtToEquity", "N/A"),
        "Current Ratio (Yahoo)": yf_ticker.info.get("currentRatio", "N/A"),
        "ROE (%) (Yahoo)": yf_ticker.info.get("returnOnEquity", np.nan) * 100 if yf_ticker.info.get("returnOnEquity") else "N/A",
        "Free Cash Flow (Yahoo)": yf_ticker.info.get("freeCashFlow", "N/A"),
        "Debt-to-Equity (FMP)": fmp_ratios.get("Debt-to-Equity Ratio", "N/A"),
        "Current Ratio (FMP)": fmp_ratios.get("Current Ratio", "N/A"),
        "ROE (FMP %)": fmp_ratios.get("ROE (%)", "N/A"),
        "Free Cash Flow per Share (FMP)": fmp_metrics.get("Free Cash Flow per Share", "N/A"),
        "Debt-to-Equity (AlphaVantage)": alpha_overview.get("Debt-to-Equity Ratio", "N/A"),
        "Current Ratio (AlphaVantage)": alpha_overview.get("Current Ratio", "N/A"),
        "ROE (%) (AlphaVantage)": alpha_overview.get("ROE (%)", "N/A"),
    }

    technicals = calculate_technical_indicators(hist)
    
    # Log data for debugging
    logger.info(f"Combined Fundamentals: {combined_fundamentals}")
    logger.info(f"Technicals: {technicals}")

    return {
        "fundamentals": combined_fundamentals,
        "technicals": technicals,
        "history": hist
    }

# === Streamlit Table Display (Explicitly listing all fetched data) ===
if __name__ == "__main__":
    st.title("Detailed Data Ingestion")

    ticker_input = st.text_input("Enter Ticker:", "AAPL")
    if st.button("Fetch and Display Data"):
        data = ingest_data(ticker_input, st.session_state["api_keys"])

        st.subheader("Fetched Fundamental Data")
        st.table(pd.DataFrame(data["fundamentals"].items(), columns=["Indicator", "Value"]))

        st.subheader("Fetched Technical Indicators")
        st.table(pd.DataFrame(data["technicals"].items(), columns=["Indicator", "Value"]))

        st.subheader("Recent Historical Prices (Last 5 days)")
        st.table(data["history"].tail(5))

        if data["history"].empty:
            st.warning("No historical data retrieved, please verify the ticker.")
        else:
            st.plotly_chart(
                go.Figure(go.Candlestick(
                    x=data["history"].index,
                    open=data["history"]["Open"],
                    high=data["history"]["High"],
                    low=data["history"]["Low"],
                    close=data["history"]["Close"],
                )).update_layout(title=f"{ticker} Candlestick Chart"),
                use_container_width=True
            )
