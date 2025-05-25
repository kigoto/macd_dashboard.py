import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import smtplib
from email.mime.text import MIMEText
import time

st.set_page_config(layout="wide")

st.title("📊 Real-Time MACD + VWAP Dashboard with Option Chain Overlay and Alerts")

ticker_input = st.text_input("Enter stock symbol (e.g., NVDA)", value="NVDA").upper()
interval = st.selectbox("Select Interval", ["1m", "5m", "15m", "1h"], index=0)
duration = "1d" if interval == "1m" else "5d"

# Email Alert
st.sidebar.header("🔔 Email Alerts (Optional)")
email_alert = st.sidebar.checkbox("Enable Email Alerts")
recipient_email = st.sidebar.text_input("Recipient Email")
sender_email = st.sidebar.text_input("Sender Email (Gmail)")
sender_password = st.sidebar.text_input("App Password", type="password")

# Auto Refresh
st.sidebar.header("⏱️ Auto-Refresh")
auto_refresh = st.sidebar.checkbox("Enable Auto-Refresh")
refresh_rate = st.sidebar.slider("Refresh every (seconds)", min_value=30, max_value=300, value=60, step=30)

def get_macd(data):
    exp1 = data['Close'].ewm(span=12, adjust=False).mean()
    exp2 = data['Close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def get_vwap(data):
    cum_vol_price = (data['Volume'] * (data['High'] + data['Low'] + data['Close']) / 3).cumsum()
    cum_vol = data['Volume'].cumsum()
    vwap = cum_vol_price / cum_vol
    return vwap

def check_cross(macd, signal):
    macd = macd.dropna()
    signal = signal.dropna()
    if len(macd) < 2 or len(signal) < 2:
        return "No signal"
    if macd.iloc[-2] < signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1]:
        return "📈 BUY SIGNAL"
    elif macd.iloc[-2] > signal.iloc[-2] and macd.iloc[-1] < signal.iloc[-1]:
        return "📉 SELL SIGNAL"
    else:
        return "No crossover"

def send_email_alert(subject, body, to_email, from_email, password):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())
    except Exception as e:
        st.sidebar.error(f"Email failed: {e}")

@st.cache_data(ttl=60)
def load_data(ticker):
    return yf.download(ticker, period=duration, interval=interval, progress=False)

@st.cache_data(ttl=600)
def load_option_chain(ticker):
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        chain = stock.option_chain(expirations[0])
        return chain.calls[['strike', 'lastPrice', 'volume', 'openInterest']]
    except Exception:
        return pd.DataFrame()

def render_dashboard():
    data = load_data(ticker_input)
    macd, signal = get_macd(data)
    vwap = get_vwap(data)
    alert = check_cross(macd, signal)
    last_price = data['Close'].iloc[-1]

    st.subheader(f"{ticker_input} - Price: ${last_price:.2f} | {alert}")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(data.index[-100:], macd[-100:], label="MACD", color="blue")
    ax.plot(data.index[-100:], signal[-100:], label="Signal", color="red")
    ax.plot(data.index[-100:], vwap[-100:], label="VWAP", color="orange", linestyle="--")
    ax.bar(data.index[-100:], (macd - signal)[-100:], color="gray", label="Histogram")
    ax.legend()
    ax.grid()
    st.pyplot(fig)

    st.markdown("### 🧾 Option Chain (Nearest Expiration)")
    option_df = load_option_chain(ticker_input)
    if not option_df.empty:
        st.dataframe(option_df.sort_values("volume", ascending=False).head(10))
    else:
        st.warning("Option chain data unavailable for this ticker or data source blocked.")

    if email_alert and ("BUY" in alert or "SELL" in alert):
        subject = f"{ticker_input} {alert}"
        body = f"{ticker_input} triggered a {alert} at ${last_price:.2f}"
        send_email_alert(subject, body, recipient_email, sender_email, sender_password)

if auto_refresh:
    while True:
        render_dashboard()
        time.sleep(refresh_rate)
        st.rerun()
else:
    render_dashboard()
