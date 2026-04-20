import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

INDICES = ["^GSPC", "^IXIC", "^DJI"]

def get_nasdaq_stocks():
    try:
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=500&exchange=NASDAQ&download=true"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        rows = data["data"]["rows"]
        stocks = []
        for row in rows:
            try:
                price = float(row["lastsale"].replace("$",""))
                if price <= 15:
                    stocks.append(row["symbol"])
            except:
                continue
        return stocks[:100]
    except Exception as e:
        print(f"שגיאה בשאיבת מניות: {e}")
        return ["PLUG","SENS","CLOV","MVIS","AAL","F","ABEV","NOK","SIRI","BAC"]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})

def send_email(subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"email error: {e}")

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def analyze_stock(ticker):
    try:
        data = yf.download(ticker, period="3mo", interval="1h", progress=False)
        if data.empty or len(data) < 30:
            return None
        close = data["Close"].squeeze()
        volume = data["Volume"].squeeze()
        price = float(close.iloc[-1])
        if price > 15:
            return None
        rsi = float(calc_rsi(close).iloc[-1])
        ema20 = float(close.ewm(span=20).mean().iloc[-1])
        ema50 = float(close.ewm(span=50).mean().iloc[-1])
        macd_line = close.ewm(span=12).mean() - close.ewm(span=26).mean()
        signal_line = macd_line.ewm(span=9).mean()
        macd = float(macd_line.iloc[-1])
        signal = float(signal_line.iloc[-1])
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = float((bb_mid + 2*bb_std).iloc[-1])
        bb_lower = float((bb_mid - 2*bb_std).iloc[-1])
        vol_avg = float(volume.rolling(20).mean().iloc[-1])
        vol_current = float(volume.iloc[-1])
        signals = []
        if rsi < 30: signals.append("🟢 RSI נמוך מאוד - LONG חזק")
        elif rsi < 35: signals.append("🟡 RSI נמוך - LONG")
        if rsi > 70: signals.append("🔴 RSI גבוה מאוד - SHORT חזק")
        elif rsi > 65: signals.append("🟠 RSI גבוה - SHORT")
        if macd > signal: signals.append("📈 MACD חיובי")
        if price < bb_lower: signals.append("💚 מתחת לבולינגר - קנייה")
        if price > bb_upper: signals.append("❤️ מעל בולינגר - מכירה")
        if ema20 > ema50: signals.append("⬆️ EMA חיובי")
        if vol_current > vol_avg * 2: signals.append("🔥 נפח גבוה מאוד!")
        elif vol_current > vol_avg * 1.5: signals.append("📊 נפח גבוה")
        strong = any("חזק" in s or "🔥" in s or "💚" in s or "❤️" in s for s in signals)
        if len(signals) >= 2 or strong:
            return {"ticker": ticker, "price": price, "rsi": round(rsi,1), "signals": signals}
    except Exception as e:
        print(f"error {ticker}: {e}")
    return None

def analyze_index(ticker):
    try:
        data = yf.download(ticker, period="1mo", interval="1h", progress=False)
        if data.empty:
            return None
        close = data["Close"].squeeze()
        rsi = float(calc_rsi(close).iloc[-1])
        macd_line = close.ewm(span=12).mean() - close.ewm(span=26).mean()
        signal_line = macd_line.ewm(span=9).mean()
        macd = float(macd_line.iloc[-1])
        signal = float(signal_line.iloc[-1])
        if rsi < 40 and macd > signal:
            direction = "LONG 📈"
        elif rsi > 60 and macd < signal:
            direction = "SHORT 📉"
        else:
            direction = "NEUTRAL ⏸"
        return {"ticker": ticker, "rsi": round(rsi,1), "direction": direction}
    except:
        return None

def get_news(ticker):
    try:
        url = f"https://newsapi.org/v2/everything?q={ticker}+stock+nasdaq&language=en&sortBy=publishedAt&pageSize=2&apiKey={NEWS_API_KEY}"
        r = requests.get(url, timeout=10)
        articles = r.json().get("articles", [])
        return [a["title"] for a in articles[:1]]
    except:
        return []

def main():
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"סריקה: {now}")
    stocks = get_nasdaq_stocks()
    print(f"נמצאו {len(stocks)} מניות לסריקה")
    alerts = []
    email_body = f"Stock Bot {now}\n{'='*40}\n\n"
    for stock in stocks:
        result = analyze_stock(stock)
        if result:
            news = get_news(result["ticker"])
            msg = f"🔔 {result['ticker']} | ${result['price']:.2f} | RSI:{result['rsi']}\n"
            msg += "\n".join(result["signals"])
            if news:
                msg += f"\n📰 {news[0][:80]}"
            alerts.append(msg)
            email_body += msg + "\n\n"
    names = {"^GSPC":"S&P500","^IXIC":"NASDAQ","^DJI":"DOW"}
    email_body += "\n📈 מדדים:\n"
    for idx in INDICES:
        result = analyze_index(idx)
        if result:
            msg = f"📊 {names[idx]} | RSI:{result['rsi']} | {result['direction']}"
            alerts.append(msg)
            email_body += msg + "\n"
    if alerts:
        chunks = [alerts[i:i+10] for i in range(0, len(alerts), 10)]
        for chunk in chunks:
            send_telegram(f"🤖 Stock Bot {now}\n\n" + "\n\n".join(chunk))
        send_email(f"Stock Bot {now}", email_body)
        print(f"נשלחו {len(alerts)} התרעות!")
    else:
        print("אין התרעות")

if __name__ == "__main__":
    main()
