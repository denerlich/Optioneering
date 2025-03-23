import streamlit as st
import pandas as pd
import numpy as np
import requests
import random
import datetime
import plotly.graph_objects as go
import io
import yfinance as yf
import asyncio
import nest_asyncio
import logging
from ib_insync import *
from groq import Groq  # Groq API integration

# === Logging Configuration ===
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# === Asyncio Setup ===
nest_asyncio.apply()
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

pd.options.display.float_format = '{:.2f}'.format

# === Session State for API Keys and Tickers ===
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {}
if "tickers" not in st.session_state:
    st.session_state["tickers"] = []

# === Excel File Upload ===
st.sidebar.header("Upload Configuration File")
uploaded_file = st.sidebar.file_uploader("Upload Excel file with Tickers and API Codes", type=["xlsx"])

if uploaded_file:
    # Read Excel file
    xl = pd.ExcelFile(uploaded_file)
    
    # Load Tickers from "Tickers" tab
    if "Tickers" in xl.sheet_names:
        tickers_df = pd.read_excel(uploaded_file, sheet_name="Tickers")
        st.session_state["tickers"] = tickers_df["Ticker"].dropna().tolist()[:200]  # Limit to 200 tickers
    
    # Load API Keys from "APICodes" tab
    if "APICodes" in xl.sheet_names:
        api_df = pd.read_excel(uploaded_file, sheet_name="APICodes")
        st.session_state["api_keys"] = dict(zip(api_df["API"], api_df["Secret"]))
    
    if st.session_state["tickers"] and st.session_state["api_keys"]:
        st.sidebar.success("File uploaded successfully!")
    else:
        st.sidebar.error("File must contain 'Tickers' and 'APICodes' tabs with valid data.")

# === API Key Access ===
FMP_API_KEY = st.session_state["api_keys"].get("FMP_API_KEY", "")
ALPHA_VANTAGE_API_KEY = st.session_state["api_keys"].get("ALPHA_VANTAGE_API_KEY", "")
GROQ_API_KEY = st.session_state["api_keys"].get("GROQ_API_KEY", "")

# === Groq Client Initialization ===
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    st.error("GROQ_API_KEY not found. Please upload a valid Excel file.")
    st.stop()

# === IBKR Connection ===
def connect_ibkr():
    ib = IB()
    if "ibkrClientId" not in st.session_state:
        st.session_state["ibkrClientId"] = random.randint(1000, 9999)
    ib.connect("127.0.0.1", 7496, clientId=st.session_state["ibkrClientId"])
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
    if ticker_data.modelGreeks and ticker_data.modelGreeks.impliedVolatility is not None:
        return ticker_data.modelGreeks.impliedVolatility
    return None

# === Fundamental Data ===
def is_missing(value):
    return value is None or (isinstance(value, float) and np.isnan(value))

def fetch_fmp_ratios(ticker):
    url = f'https://financialmodelingprep.com/api/v3/ratios/{ticker}?apikey={FMP_API_KEY}'
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
    except:
        return {}

def fetch_fmp_key_metrics(ticker):
    url = f'https://financialmodelingprep.com/api/v3/key-metrics/{ticker}?apikey={FMP_API_KEY}'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data:
                latest = data[0]
                return {'Free Cash Flow': latest.get('freeCashFlowPerShare')}
    except:
        return {}

def fetch_alpha_vantage_overview(ticker):
    url = f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={ALPHA_VANTAGE_API_KEY}'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'Debt-to-Equity Ratio': float(data.get('DebtToEquity', 'N/A')) if data.get('DebtToEquity') != 'None' else None,
                'Current Ratio': float(data.get('CurrentRatio', 'N/A')) if data.get('CurrentRatio') != 'None' else None,
                'Return on Equity (%)': float(data.get('ReturnOnEquityTTM', 'N/A')) if data.get('ReturnOnEquityTTM') != 'None' else None,
            }
    except:
        return {}

def get_fundamental_data(ticker):
    stock = yf.Ticker(ticker)
    yahoo_info = stock.info
    fundamentals = {
        "Debt-to-Equity Ratio": yahoo_info.get("debtToEquity", np.nan),
        "Current Ratio": yahoo_info.get("currentRatio", np.nan),
        "Free Cash Flow": yahoo_info.get("freeCashFlow", np.nan),
        "Return on Equity (%)": yahoo_info.get("returnOnEquity", np.nan),
    }
    
    fmp_ratios = fetch_fmp_ratios(ticker)
    for key in ["Debt-to-Equity Ratio", "Current Ratio", "Return on Equity (%)"]:
        if is_missing(fundamentals[key]) and not is_missing(fmp_ratios.get(key)):
            fundamentals[key] = fmp_ratios[key]

    fmp_key_metrics = fetch_fmp_key_metrics(ticker)
    if is_missing(fundamentals["Free Cash Flow"]) and not is_missing(fmp_key_metrics.get("Free Cash Flow")):
        fundamentals["Free Cash Flow"] = fmp_key_metrics["Free Cash Flow"]

    alpha_ratios = fetch_alpha_vantage_overview(ticker)
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
        fs = ticker_obj.financials
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
        revenue_growth = np.nan
        if fs.shape[1] >= 2:
            rev_rows = [row for row in fs.index if "Total Revenue" in row]
            if rev_rows:
                latest_revenue = fs.loc[rev_rows[0], fs.columns[0]]
                previous_revenue = fs.loc[rev_rows[0], fs.columns[1]]
                if pd.notna(latest_revenue) and pd.notna(previous_revenue) and previous_revenue != 0:
                    revenue_growth = ((latest_revenue - previous_revenue) / previous_revenue) * 100
        fundamentals = {
            "Debt-to-Equity Ratio": debt_to_equity,
            "Current Ratio": current_ratio,
            "Free Cash Flow": free_cash_flow,
            "Revenue Growth (%)": revenue_growth,
            "Return on Equity (%)": ticker_obj.info.get("returnOnEquity", np.nan),
        }
        return fundamentals
    except:
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
    technicals = {
        "Current Price": latest['Close'],
        "RSI": rsi,
        "MACD Histogram": latest['MACD_Hist'],
    }
    technicals.update(performance)
    return technicals

def calculate_options_indicators_ibkr(ib, ticker):
    iv_snapshot = fetch_ibkr_implied_volatility(ib, ticker)
    return {"Average IV (Puts)": iv_snapshot}

# === Grok Integration ===
def get_grok_insight(ticker, fundamentals, technicals):
    prompt = f"""
    Analyze the stock {ticker} for selling put options based on the following data:
    Fundamentals: {fundamentals}
    Technicals: {technicals}
    Provide a brief insight on whether this is a good candidate for selling puts aggressively (ATM/ITM), moderately (near ATM), or conservatively (OTM), and suggest an expiration and Delta.
    """
    try:
        response = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",  # Adjust model as needed
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Grok API error: {e}")
        return "Grok analysis unavailable."

# === Scoring and Verdict ===
def calculate_scores(fund, tech, thresholds):
    fund_score = 0
    if not is_missing(fund.get("Debt-to-Equity Ratio")) and fund["Debt-to-Equity Ratio"] <= thresholds["Debt-to-Equity"]:
        fund_score += 10
    elif not is_missing(fund.get("Debt-to-Equity Ratio")) and fund["Debt-to-Equity Ratio"] <= 1.0:
        fund_score += 5
    if not is_missing(fund.get("Current Ratio")) and fund["Current Ratio"] >= thresholds["Current Ratio"]:
        fund_score += 10
    elif not is_missing(fund.get("Current Ratio")) and fund["Current Ratio"] >= 1.0:
        fund_score += 5
    if not is_missing(fund.get("Free Cash Flow")) and fund["Free Cash Flow"] > 0:
        fund_score += 10
    if not is_missing(fund.get("Revenue Growth (%)")) and fund["Revenue Growth (%)"] >= thresholds["Revenue Growth"]:
        fund_score += 10
    elif not is_missing(fund.get("Revenue Growth (%)")) and fund["Revenue Growth (%)"] >= 5:
        fund_score += 5
    if not is_missing(fund.get("Return on Equity (%)")) and fund["Return on Equity (%)"] >= thresholds["ROE"]:
        fund_score += 10
    elif not is_missing(fund.get("Return on Equity (%)")) and fund["Return on Equity (%)"] >= 10:
        fund_score += 5
    fund_score = (fund_score / 50) * 10 * 0.6

    tech_score = 0
    rsi = tech.get("RSI", 0)
    if thresholds["RSI_low"] <= rsi <= thresholds["RSI_high"]:
        tech_score += 10
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        tech_score += 5
    if tech.get("MACD Histogram", 0) > 0:
        tech_score += 10
    for perf in ["7-day Perf (%)", "30-day Perf (%)", "60-day Perf (%)"]:
        value = tech.get(perf, 0)
        if value > 2:
            tech_score += 10
        elif -2 <= value <= 2:
            tech_score += 5
    tech_score = (tech_score / 50) * 10 * 0.4

    overall_score = fund_score + tech_score
    return fund_score, tech_score, overall_score

def get_option_recommendation(score, current_price):
    if score >= 8:
        return {"Expiration": "60 days", "Delta": 50, "Strike": current_price}
    elif score >= 6:
        return {"Expiration": "45 days", "Delta": 35, "Strike": current_price * 0.97}
    else:
        return {"Expiration": "30 days", "Delta": 20, "Strike": current_price * 0.90}

# === Streamlit UI ===
st.set_page_config(page_title="AI Options Selling Bot with Grok", layout="wide")
st.title("AI-Driven Options Selling Bot with Grok Integration")

if not st.session_state["tickers"]:
    st.warning("Please upload an Excel file with tickers and API keys to proceed.")
    st.stop()

st.sidebar.header("Adjust Thresholds")
thresholds = {
    "Debt-to-Equity": st.sidebar.number_input("Max Debt-to-Equity Ratio", min_value=0.0, value=0.5, step=0.1),
    "Current Ratio": st.sidebar.number_input("Min Current Ratio", min_value=0.0, value=1.5, step=0.1),
    "Revenue Growth": st.sidebar.number_input("Min Revenue Growth (%)", value=10.0, step=1.0),
    "ROE": st.sidebar.number_input("Min Return on Equity (%)", value=15.0, step=1.0),
    "RSI_low": st.sidebar.number_input("RSI Lower Bound", min_value=0, max_value=100, value=40, step=1),
    "RSI_high": st.sidebar.number_input("RSI Upper Bound", min_value=0, max_value=100, value=60, step=1),
}

ticker_input = st.selectbox("Select Ticker Symbol", st.session_state["tickers"], index=0)
run_button = st.button("Run Analysis")

if run_button and ticker_input:
    ticker = ticker_input.upper()
    ib = connect_ibkr()
    
    with st.spinner("Fetching data..."):
        ibkr_hist = fetch_ibkr_stock_data(ib, ticker)
        hist = ibkr_hist if ibkr_hist is not None and not ibkr_hist.empty else yf.Ticker(ticker).history(period="1y")
        
        fundamentals_fallback = get_fundamental_data(ticker)
        yfa = yf.Ticker(ticker)
        adv_fund = calculate_fundamentals(yfa)
        combined_fundamentals = {k: adv_fund.get(k, fundamentals_fallback.get(k, "N/A")) for k in set(fundamentals_fallback) | set(adv_fund)}
        
        technicals = calculate_technical_indicators(hist)
        options_data = calculate_options_indicators_ibkr(ib, ticker)
    
    ib.disconnect()

    fund_score, tech_score, overall_score = calculate_scores(combined_fundamentals, technicals, thresholds)
    option_rec = get_option_recommendation(overall_score, technicals["Current Price"])
    grok_insight = get_grok_insight(ticker, combined_fundamentals, technicals)

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Fundamental Indicators (60%)")
        fund_df = pd.DataFrame(list(combined_fundamentals.items()), columns=["Indicator", "Value"])
        st.table(fund_df)
        st.write(f"Fundamental Score: {fund_score:.1f}/6.0")
    
    with col2:
        st.subheader("Technical Indicators (40%)")
        tech_df = pd.DataFrame(list(technicals.items()), columns=["Indicator", "Value"])
        st.table(tech_df)
        st.write(f"Technical Score: {tech_score:.1f}/4.0")
    
    with col3:
        st.subheader("AI Recommendation")
        st.write(f"Overall Score: {overall_score:.1f}/10")
        st.write(f"Recommended Put: {option_rec['Expiration']}, {option_rec['Delta']} Delta, Strike ${option_rec['Strike']:.2f}")
        st.write(f"Strategy: {'Aggressive (ATM/ITM)' if overall_score >= 8 else 'Moderate (Near ATM)' if overall_score >= 6 else 'Conservative (OTM)'}")
        st.subheader("Grok Insight")
        st.write(grok_insight)

    if not hist.empty:
        fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
        fig.update_layout(title=f"{ticker} Candlestick Chart", xaxis_title="Date", yaxis_title="Price")
        st.plotly_chart(fig, use_container_width=True)
