import requests
import os
from datetime import datetime

# ============= Configuration =============
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = "362387912"

# ============= Telegram Bot =============
class TelegramBot:
    def __init__(self, token, chat_id):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
    
    def send(self, text, parse_mode="HTML"):
        try:
            requests.post(self.url, json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}, timeout=10)
            return True
        except Exception as e:
            print(f"Telegram error: {e}")
            return False

# ============= CoinGecko API =============
def get_btc_data():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin"
    params = {"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()

def calculate_rsi(coin_id, days=14):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    prices = [p[1] for p in data['prices']]
    
    if len(prices) < 15:
        return 50.0
    
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    avg_gain = sum(gains[-14:]) / 14
    avg_loss = sum(losses[-14:]) / 14
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ============= Smart Notification Logic =============
def analyze():
    print("Fetching BTC data from CoinGecko...")
    data = get_btc_data()
    
    price = data['market_data']['current_price']['usd']
    change_24h = data['market_data']['price_change_percentage_24h']
    high_24h = data['market_data']['high_24h']['usd']
    low_24h = data['market_data']['low_24h']['usd']
    market_cap = data['market_data']['market_cap']['usd']
    
    rsi = calculate_rsi('bitcoin', 14)
    
    # Determine decision
    if rsi < 30:
        decision, emoji, reason, confidence = "BUY", "🟢", f"RSI منخفض ({rsi:.1f}) - تشبع بيعي", 0.80
    elif rsi > 70:
        decision, emoji, reason, confidence = "SELL", "", f"RSI مرتفع ({rsi:.1f}) - تشبع شرائي", 0.80
    else:
        decision, emoji, reason, confidence = "HOLD", "", "منطقة محايدة", 0.50
    
    tg = TelegramBot(TELEGRAM_TOKEN, CHAT_ID)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')
    
    # Smart notification: Short for HOLD, detailed for BUY/SELL
    if decision == "HOLD":
        # رسالة قصيرة لـ HOLD
        msg = f"{emoji} <b>BTC:</b> ${price:,.0f} | RSI: {rsi:.1f} | HOLD\n⏰ {timestamp}"
    else:
        # رسالة مفصلة لـ BUY/SELL
        msg = f"""
{emoji} <b>BTC/USDT - {decision} SIGNAL</b>
━━━━━━━━━━━━━━━━━━━━
💰 <b>Price:</b> ${price:,.2f}
📈 <b>24h Change:</b> {change_24h:+.2f}%
🔺 <b>24h High:</b> ${high_24h:,.2f}
🔻 <b>24h Low:</b> ${low_24h:,.2f}
💎 <b>Market Cap:</b> ${market_cap/1e9:.1f}B
━━━━━━━━━━━━━━━━━━━━
📊 <b>RSI (14-day):</b> {rsi:.2f}
{emoji} <b>Decision:</b> {decision}
 <b>Reason:</b> {reason}
🎯 <b>Confidence:</b> {confidence*100:.0f}%
 {timestamp}
"""
    
    success = tg.send(msg)
    print(f"✅ Sent {decision} signal" if success else "❌ Failed")
    print(f"Price: ${price:,.2f} | RSI: {rsi:.2f}")

if __name__ == "__main__":
    analyze()
