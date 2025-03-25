import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

@retry(wait=wait_exponential(multiplier=1, min=2, max=5), stop=stop_after_attempt(3),
       retry=retry_if_exception_type(requests.RequestException))
def fetch_stockanalysis_html(ticker):
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/"
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.text

def extract_stockanalysis_data(ticker):
    try:
        html = fetch_stockanalysis_html(ticker)
        soup = BeautifulSoup(html, "html.parser")
        data = {"Ticker": ticker}

        stat_section = soup.find("div", class_="stats")
        if not stat_section:
            return {"Ticker": ticker, "Error": "Stats section not found"}

        rows = stat_section.find_all("div", class_="snapshot")
        for row in rows:
            for item in row.find_all("div", recursive=False):
                label = item.find("span", class_="label")
                value = item.find("span", class_="value")
                if label and value:
                    data[label.text.strip()] = value.text.strip()

        return data
    except Exception as e:
        logger.error(f"Extraction error for {ticker}: {e}")
        return {"Ticker": ticker, "Error": str(e)}

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def score_ticker(row):
    def safe_float(val):
        try:
            return float(str(val).replace("%", "").replace(",", ""))
        except:
            return 0.0

    pe = safe_float(row.get("P/E"))
    rsi = safe_float(row.get("RSI"))
    roe = safe_float(row.get("ROE"))
    iv = safe_float(row.get("Volatility"))

    fundamentals_score = int(pe < 20) + int(roe > 10)
    technicals_score = int(30 < rsi < 50) + int(iv > 1.5)

    return fundamentals_score, technicals_score

def process_file(file, chunk_size, rate_delay, pause_between_chunks):
    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
    tickers = df.iloc[:, 0].dropna().astype(str).str.upper().unique().tolist()
    results = []

    for chunk in chunk_list(tickers, chunk_size):
        for ticker in chunk:
            with st.spinner(f"Fetching {ticker}"):
                row_data = extract_stockanalysis_data(ticker)
                results.append(row_data)
                time.sleep(rate_delay)
        time.sleep(pause_between_chunks)

    return pd.DataFrame(results)

def main():
    st.set_page_config(page_title="📊 StockAnalysis Analyzer", layout="wide")
    st.title("📊 StockAnalysis Smart Analyzer")

    uploaded_file = st.file_uploader("📁 Upload Tickers File (CSV/XLSX)", type=["xlsx", "xls", "csv"])

    chunk_size = st.sidebar.number_input("Chunk Size", min_value=10, max_value=200, value=50)
    rate_delay = st.sidebar.number_input("Delay (sec)", min_value=0.5, max_value=5.0, value=1.0)
    pause_between_chunks = st.sidebar.number_input("Pause Between Chunks (sec)", min_value=2, max_value=30, value=5)

    if uploaded_file and st.button("🔍 Extract + Analyze"):
        df_data = process_file(uploaded_file, chunk_size, rate_delay, pause_between_chunks)
        st.dataframe(df_data)

        analysis_results = []
        for _, row in df_data.iterrows():
            fscore, tscore = score_ticker(row)
            analysis_results.append({
                "Ticker": row["Ticker"],
                "Fundamental Score": fscore,
                "Technical Score": tscore,
            })

        st.subheader("📈 Scoring Analysis")
        st.dataframe(pd.DataFrame(analysis_results))

if __name__ == "__main__":
    main()
