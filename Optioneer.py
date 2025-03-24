import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import io
import time
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from groq import Groq

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers to avoid 403 errors
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=5),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((requests.RequestException,))
)
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
            key = cells[i].get_text(strip=True)
            val = cells[i+1].get_text(strip=True)
            data[key] = val
        return data
    except Exception as e:
        return {"Ticker": ticker, "Error": str(e)}

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def score_ticker(row):
    try:
        pe = float(row.get("P/E", "").replace("%", "") or 0)
        rsi = float(row.get("RSI (14)", "").replace("%", "") or 0)
        roe = float(row.get("ROE", "").replace("%", "") or 0)
        iv = float(row.get("Volatility", "0").split()[0].replace("%", "") or 0)

        fundamentals_score = 0
        technicals_score = 0

        if pe and pe < 20: fundamentals_score += 1
        if roe and roe > 10: fundamentals_score += 1
        if rsi and 30 < rsi < 50: technicals_score += 1
        if iv and iv > 1.5: technicals_score += 1

        return fundamentals_score, technicals_score
    except:
        return 0, 0

def get_grok_insight(ticker, fundamentals, technicals, groq_api_key):
    prompt = f"""
    Analyze the stock {ticker} for selling put options based on the following data:
    Fundamentals: {fundamentals}
    Technicals: {technicals}
    Provide a brief insight on whether this is a good candidate for selling puts aggressively (ATM/ITM), moderately (near ATM), or conservatively (OTM), and suggest an expiration and Delta.
    """
    try:
        groq_client = Groq(api_key=groq_api_key)
        response = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "Groq analysis unavailable."

def process_file(file, chunk_size=100, rate_delay=1, pause_between_chunks=5):
    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
    tickers = df.iloc[:, 0].dropna().astype(str).str.upper().unique().tolist()
    st.info(f"{len(tickers)} tickers found. Starting data extraction in chunks of {chunk_size}...")

    results = []
    ticker_chunks = list(chunk_list(tickers, chunk_size))

    for chunk_idx, chunk in enumerate(ticker_chunks):
        st.info(f"📦 Processing chunk {chunk_idx + 1}/{len(ticker_chunks)}...")
        for i, ticker in enumerate(chunk):
            with st.spinner(f"Fetching {ticker} ({i + 1}/{len(chunk)})..."):
                row_data = extract_finviz_data(ticker)
                results.append(row_data)
                time.sleep(rate_delay)
        if chunk_idx < len(ticker_chunks) - 1:
            st.warning(f"Sleeping {pause_between_chunks}s between chunks to avoid rate limits...")
            time.sleep(pause_between_chunks)

    df_result = pd.DataFrame(results)
    df_result = df_result.iloc[:, :78]  # Trim columns to BZ max
    return df_result

def main():
    st.set_page_config(page_title="📈 Finviz Analyzer + Groq", layout="wide")
    st.title("📈 Finviz Smart Analyzer")

    uploaded_file = st.file_uploader("Upload CSV or Excel file with tickers", type=["xlsx", "xls", "csv"])
    groq_file = st.file_uploader("🔑 Upload Groq API Key (.txt)", type=["txt"])
    groq_api_key = groq_file.read().decode("utf-8").strip() if groq_file else None

    with st.expander("⚙️ Options"):
        chunk_size = st.number_input("Chunk Size", 10, 200, 100, 10)
        rate_delay = st.number_input("Delay per Ticker (s)", 0.5, 5.0, 1.0, 0.5)
        pause_between_chunks = st.number_input("Pause Between Chunks (s)", 2, 30, 5, 1)

    if uploaded_file and st.button("🔍 Extract + Analyze"):
        df = process_file(
            uploaded_file,
            chunk_size=int(chunk_size),
            rate_delay=float(rate_delay),
            pause_between_chunks=int(pause_between_chunks)
        )
        st.dataframe(df)

        if groq_api_key:
            analysis = []
            st.subheader("🤖 Groq LLM Analysis")
            for _, row in df.iterrows():
                fundamentals_score, technicals_score = score_ticker(row)
                insight = get_grok_insight(
                    row["Ticker"],
                    {"P/E": row.get("P/E"), "ROE": row.get("ROE")},
                    {"RSI": row.get("RSI (14)"), "Volatility": row.get("Volatility")},
                    groq_api_key
                )
                analysis.append({
                    "Ticker": row["Ticker"],
                    "Fundamental Score": fundamentals_score,
                    "Technical Score": technicals_score,
                    "Groq Insight": insight
                })
            st.dataframe(pd.DataFrame(analysis))
        else:
            st.warning("Upload a Groq API key to enable LLM-based analysis.")

if __name__ == "__main__":
    main()
