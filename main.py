import requests
import os
import csv
import json
from datetime import datetime

# ============= Configuration =============
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = "362387912"
LOG_FILE = "trading_log.csv"
PORTFOLIO_FILE = "portfolio.json"

VIRTUAL_CASH = 1000.0
TRADE_SIZE_USD = 50.0  # تقليل من $100 إلى $50

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

def get_price_history(coin_id, days=30):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return [p[1] for p in data['prices']]

# ============= Technical Indicators =============
def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_macd(prices):
    if len(prices) < 26:
        return None, None, None
    ema_12 = calculate_ema(prices, 12)
    ema_26 = calculate_ema(prices, 26)
    macd = ema_12 - ema_26
    return macd, ema_12, ema_26

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ============= Smart Decision Logic (محسّن) =============
def get_decision(rsi, macd, price, ema_9, last_rsi=None):
    """
    منطق قرار محسّن - أكثر مرونة في الشراء:
    - BUY قوي: RSI < 30 (بدلاً من 25)
    - BUY متوسط: RSI < 35 + MACD < -50
    - BUY خفيف: RSI < 40 + السعر تحت EMA 9
    """
    # BUY قوي: RSI منخفض جداً (تشبع بيعي)
    if rsi < 30:
        return "BUY", "🟢", f"RSI منخفض جداً ({rsi:.1f}) - تشبع بيعي", 0.85
    
    # BUY متوسط: RSI منخفض + MACD سلبي قوي
    elif rsi < 35 and macd is not None and macd < -50:
        return "BUY", "🟢", f"RSI منخفض ({rsi:.1f}) + MACD سلبي قوي ({macd:.1f})", 0.75
    
    # BUY خفيف: RSI معتدل + السعر تحت EMA
    elif rsi < 40 and ema_9 is not None and price < ema_9:
        return "BUY", "", f"RSI ({rsi:.1f}) + السعر تحت EMA 9", 0.65
    
    # SELL قوي: RSI مرتفع جداً
    elif rsi > 75:
        return "SELL", "🔴", f"RSI مرتفع جداً ({rsi:.1f}) - تشبع شرائي شديد", 0.85
    
    # SELL متوسط: RSI مرتفع + MACD سلبي
    elif rsi > 70 and macd is not None and macd < 0:
        return "SELL", "🔴", f"RSI مرتفع ({rsi:.1f}) + MACD سلبي", 0.75
    
    # منطقة محايدة
    else:
        return "HOLD", "", "منطقة محايدة", 0.50

# ============= Paper Trading =============
def load_portfolio():
    if os.path.isfile(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'cash': VIRTUAL_CASH,
        'holdings': {'BTC': 0.0, 'PAXG': 0.0},
        'total_trades': 0,
        'start_date': datetime.now().strftime('%Y-%m-%d')
    }

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)

def execute_paper_trade(coin_name, decision, price, portfolio):
    trade_action = "لا يوجد تداول"
    
    if decision == "BUY" and portfolio['cash'] >= TRADE_SIZE_USD:
        qty = TRADE_SIZE_USD / price
        portfolio['holdings'][coin_name] = portfolio['holdings'].get(coin_name, 0.0) + qty
        portfolio['cash'] -= TRADE_SIZE_USD
        portfolio['total_trades'] += 1
        trade_action = f"شراء {qty:.6f} @ ${price:,.0f}"
        
    elif decision == "SELL" and portfolio['holdings'].get(coin_name, 0.0) > 0:
        qty = portfolio['holdings'][coin_name]
        sell_value = qty * price
        portfolio['cash'] += sell_value
        portfolio['holdings'][coin_name] = 0.0
        portfolio['total_trades'] += 1
        trade_action = f"بيع {qty:.6f} @ ${price:,.0f} (قيمة: ${sell_value:,.0f})"
        
    return trade_action

def calculate_portfolio_value(portfolio, current_prices):
    current_value = portfolio['cash']
    holdings_value = 0.0
    for coin, qty in portfolio['holdings'].items():
        if qty > 0 and coin in current_prices:
            holdings_value += qty * current_prices[coin]
    total_value = current_value + holdings_value
    total_pnl = total_value - VIRTUAL_CASH
    pnl_pct = (total_pnl / VIRTUAL_CASH) * 100
    return total_value, total_pnl, pnl_pct

# ============= State Management =============
def get_last_state_from_csv(coin_name):
    if not os.path.isfile(LOG_FILE):
        return None
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return None
            f.seek(0)
            reader = csv.DictReader(f)
            if reader.fieldnames is None or 'coin' not in reader.fieldnames:
                return None
            last_row = None
            for row in reader:
                if row.get('coin') == coin_name:
                    last_row = row
            if last_row is None:
                return None
            state = {
                'price': float(last_row['price'].replace('$', '').replace(',', '')),
                'rsi': float(last_row['rsi']),
                'decision': last_row['decision'],
            }
            if 'macd' in last_row and last_row['macd'] != 'N/A':
                try:
                    state['macd'] = float(last_row['macd'])
                except (ValueError, TypeError):
                    state['macd'] = None
            else:
                state['macd'] = None
            return state
    except Exception as e:
        print(f"⚠️ Error reading CSV: {e}")
        return None

def should_send_alert(coin, price, rsi, macd, decision, last_state):
    if last_state is None:
        return True, "أول تشغيل"
    last_price = last_state['price']
    last_decision = last_state['decision']
    if decision != last_decision:
        return True, f"تغير القرار من {last_decision} إلى {decision}"
    if rsi < 30 or rsi > 75:
        return True, f"RSI حرج ({rsi:.1f})"
    price_change_pct = abs(price - last_price) / last_price * 100
    if price_change_pct > 3.0:
        return True, f"تغير السعر {price_change_pct:.2f}%"
    last_macd = last_state.get('macd')
    if last_macd is not None and macd is not None:
        if last_macd < 0 and macd > 0:
            return True, "MACD تحول إيجابي"
        elif last_macd > 0 and macd < 0:
            return True, "MACD تحول سلبي"
    return False, None

# ============= Logging =============
def log_decision(coin, price, rsi, macd, ema_9, ema_21, decision, reason, confidence, trade_action):
    file_exists = os.path.isfile(LOG_FILE) and os.path.getsize(LOG_FILE) > 0
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['timestamp', 'coin', 'price', 'rsi', 'macd', 'ema_9', 'ema_21', 'decision', 'reason', 'confidence', 'trade_action'])
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M UTC'),
            coin,
            f"${price:,.2f}",
            f"{rsi:.2f}",
            f"{macd:.2f}" if macd is not None else "N/A",
            f"${ema_9:,.2f}" if ema_9 is not None else "N/A",
            f"${ema_21:,.2f}" if ema_21 is not None else "N/A",
            decision,
            reason,
            f"{confidence*100:.0f}%",
            trade_action
        ])

# ============= Main Analysis =============
def analyze():
    print("Fetching data and running Paper Trading...")
    
    portfolio = load_portfolio()
    alerts = []
    current_prices = {}
    
    for coin_id, coin_name in [('bitcoin', 'BTC'), ('pax-gold', 'PAXG')]:
        print(f"\n--- {coin_name} ---")
        
        coin_data = get_coin_data(coin_id)
        price = coin_data['market_data']['current_price']['usd']
        current_prices[coin_name] = price
        
        price_history = get_price_history(coin_id, days=30)
        rsi = calculate_rsi(price_history, 14)
        macd, ema_12, ema_26 = calculate_macd(price_history)
        ema_9 = calculate_ema(price_history[-20:], 9) if len(price_history) >= 20 else None
        ema_21 = calculate_ema(price_history[-30:], 21) if len(price_history) >= 30 else None
        
        last_state = get_last_state_from_csv(coin_name)
        last_rsi = last_state['rsi'] if last_state else None
        
        decision, emoji, reason, confidence = get_decision(rsi, macd, price, ema_9, last_rsi)
        
        trade_action = execute_paper_trade(coin_name, decision, price, portfolio)
        
        log_decision(coin_name, price, rsi, macd, ema_9, ema_21, decision, reason, confidence, trade_action)
        
        should_alert, alert_reason = should_send_alert(coin_name, price, rsi, macd, decision, last_state)
        
        if should_alert:
            alerts.append({
                'name': coin_name,
                'emoji': emoji,
                'price': price,
                'rsi': rsi,
                'macd': macd,
                'ema_9': ema_9,
                'decision': decision,
                'reason': reason,
                'confidence': confidence,
                'alert_reason': alert_reason,
                'trade_action': trade_action
            })
        
        macd_str = f"{macd:.2f}" if macd is not None else "N/A"
        print(f"{coin_name}: ${price:,.0f} | RSI: {rsi:.1f} | MACD: {macd_str} | {decision} | {trade_action}")
    
    save_portfolio(portfolio)
    total_value, total_pnl, pnl_pct = calculate_portfolio_value(portfolio, current_prices)
    
    if alerts:
        tg = TelegramBot(TELEGRAM_TOKEN, CHAT_ID)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')
        
        msg_lines = [f"🚨 <b>Smart Alert & Paper Trade</b>\n{'━' * 25}"]
        
        for alert in alerts:
            msg_lines.append(f"\n{alert['emoji']} <b>{alert['name']}:</b> ${alert['price']:,.0f}")
            macd_str = f"{alert['macd']:.2f}" if alert['macd'] is not None else "N/A"
            msg_lines.append(f"📊 RSI: {alert['rsi']:.1f} | MACD: {macd_str}")
            if alert['ema_9']:
                msg_lines.append(f"📈 EMA 9: ${alert['ema_9']:,.0f}")
            msg_lines.append(f"{alert['emoji']} Decision: {alert['decision']}")
            msg_lines.append(f" Reason: {alert['reason']}")
            msg_lines.append(f"🎯 Confidence: {alert['confidence']*100:.0f}%")
            msg_lines.append(f"💼 Trade: {alert['trade_action']}")
            msg_lines.append(f" Alert: {alert['alert_reason']}")
        
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        msg_lines.append(f"\n{'━' * 25}")
        msg_lines.append(f" <b>Portfolio Value:</b> ${total_value:,.2f}")
        msg_lines.append(f"📈 <b>Total PnL:</b> {pnl_emoji} ${total_pnl:+,.2f} ({pnl_pct:+.2f}%)")
        msg_lines.append(f"🔄 <b>Total Trades:</b> {portfolio['total_trades']}")
        msg_lines.append(f"⏰ {timestamp}")
        
        msg = "\n".join(msg_lines)
        success = tg.send(msg)
        print(f"\n🚨 Alert sent: {success}")
    else:
        print("\n No alert needed - market stable")

if __name__ == "__main__":
    analyze()
