import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from google import genai

# =====================================================================
#                 CRITICAL MOMENTUM CONFIGURATION
# =====================================================================
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSI_PERIOD = 14
# Target Tier 1 Extremes
RSI_MAX_CRITICAL = 85  
RSI_MIN_CRITICAL = 20  
# Fallback Tier 2 Extremes (Guarantees nightly delivery)
RSI_MAX_FALLBACK = 75  
RSI_MIN_FALLBACK = 25  

# =====================================================================
#             COMPREHENSIVE WATCHLIST AGGREGATOR
# =====================================================================
def get_combined_watchlist():
    """Fetches unique tickers across both S&P 500 and Nasdaq 100 lists"""
    tickers = set()
    try:
        url_sp = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        df_sp = pd.read_html(url_sp)[0]
        tickers.update(df_sp['Symbol'].str.replace('.', '-', regex=False).tolist())
    except Exception as e:
        print(f"Failed to scrape S&P 500 list: {e}")
    try:
        url_nasdaq = "https://en.wikipedia.org/wiki/Nasdaq-100"
        df_nasdaq = pd.read_html(url_nasdaq)[4]
        tickers.update(df_nasdaq['Ticker'].str.replace('.', '-', regex=False).tolist())
    except Exception as e:
        print(f"Failed to scrape Nasdaq 100 list: {e}")
    return sorted(list(tickers)) if tickers else ["SPY", "QQQ", "AAPL", "NVDA"]

# =====================================================================
#                 PURE RSI CALCULATOR (4H TIMEFRAME)
# =====================================================================
def calculate_rsi_data(ticker):
    stock = yf.Ticker(ticker)
    try:
        raw = stock.history(period="45d", interval="1h")
    except Exception:
        return None
        
    if raw.empty or len(raw) < 60:
        return None
        
    raw.index = raw.index.tz_localize(None) if raw.index.tz else raw.index
    df = raw.groupby(pd.Grouper(freq='4H')).agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
    }).dropna()
    
    if len(df) < (RSI_PERIOD + 2):
        return None

    close_prices = df['Close']
    current_price = close_prices.iloc[-1]
    
    delta = close_prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_PERIOD).mean()
    
    rs = gain / (loss + 1e-10)
    rsi_series = 100 - (100 / (1 + rs))
    current_rsi = rsi_series.iloc[-1]
    
    return {
        "ticker": ticker,
        "price": round(current_price, 2),
        "rsi": round(current_rsi, 2)
    }

# =====================================================================
#                             AI AGENT PROMPT
# =====================================================================
def run_extreme_rsi_ai(hits, is_fallback=False):
    tier_title = "TIER 2 EXTENSIONS" if is_fallback else "TIER 1 CRITICAL EXTREMES"
    
    prompt = f"""
    You are a premier macro risk advisor and counter-trend reversal trader. Analyze this group of S&P 500 and Nasdaq 100 companies currently registering at technical momentum exhaustion thresholds ({tier_title} on the 4H RSI).
    
    Alert Matrix Data: {hits}

    Instructions:
    Draft a market intelligence report for our Discord server.
    Group entries precisely into:
    1. "💥 MOMENTUM CLIMAXES (4H RSI OVERBOUGHT)"
    2. "🥶 LIQUIDATION CAPITULATIONS (4H RSI OVERSOLD)"
    
    For each asset:
    - Display the ticker symbol, closing price, and its exact RSI rating.
    - Write a razor-sharp, 1-sentence strategic trading playbook detailing execution boundaries or signs of exhaustion to watch for.

    Deliver the layout cleanly using markdown bullet points. Avoid polite introductory pleasantries.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    return response.text

# =====================================================================
#                             RUN EXECUTION
# =====================================================================
try:
    print("Gathering combined market symbols...")
    watchlist = get_combined_watchlist()
    
    all_results = []
    print(f"Scanning {len(watchlist)} tickers for 4H RSI data...")
    
    for ticker in watchlist:
        res = calculate_rsi_data(ticker)
        if res:
            all_results.append(res)
            
    # Step 1: Filter for Tier 1 Critical Extremes (>= 85 or <= 20)
    matched_setups = [r for r in all_results if r["rsi"] >= RSI_MAX_CRITICAL or r["rsi"] <= RSI_MIN_CRITICAL]
    using_fallback = False
    
    # Step 2: If Tier 1 is empty, back down to Tier 2 (>= 75 or <= 25) to guarantee results
    if not matched_setups:
        print("No Tier 1 extremes found. Relaxing filter to Tier 2 limits to guarantee nightly delivery...")
        matched_setups = [r for r in all_results if r["rsi"] >= RSI_MAX_FALLBACK or r["rsi"] <= RSI_MIN_FALLBACK]
        using_fallback = True
            
    if matched_setups:
        print(f"Captured {len(matched_setups)} matches. Formatting AI report...")
        # Sort by furthest deviation from a neutral 50 RSI
        matched_setups = sorted(matched_setups, key=lambda x: abs(x["rsi"] - 50), reverse=True)
        
        evening_report = run_extreme_rsi_ai(matched_setups[:25], is_fallback=using_fallback)
        header_tag = "⚠️ TIER 2 MOMENTUM ALERT ⚠️" if using_fallback else "🚨 TIER 1 CLIMAX ENGINE ALERT 🚨"
        
        payload = {
            "username": "FEELS Climax Exhaustion Monitor",
            "content": f"## {header_tag}\n{evening_report}"
        }
        requests.post(DISCORD_WEBHOOK, json=payload)
        print("Success! Watchlist shipped straight to Discord.")
    else:
        print("Scan finalized. No stocks met fallback criteria.")
except Exception as e:
    print(f"Execution Error: {e}")
