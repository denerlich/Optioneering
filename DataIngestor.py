import logging
import requests
import yfinance as yf
import numpy as np
import streamlit as st  # Required for explicit logging in Streamlit UI

logger = logging.getLogger(__name__)

def fetch_fmp_ratios(ticker, api_key):
    url = f'https://financialmodelingprep.com/api/v3/ratios/{ticker}?apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data:
            latest = data[0]
            ratios = {
                'Debt-to-Equity Ratio (FMP)': latest.get('debtEquityRatio'),
                'Current Ratio (FMP)': latest.get('currentRatio'),
                'ROE (%) (FMP)': latest.get('returnOnEquity') * 100 if latest.get('returnOnEquity') else None,
            }
            logger.info(f"FMP ratios for {ticker}: {ratios}")
            return ratios
        else:
            logger.warning(f"No FMP ratios data returned for {ticker}.")
            return {}
    except Exception as e:
        logger.error(f"FMP Ratios fetch failed for {ticker}: {e}")
        return {}

def fetch_alpha_vantage_overview(ticker, api_key):
    url = f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        overview = {
            "Debt-to-Equity Ratio (Alpha)": data.get("DebtToEquity"),
            "Current Ratio (Alpha)": data.get("CurrentRatio"),
            "ROE (%) (Alpha)": data.get("ReturnOnEquityTTM"),
        }
        logger.info(f"Alpha Vantage overview for {ticker}: {overview}")
        return overview
    except Exception as e:
        logger.error(f"Alpha Vantage fetch failed for {ticker}: {e}")
        return {}

def calculate_technical_indicators(hist):
    if hist.empty:
        logger.error("Historical data empty, cannot calculate technicals.")
        return {}

    latest_close = hist['Close'].iloc[-1]
    delta = hist['Close'].diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = -delta.clip(upper=0).rolling(window=14).mean()
    rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else np.nan
    rsi = 100 - (100 / (1 + rs)) if not np.isnan(rs) else np.nan

    ema12 = hist['Close'].ewm(span=12).mean()
    ema26 = hist['Close'].ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    macd_hist = (macd_line - signal_line).iloc[-1]

    performance = {
        "7-day Perf (%)": (latest_close / hist['Close'].iloc[-7] - 1) * 100,
        "30-day Perf (%)": (latest_close / hist['Close'].iloc[-30] - 1) * 100,
        "60-day Perf (%)": (latest_close / hist['Close'].iloc[-60] - 1) * 100
    }

    technicals = {
        "Current Price": latest_close,
        "RSI": rsi if not np.isnan(rsi) else "N/A",
        "MACD Histogram": macd_hist,
        **performance
    }
    logger.info(f"Technicals: {technicals}")
    return technicals

# Single, correctly defined ingest_data function with explicit Streamlit logging
def ingest_data(ticker, api_keys):
    ticker = ticker.upper()
    ticker_obj = yf.Ticker(ticker)

    # Fetch Historical Data
    hist = ticker_obj.history(period="1y")
    if hist.empty:
        error_msg = f"Historical data empty for {ticker}."
        logger.error(error_msg)
        st.error(error_msg)
        return {}

    # Fetching fundamental data
    yf_fund = ticker_obj.info
    fmp_ratios = fetch_fmp_ratios(ticker, api_keys.get('FMP_API_KEY'))
    alpha_data = fetch_alpha_vantage_overview(ticker, api_keys.get('ALPHA_VANTAGE_API_KEY'))

    combined_fundamentals = {
        "Debt-to-Equity (Yahoo)": yf_fund.get("debtToEquity", "N/A"),
        "Current Ratio (Yahoo)": yf_fund.get("currentRatio", "N/A"),
        "ROE (%) (Yahoo)": yf_fund.get("returnOnEquity", "N/A"),
        "Free Cash Flow (Yahoo)": yf_fund.get("freeCashFlow", "N/A"),
        **fmp_ratios,
        **alpha_data
    }

    st.subheader(f"Retrieved Fundamental Data for {ticker}")
    st.json(combined_fundamentals)

    # Technical indicators calculation
    technicals = calculate_technical_indicators(hist)
    if not technicals:
        error_msg = f"Failed to calculate technical indicators for {ticker}."
        logger.error(error_msg)
        st.error(error_msg)
        return {}

    st.subheader(f"Retrieved Technical Data for {ticker}")
    st.json(technicals)

    return {
        "fundamentals": combined_fundamentals,
        "technicals": technicals,
        "history": hist
    }
