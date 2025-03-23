# DataIngestor.py
import pandas as pd
import numpy as np
import requests
import random
import yfinance as yf
import logging
from ib_insync import IB, Stock, util

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# === IBKR Connection ===
def connect_ibkr():
    ib = IB()
    client_id = random.randint(1000, 9999)
    ib.connect("127.0.0.1", 7496, clientId=client_id)
    logger.debug("Connected to IBKR")
    return ib

def fetch_ibkr_stock_data(ib, ticker, duration='1 Y'):
    contract = Stock(ticker, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    bars = ib.reqHistoricalData(contract, endDateTime='', durationStr=duration, barSizeSetting='1 day', whatToShow='TRADES', useRTH=True)
    if not bars:
        return None
    df = util.df(bars)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
    df.set_index('date', inplace=True)
    return df

def fetch_ibkr_implied_volatility(ib, ticker):
    contract = Stock(ticker, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    ticker_data = ib.reqMktData(contract, '', False, False)
    ib.sleep(2)
    return ticker_data.modelGreeks.impliedVolatility if ticker_data.modelGreeks and ticker_data.modelGreeks.impliedVolatility is not None else None

# === Fundamental Data ===
def is_missing(value):
    return value is None or (isinstance(value, float) and np.isnan(value))

def fetch_fmp_ratios(ticker, api_key):
    url = f'https://financialmodelingprep.com/api/v3/ratios/{ticker}?apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data:
                latest = data[0]
                return {
                    'Debt-to-Equity Ratio': latest.get('debtEquityRatio'),
                    'Current Ratio': latest.get('currentRatio'),
                    'Return on Equity (%)': latest.get('returnOnEquity') * 100 if latest.get('returnOnEquity') else None,
                }
    except Exception as e:
        logger.error(f"FMP API error: {e}")
    return {}

def fetch_fmp_key_metrics(ticker, api_key):
    url = f'https://financialmodelingprep.com/api/v3/key-metrics/{ticker}?apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data:
                latest = data[0]
                return {'Free Cash Flow': latest.get('freeCashFlowPerShare')}
    except Exception as e:
        logger.error(f"FMP API error: {e}")
    return {}

def fetch_alpha_vantage_overview(ticker, api_key):
    url = f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'Debt-to-Equity Ratio': float(data.get('DebtToEquity', 'N/A')) if data.get('DebtToEquity') != 'None' else None,
                'Current Ratio': float(data.get('CurrentRatio', 'N/A')) if data.get('CurrentRatio') != 'None' else None,
                'Return on Equity (%)': float(data.get('ReturnOnEquityTTM', 'N/A')) if data.get('ReturnOnEquityTTM') != 'None' else None,
            }
    except Exception as e:
        logger.error(f"Alpha Vantage API error: {e}")
    return {}

def get_fundamental_data(ticker, api_keys):
    stock = yf.Ticker(ticker)
    yahoo_info = stock.info
    fundamentals = {
        "Debt-to-Equity Ratio": yahoo_info.get("debtToEquity", np.nan),
        "Current Ratio": yahoo_info.get("currentRatio", np.nan),
        "Free Cash Flow": yahoo_info.get("freeCashFlow", np.nan),
        "Return on Equity (%)": yahoo_info.get("returnOnEquity", np.nan),
    }
    fmp_ratios = fetch_fmp_ratios(ticker, api_keys.get("FMP_API_KEY", ""))
    for key in ["Debt-to-Equity Ratio", "Current Ratio", "Return on Equity (%)"]:
        if is_missing(fundamentals[key]) and not is_missing(fmp_ratios.get(key)):
            fundamentals[key] = fmp_ratios[key]
    fmp_key_metrics = fetch_fmp_key_metrics(ticker, api_keys.get("FMP_API_KEY", ""))
    if is_missing(fundamentals["Free Cash Flow"]) and not is_missing(fmp_key_metrics.get("Free Cash Flow")):
        fundamentals["Free Cash Flow"] = fmp_key_metrics["Free Cash Flow"]
    alpha_ratios = fetch_alpha_vantage_overview(ticker, api_keys.get("ALPHA_VANTAGE_API_KEY", ""))
    for key in ["Debt-to-Equity Ratio", "Current Ratio", "Return on Equity (%)"]:
        if is_missing(fundamentals[key]) and not is_missing(alpha_ratios.get(key)):
            fundamentals[key] = alpha_ratios[key]
    for key in fundamentals:
        if is_missing(fundamentals[key]):
            fundamentals[key] = "N/A"
    return fundamentals

def calculate_fundamentals(ticker_obj):
    try:
        bs = ticker_obj.balance_sheet
        cf = ticker_obj.cashflow
        latest_bs = bs.iloc[:, 0]
        latest_cf = cf.iloc[:, 0]
        total_liabilities = latest_bs.get('Total Liab', np.nan)
        shareholder_equity = latest_bs.get('Total Stockholder Equity', np.nan)
        debt_to_equity = total_liabilities / shareholder_equity if pd.notna(total_liabilities) and pd.notna(shareholder_equity) and shareholder_equity != 0 else np.nan
        current_assets = latest_bs.get('Total Current Assets', np.nan)
        current_liabilities = latest_bs.get('Total Current Liabilities', np.nan)
        current_ratio = current_assets / current_liabilities if pd.notna(current_assets) and pd.notna(current_liabilities) and current_liabilities != 0 else np.nan
        operating_cf = latest_cf.get("Total Cash From Operating Activities", np.nan)
        capex = latest_cf.get("Capital Expenditures", np.nan)
        free_cash_flow = operating_cf - capex if pd.notna(operating_cf) and pd.notna(capex) else np.nan
        return {
            "Debt-to-Equity Ratio": debt_to_equity,
            "Current Ratio": current_ratio,
            "Free Cash Flow": free_cash_flow,
            "Return on Equity (%)": ticker_obj.info.get("returnOnEquity", np.nan),
        }
    except Exception as e:
        logger.error(f"Error calculating fundamentals: {e}")
        return {}

# === Technical Indicators ===
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_performance(hist):
    latest_close = hist['Close'].iloc[-1]
    perf_7d = ((latest_close / hist['Close'].iloc[-min(7, len(hist))]) - 1) * 100
    perf_30d = ((latest_close / hist['Close'].iloc[-min(30, len(hist))]) - 1) * 100
    perf_60d = ((latest_close / hist['Close'].iloc[-min(60, len(hist))]) - 1) * 100
    return {"7-day Perf (%)": perf_7d, "30-day Perf (%)": perf_30d, "60-day Perf (%)": perf_60d}

def calculate_technical_indicators(hist):
    if hist.empty:
        return {}
    hist['MA20'] = hist['Close'].rolling(window=20).mean()
    ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
    ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line
    hist['MACD_Hist'] = macd_hist
    rsi = calculate_rsi(hist['Close'])
    performance = calculate_performance(hist)
    latest = hist.iloc[-1]
    return {
        "Current Price": latest['Close'],
        "RSI": rsi,
        "MACD Histogram": latest['MACD_Hist'],
        **performance
    }

def calculate_options_indicators_ibkr(ib, ticker):
    iv_snapshot = fetch_ibkr_implied_volatility(ib, ticker)
    return {"Average IV (Puts)": iv_snapshot}

# === Main Data Ingestion Function ===
def ingest_data(ticker, api_keys):
    ib = connect_ibkr()
    try:
        ibkr_hist = fetch_ibkr_stock_data(ib, ticker)
        hist = ibkr_hist if ibkr_hist is not None and not ibkr_hist.empty else yf.Ticker(ticker).history(period="1y")
        fundamentals_fallback = get_fundamental_data(ticker, api_keys)
        yfa = yf.Ticker(ticker)
        adv_fund = calculate_fundamentals(yfa)
        combined_fundamentals = {k: adv_fund.get(k, fundamentals_fallback.get(k, "N/A")) for k in set(fundamentals_fallback) | set(adv_fund)}
        technicals = calculate_technical_indicators(hist)
        options_data = calculate_options_indicators_ibkr(ib, ticker)
        return {
            "history": hist,
            "fundamentals": combined_fundamentals,
            "technicals": technicals,
            "options_data": options_data
        }
    finally:
        ib.disconnect()
