import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import smtplib
from email.mime.text import MIMEText
import time

st.set_page_config(layout="wide")

st.title("📊 MACD + VWAP + Option Chain Dashboard with Strike Filter, Expiry Selector, and OI Overlay")

ticker_input = st.text_input("Enter stock symbol (e.g., NVDA)", value="NVDA").upper()
interval = st.selectbox("Select Interval", ["1m", "5m", "15m", "1h"], index=0)
duration = "1d" if interval == "1m" else "5d"

st.sidebar.header("🔔 Email Alerts (Optional)")
email_alert = st.sidebar.checkbox("Enable Email Alerts")
recipient_email = st.sidebar.text_input("Recipient Email")
sender_email = st.sidebar.text_input("Sender Email (Gmail)")
sender_password = st.sidebar.text_input("App Password", type="password")

st.sidebar.header("⏱️ Auto-Refresh")
auto_refresh = st.sidebar.checkbox("Enable Auto-Refresh")
refresh_rate = st.sidebar.slider("Refresh every (seconds)", min_value=30, max_value=300, value=60, step=30)

@st.cache_data(ttl=60)
def load_data(ticker):
    return yf.download(ticker, period=duration, interval=interval, progress=False)

@st.cache_data(ttl=600)
def load_option_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        return stock.options, stock
    except Exception:
        return [], None

def get_macd(data):
    exp1 = data['Close'].ewm(span=12, adjust=False).mean()
    exp2 = data['Close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def get_vwap(data):
    cum_vol_price = (data['Volume'] * (data['High'] + data['Low'] + data['Close']) / 3).cumsum()
    cum_vol = data['Volume'].cumsum()
    return cum_vol_price / cum_vol

def check_cross(macd, signal):
    macd = macd.dropna()
    signal = signal.dropna()
    if len(macd) < 2 or len(signal) < 2:
        return "No signal"
    try:
        macd_prev = float(macd.iloc[-2])
        macd_now = float(macd.iloc[-1])
        sig_prev = float(signal.iloc[-2])
        sig_now = float(signal.iloc[-1])

        if macd_prev < sig_prev and macd_now > sig_now:
            return "📈 BUY SIGNAL"
        elif macd_prev > sig_prev and macd_now < sig_now:
            return "📉 SELL SIGNAL"
        else:
            return "No crossover"
    except Exception:
        return "No signal"

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

def render_dashboard():
    data = load_data(ticker_input)
    if data.empty:
        st.error("No data loaded for this ticker.")
        return

    macd, signal = get_macd(data)
    vwap = get_vwap(data)
    alert = check_cross(macd, signal)
    last_price = data['Close'].iloc[-1]
    price_display = f"${last_price:.2f}" if last_price is not None and not pd.isna(last_price) else "N/A"

    st.subheader(f"{ticker_input} – Price: {price_display} | {alert}")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(data.index[-100:], macd[-100:], label="MACD", color="blue")
    ax.plot(data.index[-100:], signal[-100:], label="Signal", color="red")
    ax.plot(data.index[-100:], vwap[-100:], label="VWAP", color="orange", linestyle="--")
    ax.bar(data.index[-100:], (macd - signal)[-100:], color="gray", label="Histogram")
    ax.legend()
    ax.grid()
    st.pyplot(fig)

    expirations, stock = load_option_data(ticker_input)
    if not expirations or stock is None:
        st.warning("Option data unavailable.")
        return

    expiry = st.selectbox("Select Expiration", expirations)
    try:
        chain = stock.option_chain(expiry)
        calls = chain.calls
        puts = chain.puts
    except Exception:
        st.error("Could not load option chain.")
        return

    st.markdown("### 📈 Call Options Near Strike")
    if not calls.empty:
        st.markdown("Filtered within ±5% of current price.")
        near_calls = calls[calls['strike'].between(last_price * 0.95, last_price * 1.05)]
        st.dataframe(near_calls.sort_values("openInterest", ascending=False).head(10))
    else:
        st.warning("No call options found.")

    st.markdown("### 📉 Put Options Near Strike")
    if not puts.empty:
        st.markdown("Filtered within ±5% of current price.")
        near_puts = puts[puts['strike'].between(last_price * 0.95, last_price * 1.05)]
        st.dataframe(near_puts.sort_values("openInterest", ascending=False).head(10))
    else:
        st.warning("No put options found.")

    if email_alert and ("BUY" in alert or "SELL" in alert):
        subject = f"{ticker_input} {alert}"
        body = f"{ticker_input} triggered a {alert} at {price_display}"
        send_email_alert(subject, body, recipient_email, sender_email, sender_password)

if auto_refresh:
    while True:
        render_dashboard()
        time.sleep(refresh_rate)
        st.rerun()
else:
    render_dashboard()
