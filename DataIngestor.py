import logging
import requests
import yfinance as yf
import numpy as np

logger = logging.getLogger(__name__)

# Explicit fundamental data fetching from YFinance, FMP, and Alpha Vantage
def fetch_fmp_ratios(ticker, api_key):
    url = f'https://financialmodelingprep.com/api/v3/ratios/{ticker}?apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if response.ok and data:
            latest = data[0]
            return {
                'Debt-to-Equity Ratio': latest.get('debtEquityRatio'),
                'Current Ratio': latest.get('currentRatio'),
                'Return on Equity (%)': latest.get('returnOnEquity') * 100 if latest.get('returnOnEquity') else None,
            }
        else:
            logger.error(f"Failed to fetch FMP ratios for {ticker}: Empty or invalid response.")
            return {}
    except Exception as e:
        logger.error(f"Exception occurred while fetching FMP ratios for {ticker}: {e}")
        return {}

def fetch_alpha_vantage_overview(ticker, api_key):
    url = f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}'
    try:
        logger.debug(f"Alpha Vantage request URL: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Alpha Vantage data for {ticker} fetched successfully.")
        return data
    except Exception as e:
        logger.error(f"Alpha Vantage fetch failed: {e}")
        return {}

def calculate_technical_indicators(hist):
    if hist.empty:
        logger.error("Historical data empty, cannot calculate technicals.")
        return {}

    latest_close = hist['Close'].iloc[-1]
    rsi = 100 - (100 / (1 + hist['Close'].diff().clip(lower=0).rolling(14).mean().iloc[-1] /
                        abs(hist['Close'].diff().clip(upper=0).rolling(window=14).mean().iloc[-1]))

    macd = hist['Close'].ewm(span=12).mean() - hist['Close'].ewm(span=26).mean()
    macd_hist = (macd - macd.ewm(span=9).mean()).iloc[-1]

    performance = {
        "7-day Perf (%)": (latest_close / hist['Close'].iloc[-7] - 1) * 100,
        "30-day Perf (%)": (latest_close / hist['Close'].iloc[-30] - 1) * 100,
        "60-day Perf (%)": (latest_close / hist['Close'].iloc[-60] - 1) * 100
    }

    technicals = {
        "Current Price": latest_close,
        "RSI": rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else None,
        "MACD Histogram": macd_hist,
        **performance
    }
    logger.info(f"Calculated technical indicators: {technicals}")
    return technicals

# Full Ingestion Function (fully explicit)
def ingest_data(ticker, api_keys):
    data = {}
    ticker_obj = yf.Ticker(ticker)

    # Fetch Historical Data
    hist = ticker_obj.history(period="1y")
    if hist.empty:
        logger.error(f"Historical data empty for {ticker}.")
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

    technicals = calculate_technical_indicators(hist)

    return {
        "fundamentals": combined_fundamentals,
        "technicals": technicals,
        "history": hist
    }

# clearly log all data
def ingest_data(ticker, api_keys):
    data = ingest_data(ticker, api_keys)
    if not data:
        st.error("Data ingestion returned empty. Check logs.")
    else:
        st.write("### Explicitly Retrieved Fundamental Data:")
        st.json(data["fundamentals"])

        st.write("### Explicitly Retrieved Technical Data:")
        st.json(data["technicals"])

    return data
