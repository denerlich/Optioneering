# LLMAdviser.py
import logging
from groq import Groq

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def get_grok_insight(ticker, fundamentals, technicals, groq_api_key):
    groq_client = Groq(api_key=groq_api_key)
    prompt = f"""
    Analyze the stock {ticker} for selling put options based on the following data:
    Fundamentals: {fundamentals}
    Technicals: {technicals}
    Provide a brief insight on whether this is a good candidate for selling puts aggressively (ATM/ITM), moderately (near ATM), or conservatively (OTM), and suggest an expiration and Delta.
    """
    try:
        response = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Grok API error: {e}")
        return "Grok analysis unavailable."
