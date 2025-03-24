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

# Headers to avoid 403 errors
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

@retry(wait=wait_exponential(multiplier=1, min=2, max=5), stop=stop_after_attempt(3),
       retry=retry_if_exception_type((requests.RequestException,)))
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
        logger.debug(f"Failed to extract data for {ticker}: {e}")
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
    Analyze the stock {ticker} for selling put options based on the following data:
    Fundamentals: {fundamentals}
    Technicals: {technicals}
    Provide a brief insight on whether this is a good candidate for selling puts aggressively (ATM/ITM), moderately (near ATM), or conservatively (OTM), and suggest an expiration and Delta.
    """
    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.5
        )
        logger.debug(f"Groq response: {response}")
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "LLM analysis unavailable."

def process_file(file, chunk_size=100, rate_delay=1, pause_between_chunks=5):
    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
    tickers = df.iloc[:, 0].dropna().astype(str).str.upper().unique().tolist()
    st.info(f"{len(tickers)} tickers found. Starting data extraction in chunks of {chunk_size}...")

    results = []
    for chunk_idx, chunk in enumerate(chunk_list(tickers, chunk_size)):
        st.info(f"📦 Processing chunk {chunk_idx + 1} of {(len(tickers)-1)//chunk_size + 1}")
        for i, ticker in enumerate(chunk):
            with st.spinner(f"Fetching {ticker}... ({i + 1}/{len(chunk)})"):
                row_data = extract_finviz_data(ticker)
                results.append(row_data)
                time.sleep(rate_delay)
        if chunk_idx < len(tickers) // chunk_size:
            time.sleep(pause_between_chunks)

    df_result = pd.DataFrame(results)
    return df_result.iloc[:, :78]  # Limit to BZ column

def main():
    st.set_page_config(page_title="📈 Finviz Analyzer + LLM", layout="wide")
    st.title("📈 Finviz Smart Analyzer")

    uploaded_file = st.file_uploader("Upload CSV or Excel file with tickers", type=["xlsx", "xls", "csv"])
    api_file = st.file_uploader("🔑 Upload OpenAI API Key (.txt)", type=["txt"])
    api_key = api_file.read().decode("utf-8").strip() if api_file else None

    with st.expander("⚙️ Options"):
        chunk_size = st.number_input("Chunk Size", 10, 200, 100, 10)
        rate_delay = st.number_input("Delay between requests (sec)", 0.5, 5.0, 1.0, 0.5)
        pause_between_chunks = st.number_input("Pause between chunks (sec)", 2, 30, 5, 1)

    if uploaded_file and st.button("🔍 Extract + Analyze"):
        df = process_file(uploaded_file, chunk_size, rate_delay, pause_between_chunks)
        st.dataframe(df)

        if api_key:
            st.subheader("🤖 LLM Analysis")
            analysis = []
            for _, row in df.iterrows():
                fscore, tscore = score_ticker(row)
                insight = get_groq_insight(
                    row["Ticker"],
                    {"P/E": row.get("P/E"), "ROE": row.get("ROE")},
                    {"RSI": row.get("RSI (14)"), "Volatility": row.get("Volatility")},
                    api_key
                )

                )
                analysis.append({
                    "Ticker": row["Ticker"],
                    "Fundamental Score": fscore,
                    "Technical Score": tscore,
                    "LLM Insight": insight
                })
            st.dataframe(pd.DataFrame(analysis))
        else:
            st.warning("Please upload your OpenAI API key to run analysis.")

if __name__ == "__main__":
    main()
