import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import openai

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

@retry(wait=wait_exponential(multiplier=1, min=2, max=5), stop=stop_after_attempt(3),
       retry=retry_if_exception_type(requests.RequestException))
def fetch_finviz_html(ticker):
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.text

def extract_finviz_data(ticker):
    try:
        html = fetch_finviz_html(ticker)
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="snapshot-table2")
        if not table:
            return {"Ticker": ticker, "Error": "Data table not found"}
        cells = table.find_all("td")
        data = {"Ticker": ticker}
        for i in range(0, len(cells), 2):
            data[cells[i].get_text(strip=True)] = cells[i+1].get_text(strip=True)
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
    rsi = safe_float(row.get("RSI (14)"))
    roe = safe_float(row.get("ROE"))
    iv = safe_float(str(row.get("Volatility", "0")).split()[0])

    fundamentals_score = int(pe < 20) + int(roe > 10)
    technicals_score = int(30 < rsi < 50) + int(iv > 1.5)

    return fundamentals_score, technicals_score

def get_groq_insight(ticker, fundamentals, technicals, api_key):
    prompt = f"""
    Analyze the stock {ticker} for selling put options based on:
    Fundamentals: {fundamentals}
    Technicals: {technicals}

    Suggest if it's suitable for selling puts aggressively (ATM/ITM), moderately (near ATM), or conservatively (OTM). Recommend expiration and Delta.
    """
    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "LLM analysis unavailable."

def process_file(file, chunk_size, rate_delay, pause_between_chunks):
    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
    tickers = df.iloc[:, 0].dropna().astype(str).str.upper().unique().tolist()
    results = []

    for chunk in chunk_list(tickers, chunk_size):
        for ticker in chunk:
            with st.spinner(f"Fetching {ticker}"):
                row_data = extract_finviz_data(ticker)
                results.append(row_data)
                time.sleep(rate_delay)
        time.sleep(pause_between_chunks)

    return pd.DataFrame(results)

def main():
    st.set_page_config(page_title="📈 Finviz Analyzer + Groq LLM", layout="wide")
    st.title("📈 Finviz Smart Analyzer + Groq LLM")

    uploaded_file = st.file_uploader("📁 Upload Tickers File (CSV/XLSX)", type=["xlsx", "xls", "csv"])
    api_file = st.file_uploader("🔑 Upload Groq API Key (.txt)", type=["txt"])

    api_key = api_file.read().decode("utf-8").strip() if api_file else None

    chunk_size = st.sidebar.number_input("Chunk Size", min_value=10, max_value=200, value=50)
    rate_delay = st.sidebar.number_input("Delay (sec)", min_value=0.5, max_value=5.0, value=1.0)
    pause_between_chunks = st.sidebar.number_input("Pause Between Chunks (sec)", min_value=2, max_value=30, value=5)

    if uploaded_file and api_key and st.button("🔍 Extract + Analyze"):
        df_data = process_file(uploaded_file, chunk_size, rate_delay, pause_between_chunks)
        st.dataframe(df_data)

        analysis_results = []
        for _, row in df_data.iterrows():
            fscore, tscore = score_ticker(row)
            insight = get_groq_insight(
                row["Ticker"],
                {"P/E": row.get("P/E"), "ROE": row.get("ROE")},
                {"RSI": row.get("RSI (14)"), "Volatility": row.get("Volatility")},
                api_key
            )
            analysis_results.append({
                "Ticker": row["Ticker"],
                "Fundamental Score": fscore,
                "Technical Score": tscore,
                "LLM Insight": insight
            })

        st.subheader("🤖 Groq LLM Analysis")
        st.dataframe(pd.DataFrame(analysis_results))
    elif not api_key:
        st.warning("Please upload your Groq API key.")

if __name__ == "__main__":
    main()
