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

# ============= CoinGecko API =============
def get_coin_data(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
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

def get_decision(rsi):
    if rsi < 30:
        return "BUY", "🟢", f"RSI منخفض ({rsi:.1f})", 0.80
    elif rsi > 70:
        return "SELL", "🔴", f"RSI مرتفع ({rsi:.1f})", 0.80
    else:
        return "HOLD", "🟡", "منطقة محايدة", 0.50

# ============= Main Analysis =============
def analyze():
    print("Fetching BTC and PAXG data...")
    
    # جلب بيانات البيتكوين
    btc_data = get_coin_data('bitcoin')
    btc_price = btc_data['market_data']['current_price']['usd']
    btc_rsi = calculate_rsi('bitcoin', 14)
    btc_decision, btc_emoji, btc_reason, btc_conf = get_decision(btc_rsi)
    
    # جلب بيانات الذهب (PAXG)
    paxg_data = get_coin_data('pax-gold')
    paxg_price = paxg_data['market_data']['current_price']['usd']
    paxg_rsi = calculate_rsi('pax-gold', 14)
    paxg_decision, paxg_emoji, paxg_reason, paxg_conf = get_decision(paxg_rsi)
    
    tg = TelegramBot(TELEGRAM_TOKEN, CHAT_ID)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')
    
    # رسالة موحدة للبيتكوين والذهب
    msg = f"""
{btc_emoji} <b>BTC:</b> ${btc_price:,.0f} | RSI: {btc_rsi:.1f} | {btc_decision}
{paxg_emoji} <b>GOLD:</b> ${paxg_price:,.0f} | RSI: {paxg_rsi:.1f} | {paxg_decision}
⏰ {timestamp}
"""
    
    success = tg.send(msg)
    print(f"✅ Sent" if success else "❌ Failed")
    print(f"BTC: ${btc_price:,.0f} | RSI: {btc_rsi:.1f} | {btc_decision}")
    print(f"PAXG: ${paxg_price:,.0f} | RSI: {paxg_rsi:.1f} | {paxg_decision}")

if __name__ == "__main__":
    analyze()
