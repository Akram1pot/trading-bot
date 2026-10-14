import requests
import os
import csv
import json
from datetime import datetime

# ============= Configuration =============
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = "362387912"
LOG_FILE = "trading_log.csv"
STATE_FILE = "last_state.json"

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
        return "SELL", "", f"RSI مرتفع ({rsi:.1f})", 0.80
    else:
        return "HOLD", "🟡", "منطقة محايدة", 0.50

# ============= State Management =============
def load_state():
    """تحميل آخر حالة محفوظة"""
    if os.path.isfile(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_state(state):
    """حفظ الحالة الحالية"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def should_send_alert(coin, price, rsi, decision, last_state):
    """تحديد ما إذا كان يجب إرسال تنبيه"""
    
    # إذا لم توجد حالة سابقة، أرسل دائماً (أول تشغيل)
    if coin not in last_state:
        return True, "أول تشغيل"
    
    last = last_state[coin]
    last_price = last['price']
    last_decision = last['decision']
    last_rsi = last['rsi']
    
    # الشرط 1: تغير القرار (HOLD → BUY/SELL أو العكس)
    if decision != last_decision:
        return True, f"تغير القرار من {last_decision} إلى {decision}"
    
    # الشرط 2: RSI في منطقة حرجة
    if rsi < 30 or rsi > 70:
        return True, f"RSI حرج ({rsi:.1f})"
    
    # الشرط 3: تغير السعر أكثر من 3%
    price_change_pct = abs(price - last_price) / last_price * 100
    if price_change_pct > 3.0:
        return True, f"تغير السعر {price_change_pct:.2f}%"
    
    # لا تنبيه
    return False, None

# ============= Logging =============
def log_decision(coin, price, rsi, decision, reason, confidence):
    file_exists = os.path.isfile(LOG_FILE)
    
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['timestamp', 'coin', 'price', 'rsi', 'decision', 'reason', 'confidence'])
        
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M UTC'),
            coin,
            f"${price:,.2f}",
            f"{rsi:.2f}",
            decision,
            reason,
            f"{confidence*100:.0f}%"
        ])
    
    print(f"📝 Logged: {coin} {decision} at ${price:,.0f}")

# ============= Main Analysis =============
def analyze():
    print("Fetching BTC and PAXG data...")
    
    # تحميل آخر حالة
    last_state = load_state()
    
    # البيتكوين
    btc_data = get_coin_data('bitcoin')
    btc_price = btc_data['market_data']['current_price']['usd']
    btc_rsi = calculate_rsi('bitcoin', 14)
    btc_decision, btc_emoji, btc_reason, btc_conf = get_decision(btc_rsi)
    
    # الذهب (PAXG)
    paxg_data = get_coin_data('pax-gold')
    paxg_price = paxg_data['market_data']['current_price']['usd']
    paxg_rsi = calculate_rsi('pax-gold', 14)
    paxg_decision, paxg_emoji, paxg_reason, paxg_conf = get_decision(paxg_rsi)
    
    # تسجيل القرارات في CSV (دائماً)
    log_decision('BTC', btc_price, btc_rsi, btc_decision, btc_reason, btc_conf)
    log_decision('PAXG', paxg_price, paxg_rsi, paxg_decision, paxg_reason, paxg_conf)
    
    # التحقق من التنبيهات الذكية
    btc_alert, btc_alert_reason = should_send_alert('BTC', btc_price, btc_rsi, btc_decision, last_state)
    paxg_alert, paxg_alert_reason = should_send_alert('PAXG', paxg_price, paxg_rsi, paxg_decision, last_state)
    
    tg = TelegramBot(TELEGRAM_TOKEN, CHAT_ID)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')
    
    # إرسال فقط إذا كان هناك تنبيه
    if btc_alert or paxg_alert:
        alert_lines = []
        
        if btc_alert:
            alert_lines.append(f"🚨 <b>BTC ALERT:</b> {btc_alert_reason}")
            alert_lines.append(f"{btc_emoji} <b>BTC:</b> ${btc_price:,.0f} | RSI: {btc_rsi:.1f} | {btc_decision}")
        
        if paxg_alert:
            alert_lines.append(f"🚨 <b>GOLD ALERT:</b> {paxg_alert_reason}")
            alert_lines.append(f"{paxg_emoji} <b>GOLD:</b> ${paxg_price:,.0f} | RSI: {paxg_rsi:.1f} | {paxg_decision}")
        
        alert_lines.append(f" {timestamp}")
        
        msg = "\n".join(alert_lines)
        success = tg.send(msg)
        print(f"🚨 Alert sent: {success}")
    else:
        print("💤 No alert needed - market stable")
    
    # حفظ الحالة الجديدة
    new_state = {
        'BTC': {'price': btc_price, 'rsi': btc_rsi, 'decision': btc_decision},
        'PAXG': {'price': paxg_price, 'rsi': paxg_rsi, 'decision': paxg_decision}
    }
    save_state(new_state)
    
    print(f"BTC: ${btc_price:,.0f} | RSI: {btc_rsi:.1f} | {btc_decision}")
    print(f"PAXG: ${paxg_price:,.0f} | RSI: {paxg_rsi:.1f} | {paxg_decision}")

if __name__ == "__main__":
    analyze()
