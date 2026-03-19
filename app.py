"""
MarketPolitics AI — Backend API Server

Flask API that serves stock data, political news, and AI-generated reports
as JSON endpoints consumed by the frontend dashboard (index.html).

Setup:
  pip install flask flask-cors openai yfinance requests pandas langchain-openai

Run:
  python app.py
  Then open index.html in your browser (or visit http://localhost:8080)

Environment Variables (set before running, or you'll be prompted):
  NEWS_API_KEY   — your NewsAPI.org key
  OPENAI_API_KEY — your OpenAI key
"""

import os
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, send_file
from flask_cors import CORS

import yfinance as yf
import requests
from langchain_openai import ChatOpenAI


# CONFIG

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
CORS(app)

MY_STOCKS = ["NVDA", "SPY", "AMZN", "GOOGL", "AAPL"]

# API keys — prompted at startup
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not NEWS_API_KEY:
    from getpass import getpass
    NEWS_API_KEY = getpass("Enter your News API key: ")

if not OPENAI_API_KEY:
    from getpass import getpass
    OPENAI_API_KEY = getpass("Enter your OpenAI API key: ")


# STOCK DATA
def get_stock_data():
    """Fetch 5-day stock data and return as list of dicts."""
    results = []
    for ticker in MY_STOCKS:
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if data.empty:
                continue

            info = yf.Ticker(ticker).info
            start_price = round(float(data["Close"].iloc[0]), 2)
            end_price = round(float(data["Close"].iloc[-1]), 2)
            change_pct = round((end_price - start_price) /
                               start_price * 100, 2)

            # Build sparkline from daily closes
            spark = [round(float(p), 2) for p in data["Close"].tolist()]

            # Simple sentiment heuristic based on change
            if change_pct > 2:
                sentiment = "Bullish"
            elif change_pct < -2:
                sentiment = "Bearish"
            elif change_pct > 0:
                sentiment = "Bullish"
            elif change_pct < 0:
                sentiment = "Bearish"
            else:
                sentiment = "Neutral"

            results.append({
                "ticker": ticker,
                "name": info.get("shortName", ticker),
                "sector": info.get("sector", "N/A"),
                "open": start_price,
                "close": end_price,
                "current": end_price,
                "change": change_pct,
                "volume": _format_volume(info.get("averageVolume", 0)),
                "sentiment": sentiment,
                "color": _ticker_color(ticker),
                "spark": spark,
            })
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            continue

    return results


def _format_volume(vol):
    """Format volume as human-readable string."""
    if vol >= 1_000_000_000:
        return f"{vol / 1_000_000_000:.1f}B"
    elif vol >= 1_000_000:
        return f"{vol / 1_000_000:.0f}M"
    elif vol >= 1_000:
        return f"{vol / 1_000:.0f}K"
    return str(vol)


def _ticker_color(ticker):
    """Brand colors for known tickers."""
    colors = {
        "NVDA": "#76b900",
        "SPY": "#3b82f6",
        "AMZN": "#ff9900",
        "GOOGL": "#4285f4",
        "AAPL": "#a2aaad",
    }
    return colors.get(ticker, "#6366f1")


# NEWS DATA
def get_political_news():
    """Fetch political headlines and return as list of dicts."""
    url = (
        "https://newsapi.org/v2/top-headlines"
        f"?country=us&category=politics&pageSize=6&apiKey={NEWS_API_KEY}"
    )
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        articles = res.json().get("articles", [])

        results = []
        for i, a in enumerate(articles):
            if "title" not in a or not a["title"]:
                continue

            # Simple sentiment analysis based on keywords
            title_lower = a["title"].lower()
            if any(w in title_lower for w in ["surge", "gain", "rise", "beat", "record", "boost"]):
                sentiment = "bullish"
            elif any(w in title_lower for w in ["fall", "drop", "crisis", "tension", "war", "strike", "threat"]):
                sentiment = "bearish"
            else:
                sentiment = "neutral"

            # Try to match affected tickers
            tickers = []
            for t in MY_STOCKS:
                if t.lower() in title_lower or _company_in_title(t, title_lower):
                    tickers.append(t)
            if not tickers:
                tickers = ["SPY"]  # Default: broad market impact

            published = a.get("publishedAt", "")
            time_str = ""
            if published:
                try:
                    dt = datetime.fromisoformat(
                        published.replace("Z", "+00:00"))
                    time_str = dt.strftime("%H:%M")
                except:
                    time_str = "—"

            results.append({
                "id": i + 1,
                "time": time_str,
                "headline": a["title"],
                "source": a.get("source", {}).get("name", "Unknown"),
                "sentiment": sentiment,
                "tickers": tickers,
                "cat": _categorize_headline(a["title"]),
            })

        return results

    except requests.RequestException as e:
        print(f"News API error: {e}")
        return []


def _company_in_title(ticker, title):
    """Check if a company name appears in headline."""
    names = {
        "NVDA": ["nvidia", "nvda"],
        "AAPL": ["apple", "iphone", "aapl"],
        "GOOGL": ["google", "alphabet", "googl"],
        "AMZN": ["amazon", "amzn", "aws"],
        "SPY": ["s&p", "market", "stocks", "wall street"],
    }
    return any(n in title for n in names.get(ticker, []))


def _categorize_headline(title):
    """Simple category assignment."""
    t = title.lower()
    if any(w in t for w in ["earning", "revenue", "profit", "quarter"]):
        return "Earnings"
    elif any(w in t for w in ["iran", "china", "russia", "war", "military", "geopolit"]):
        return "Geopolitics"
    elif any(w in t for w in ["fed", "rate", "inflation", "gdp", "jobs"]):
        return "Economy"
    elif any(w in t for w in ["congress", "senate", "house", "bill", "vote", "election"]):
        return "Policy"
    elif any(w in t for w in ["tech", "ai", "chip", "semiconductor"]):
        return "Technology"
    return "General"


# AI REPORT
def generate_ai_report(stocks_data, news_data):
    """Generate AI analysis using GPT-4o-mini."""
    try:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=OPENAI_API_KEY,
        )

        # Format data for the prompt
        stock_summary = "\n".join(
            f"{s['ticker']}: {s['change']:+.2f}% (${s['open']:.2f} → ${s['close']:.2f})"
            for s in stocks_data
        )
        news_summary = "\n".join(
            f"- [{h['sentiment'].upper()}] {h['headline']} ({h['source']})"
            for h in news_data
        )

        prompt = f"""You are an expert financial analyst at a major investment bank.
Analyze this week's US market performance and political events.

STOCKS:
{stock_summary}

POLITICAL/MARKET HEADLINES:
{news_summary}

Write a professional weekly report with exactly these 4 sections.
For each section, write 2-3 sentences. Be specific with numbers.

Respond in this exact JSON format (no markdown, no backticks):
{{
  "sections": [
    {{"title": "MARKET PERFORMANCE", "text": "..."}},
    {{"title": "POLITICAL DRIVERS", "text": "..."}},
    {{"title": "CORRELATION ANALYSIS", "text": "..."}},
    {{"title": "OUTLOOK", "text": "..."}}
  ],
  "summary_sentiment": "bullish" or "bearish" or "neutral"
}}"""

        response = llm.invoke(prompt)
        content = response.content.strip()

        # Try to parse as JSON
        try:
            report = json.loads(content)
        except json.JSONDecodeError:
            # If model wraps in backticks, strip them
            clean = content.replace("```json", "").replace("```", "").strip()
            report = json.loads(clean)

        return report

    except Exception as e:
        print(f"AI report error: {e}")
        return {
            "sections": [
                {"title": "MARKET PERFORMANCE",
                    "text": f"Error generating report: {str(e)}"},
            ],
            "summary_sentiment": "neutral",
        }


# API ROUTES
@app.route("/")
def serve_frontend():
    """Serve the index.html dashboard."""
    return send_file(BASE_DIR / "index.html")


@app.route("/api/stocks")
def api_stocks():
    """GET /api/stocks — Returns current stock data as JSON."""
    data = get_stock_data()
    return jsonify({
        "stocks": data,
        "timestamp": datetime.now().isoformat(),
        "tickers": MY_STOCKS,
    })


@app.route("/api/news")
def api_news():
    """GET /api/news — Returns political headlines with sentiment."""
    data = get_political_news()
    return jsonify({
        "headlines": data,
        "timestamp": datetime.now().isoformat(),
        "count": len(data),
    })


@app.route("/api/report")
def api_report():
    """GET /api/report — Returns AI-generated weekly analysis."""
    stocks = get_stock_data()
    news = get_political_news()
    report = generate_ai_report(stocks, news)
    return jsonify({
        "report": report,
        "timestamp": datetime.now().isoformat(),
        "model": "gpt-4o-mini",
        "date": datetime.today().strftime("Week of %b %d, %Y"),
    })


@app.route("/api/all")
def api_all():
    """GET /api/all — Returns everything in one call (stocks + news + report)."""
    stocks = get_stock_data()
    news = get_political_news()
    report = generate_ai_report(stocks, news)
    return jsonify({
        "stocks": stocks,
        "headlines": news,
        "report": report,
        "timestamp": datetime.now().isoformat(),
        "date": datetime.today().strftime("Week of %b %d, %Y"),
    })


# ENTRY POINT
if __name__ == "__main__":
    PORT = 8080
    print("\n" + "=" * 55)
    print("  MarketPolitics Nexus — API Server")
    print("=" * 55)
    print(f"  Dashboard:  http://localhost:{PORT}")
    print(f"  API:        http://localhost:{PORT}/api/stocks")
    print(f"              http://localhost:{PORT}/api/news")
    print(f"              http://localhost:{PORT}/api/report")
    print(f"              http://localhost:{PORT}/api/all")
    print("=" * 55 + "\n")
    app.run(debug=True, host="127.0.0.1", port=PORT)
