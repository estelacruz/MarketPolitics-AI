#pip install openai yfinance requests pandas
import yfinance as yf
import requests
from langchain_openai import ChatOpenAI
from datetime import datetime
import openai
import requests
from getpass import getpass

MY_STOCKS = ["NVDA", "SPY", "AMZN", "GOOGL", "AAPL"]

#STOCKS
def get_stock_data():
    summaries = []
    for ticker in MY_STOCKS:
        data = yf.Ticker(ticker).history(period="5d")
        start_price = data['Close'].iloc[0]   # use iloc for position
        end_price = data['Close'].iloc[-1]    # use iloc for position
        change_pct = (end_price - start_price) / start_price * 100
        summaries.append(
            f"{ticker}: {change_pct:.2f}% change "
            f"(from ${start_price:.2f} to ${end_price:.2f})"
        )
    return "\n".join(summaries)

print(get_stock_data())

#NEWS
NEWS_API_KEY = getpass("Enter your News API key: ")
def get_political_news():
    url = (
        "https://newsapi.org/v2/top-headlines"
        f"?country=us&category=politics&pageSize=5&apiKey={NEWS_API_KEY}"
    )
    try:
        res = requests.get(url)
        res.raise_for_status()  # Raise error if bad HTTP response
        articles = res.json().get("articles", [])
        headlines = [f"- {a['title']}" for a in articles if 'title' in a]
        return "\n".join(headlines) if headlines else "No major political headlines."
    except requests.RequestException as e:
        return f"Error fetching news: {e}"

print(get_political_news())

# ---------- OpenAI LLM ----------
OPENAI_API_KEY = getpass("Enter your OpenAI API key: ")
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=OPENAI_API_KEY
)

stocks = get_stock_data()
news = get_political_news()

prompt = f""" You are a expert financial analyst. Summarize this week’s US market performance and major political events.

Stocks:
{stocks}

Politics:
{news}

Write a concise, professional weekly report.
"""

response = llm.invoke(prompt)

# ---------- OUTPUT ----------
today = datetime.today().strftime("%Y-%m-%d")
print(f"\nWeekly US Stocks & Politics Report ({today})\n")
print(response.content)
