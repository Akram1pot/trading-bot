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
    
    def send(self, text):
        try:
            requests.post(self.url, json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
            return True
        except Exception as e:
            print(f"Telegram error: {e}")
            return False

# ============= CoinGecko API (Free, No Geo-Restrictions) =============
def get_btc_data():
    """جلب بيانات البيتكوين من CoinGecko"""
    url = "https://api.coingecko.com/api/v3/coins/bitcoin"
    params = {
        "localization": "false",
        "tickers": "false",
        "community_data": "false",
        "developer_data": "false"
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()

def calculate_rsi_from_history(coin_id, days=14):
    """حساب RSI تقريبي من تاريخ الأسعار"""
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

# ============= Trading Logic =============
def analyze():
    print("Fetching BTC data from CoinGecko...")
    data = get_btc_data()
    
    price = data['market_data']['current_price']['usd']
    change_24h = data['market_data']['price_change_percentage_24h']
    high_24h = data['market_data']['high_24h']['usd']
    low_24h = data['market_data']['low_24h']['usd']
    market_cap = data['market_data']['market_cap']['usd']
    
    print(f"Price: ${price:,.2f}")
    print(f"24h Change: {change_24h:.2f}%")
    
    # حساب RSI تقريبي
    rsi = calculate_rsi_from_history('bitcoin', 14)
    print(f"RSI (14-day approx): {rsi:.2f}")
    
    # قرار التداول
    if rsi < 30:
        decision = "BUY"
        emoji = ""
        reason = f"RSI منخفض ({rsi:.1f}) - تشبع بيعي"
        confidence = 0.80
    elif rsi > 70:
        decision = "SELL"
        emoji = ""
        reason = f"RSI مرتفع ({rsi:.1f}) - تشبع شرائي"
        confidence = 0.80
    else:
        decision = "HOLD"
        emoji = "🟡"
        reason = "منطقة محايدة - انتظر إشارة أوضح"
        confidence = 0.50
    
    # رسالة Telegram
    msg = f"""
{emoji} <b>BTC/USDT Analysis</b>
━━━━━━━━━━━━━━━━━━━━
💰 <b>Price:</b> ${price:,.2f}
📈 <b>24h Change:</b> {change_24h:+.2f}%
🔺 <b>24h High:</b> ${high_24h:,.2f}
🔻 <b>24h Low:</b> ${low_24h:,.2f}
💎 <b>Market Cap:</b> ${market_cap/1e9:.1f}B

━━━━━━━━━━━━━━━━━━━━
 <b>RSI (14-day):</b> {rsi:.2f}
{emoji} <b>Decision:</b> {decision}
📝 <b>Reason:</b> {reason}
🎯 <b>Confidence:</b> {confidence*100:.0f}%

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
"""
    
    tg = TelegramBot(TELEGRAM_TOKEN, CHAT_ID)
    success = tg.send(msg)
    
    if success:
        print("✅ Telegram notification sent!")
    else:
        print("❌ Failed to send Telegram notification")
    
    print(f"\nFinal Decision: {decision}")

if __name__ == "__main__":
    analyze()
