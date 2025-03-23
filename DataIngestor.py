import logging
import requests
import yfinance as yf
import numpy as np
import streamlit as st

logger = logging.getLogger(__name__)

# === Fetch from FMP and Alpha Vantage ===

def fetch_fmp_ratios(ticker, api_key):
    url = f'https://financialmodelingprep.com/api/v3/ratios/{ticker}?apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data:
            latest = data[0]
            return {
                'Debt-to-Equity (FMP)': latest.get('debtEquityRatio'),
                'Current Ratio (FMP)': latest.get('currentRatio'),
                'ROE (%) (FMP)': latest.get('returnOnEquity') * 100 if latest.get('returnOnEquity') else None,
            }
    except Exception as e:
        logger.warning(f"FMP fetch failed for {ticker}: {e}")
    return {}

def fetch_alpha_vantage_overview(ticker, api_key):
    url = f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "Debt-to-Equity (Alpha)": data.get("DebtToEquity"),
            "Current Ratio (Alpha)": data.get("CurrentRatio"),
            "ROE (%) (Alpha)": data.get("ReturnOnEquityTTM"),
        }
    except Exception as e:
        logger.warning(f"Alpha Vantage fetch failed for {ticker}: {e}")
        return {}

# === Technicals ===

def calculate_technical_indicators(hist):
    if hist.empty:
        st.error("No historical data for technical analysis.")
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

    technicals = {
        "Current Price": latest_close,
        "RSI": round(rsi, 2) if not np.isnan(rsi) else "N/A",
        "MACD Histogram": round(macd_hist, 2),
    }
    logger.info(f"Technical indicators for {hist.index[-1].date()}: {technicals}")
    return technicals

# === IBKR Integration ===

def fetch_ibkr_historical_data(ticker, duration='1 Y'):
    try:
        from ib_insync import IB, Stock, util  # Local import to avoid event loop issues
        ib = IB()
        client_id = st.session_state.get("ibkrClientId", 1234)
        ib.connect("127.0.0.1", 7496, clientId=client_id)
        contract = Stock(ticker, "SMART", "USD")
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr=duration,
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        df = util.df(bars)
        ib.disconnect()
        if df.empty:
            return None
        df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
        df.set_index("date", inplace=True)
        return df
    except Exception as e:
        logger.warning(f"Failed to fetch IBKR historical data for {ticker}: {e}")
        return None


def fetch_ibkr_implied_volatility(ticker):
    try:
        from ib_insync import IB, Stock
        ib = IB()
        client_id = st.session_state.get("ibkrClientId", 1234)
        ib.connect("127.0.0.1", 7496, clientId=client_id)
        contract = Stock(ticker, "SMART", "USD")
        ib.qualifyContracts(contract)
        snapshot = ib.reqMktData(contract, "", False, False)
        ib.sleep(2)
        iv = snapshot.modelGreeks.impliedVolatility if snapshot.modelGreeks else None
        ib.disconnect()
        return iv
    except Exception as e:
        logger.warning(f"Could not fetch IV from IBKR for {ticker}: {e}")
        return None


# === Ingest Function ===

def ingest_data(ticker, api_keys, use_ibkr=False):
    ticker = ticker.upper()

    if use_ibkr:
        st.info(f"Attempting to fetch historical data from IBKR for {ticker}...")
        hist = fetch_ibkr_historical_data(ticker)
        iv = fetch_ibkr_implied_volatility(ticker)
    else:
        hist = None
        iv = None

    if hist is None or hist.empty:
        st.warning("Using Yahoo Finance fallback.")
        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(period="1y")
        if hist.empty:
            st.error(f"No price data found for {ticker}.")
            return {}

    # Fundamentals
    try:
        yf_data = yf.Ticker(ticker).info
    except Exception as e:
        yf_data = {}
        logger.warning(f"Failed to fetch Yahoo fundamentals: {e}")

    fmp_ratios = fetch_fmp_ratios(ticker, api_keys.get("FMP_API_KEY"))
    alpha_ratios = fetch_alpha_vantage_overview(ticker, api_keys.get("ALPHA_VANTAGE_API_KEY"))

    fundamentals = {
        "Debt-to-Equity (Yahoo)": yf_data.get("debtToEquity", "N/A"),
        "Current Ratio (Yahoo)": yf_data.get("currentRatio", "N/A"),
        "ROE (%) (Yahoo)": yf_data.get("returnOnEquity", "N/A"),
        "Free Cash Flow (Yahoo)": yf_data.get("freeCashFlow", "N/A"),
        **fmp_ratios,
        **alpha_ratios
    }

    st.subheader("Fundamentals")
    st.json(fundamentals)

    # Technicals
    technicals = calculate_technical_indicators(hist)
    if iv:
        technicals["IV (IBKR)"] = round(iv, 4)
    else:
        technicals["IV (IBKR)"] = "Unavailable"

    st.subheader("Technicals")
    st.json(technicals)

    return {
        "fundamentals": fundamentals,
        "technicals": technicals,
        "history": hist
    }
