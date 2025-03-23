import logging
import yfinance as yf
import numpy as np
import streamlit as st
import time
from ib_insync import IB, Stock, util

logger = logging.getLogger(__name__)

# Helper to connect to IBKR (with random session-safe client ID)
def connect_ibkr(max_retries=3):
    ib = IB()
    for attempt in range(max_retries):
        try:
            ib.connect("127.0.0.1", 7496, clientId=123)
            if ib.isConnected():
                return ib
        except Exception as e:
            print(f"[Attempt {attempt+1}] IBKR connection failed: {e}")
            time.sleep(2)
    raise RuntimeError("Unable to connect to IBKR after multiple attempts.")

def fetch_ibkr_historical_data(ib, ticker, duration="1 Y"):
    contract = Stock(ticker, "SMART", "USD")
    ib.qualifyContracts(contract)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=duration,
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True
    )
    if not bars:
        return None
    df = util.df(bars)
    df.set_index("date", inplace=True)
    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
    return df

def calculate_technical_indicators(hist):
    if hist.empty:
        return {}

    close = hist['Close']
    latest_close = close.iloc[-1]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = -delta.clip(upper=0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    macd_line = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    signal = macd_line.ewm(span=9).mean()
    macd_hist = (macd_line - signal).iloc[-1]

    return {
        "Current Price": latest_close,
        "RSI": rsi.iloc[-1],
        "MACD Histogram": macd_hist,
        "7-day Perf (%)": ((latest_close / close.iloc[-7]) - 1) * 100,
        "30-day Perf (%)": ((latest_close / close.iloc[-30]) - 1) * 100,
        "60-day Perf (%)": ((latest_close / close.iloc[-60]) - 1) * 100
    }

def ingest_data(ticker, api_keys=None, use_ibkr=False):
    ticker = ticker.upper()
    hist = None
    ib = None

    if use_ibkr:
        try:
            ib = connect_ibkr()
            hist = fetch_ibkr_historical_data(ib, ticker)
            if hist is not None and not hist.empty:
                st.info("✅ IBKR data used.")
        except Exception as e:
            st.warning(f"IBKR failed: {e}")
            logger.warning(f"IBKR fallback for {ticker}: {e}")
        finally:
            if ib: ib.disconnect()

    if hist is None or hist.empty:
        st.warning("⚠️ Using Yahoo Finance fallback.")
        try:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period="1y")
            fund_info = ticker_obj.info
        except Exception as e:
            logger.error(f"Yahoo Finance failed for {ticker}: {e}")
            return {}

        fundamentals = {
            "Debt-to-Equity": fund_info.get("debtToEquity", "N/A"),
            "Current Ratio": fund_info.get("currentRatio", "N/A"),
            "ROE (%)": fund_info.get("returnOnEquity", "N/A"),
            "Free Cash Flow": fund_info.get("freeCashFlow", "N/A"),
        }
    else:
        # For simplicity, fundamentals only via yfinance if IBKR doesn't provide them directly
        ticker_obj = yf.Ticker(ticker)
        fund_info = ticker_obj.info
        fundamentals = {
            "Debt-to-Equity": fund_info.get("debtToEquity", "N/A"),
            "Current Ratio": fund_info.get("currentRatio", "N/A"),
            "ROE (%)": fund_info.get("returnOnEquity", "N/A"),
            "Free Cash Flow": fund_info.get("freeCashFlow", "N/A"),
        }

    if hist is None or hist.empty:
        st.error(f"No price data found for {ticker}.")
        return {}

    technicals = calculate_technical_indicators(hist)

    return {
        "fundamentals": fundamentals,
        "technicals": technicals,
        "history": hist
    }
