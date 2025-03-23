# StreamlitUI.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

def render_ui(data, thresholds, grok_insight, ticker):
    st.title("AI-Driven Options Selling Bot with Grok Integration")
    
    if not data:
        st.warning("Please upload an Excel file with tickers and API keys to proceed.")
        return

    st.sidebar.header("Adjust Thresholds")
    thresholds.update({
        "Debt-to-Equity": st.sidebar.number_input("Max Debt-to-Equity Ratio", min_value=0.0, value=thresholds.get("Debt-to-Equity", 0.5), step=0.1),
        "Current Ratio": st.sidebar.number_input("Min Current Ratio", min_value=0.0, value=thresholds.get("Current Ratio", 1.5), step=0.1),
        "ROE": st.sidebar.number_input("Min Return on Equity (%)", value=thresholds.get("ROE", 15.0), step=1.0),
        "RSI_low": st.sidebar.number_input("RSI Lower Bound", min_value=0, max_value=100, value=thresholds.get("RSI_low", 40), step=1),
        "RSI_high": st.sidebar.number_input("RSI Upper Bound", min_value=0, max_value=100, value=thresholds.get("RSI_high", 60), step=1),
    })

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Fundamental Indicators (60%)")
        fund_df = pd.DataFrame(list(data["fundamentals"].items()), columns=["Indicator", "Value"])
        st.table(fund_df)
        st.write(f"Fundamental Score: {data['fund_score']:.1f}/6.0")
    
    with col2:
        st.subheader("Technical Indicators (40%)")
        tech_df = pd.DataFrame(list(data["technicals"].items()), columns=["Indicator", "Value"])
        st.table(tech_df)
        st.write(f"Technical Score: {data['tech_score']:.1f}/4.0")
    
    with col3:
        st.subheader("AI Recommendation")
        st.write(f"Overall Score: {data['overall_score']:.1f}/10")
        st.write(f"Recommended Put: {data['option_rec']['Expiration']}, {data['option_rec']['Delta']} Delta, Strike ${data['option_rec']['Strike']:.2f}")
        st.write(f"Strategy: {'Aggressive (ATM/ITM)' if data['overall_score'] >= 8 else 'Moderate (Near ATM)' if data['overall_score'] >= 6 else 'Conservative (OTM)'}")
        st.subheader("Grok Insight")
        st.write(grok_insight)

    if not data["history"].empty:
        fig = go.Figure(data=[go.Candlestick(x=data["history"].index, open=data["history"]['Open'], high=data["history"]['High'], low=data["history"]['Low'], close=data["history"]['Close'])])
        fig.update_layout(title=f"{ticker} Candlestick Chart", xaxis_title="Date", yaxis_title="Price")
        st.plotly_chart(fig, use_container_width=True)
