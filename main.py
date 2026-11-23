import requests
import os
import csv
import json
from datetime import datetime, timedelta

# ============= Configuration =============
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = "362387912"
LOG_FILE = "trading_log.csv"
STATE_FILE = "last_state.json"
PORTFOLIO_FILE = "portfolio.json"

VIRTUAL_CASH = 1000.0

# === نظام الفرص المتدرجة (الحل الجديد) ===
MAX_TRADES_PER_ASSET = 5

OPPORTUNITY_TIERS = [
    (15,  75,  0,   0,   "طارئة 🔴"),
    (20,  60,  6,   1,   "قوية جداً 🟠"),
    (25,  50,  12,  2,   "قوية 🟡"),
    (30,  50,  24,  3,   "عادية 🟢"),
    (40,  40,  24,  3,   "خفيفة 🔵"),
]

STOP_LOSS_PERCENT = 8.0
TAKE_PROFIT_PERCENT = 15.0

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

# ============= Smart Decision Logic =============
def get_decision(rsi, macd, price, ema_9, last_rsi=None):
    if rsi < 30:
        return "BUY", "🟢", f"RSI منخفض جداً ({rsi:.1f}) - تشبع بيعي", 0.85
    elif rsi < 35 and macd is not None and macd < -50:
        return "BUY", "🟢", f"RSI منخفض ({rsi:.1f}) + MACD سلبي قوي", 0.75
    elif rsi < 40 and ema_9 is not None and price < ema_9:
        return "BUY", "🟡", f"RSI ({rsi:.1f}) + السعر تحت EMA 9", 0.65
    elif rsi > 75:
        return "SELL", "🔴", f"RSI مرتفع جداً ({rsi:.1f}) - تشبع شرائي", 0.85
    elif rsi > 70 and macd is not None and macd < 0:
        return "SELL", "🔴", f"RSI مرتفع ({rsi:.1f}) + MACD سلبي", 0.75
    else:
        return "HOLD", "🟡", "منطقة محايدة", 0.50

def get_opportunity_tier(rsi):
    for rsi_max, size, hours, drop, label in OPPORTUNITY_TIERS:
        if rsi < rsi_max:
            return size, hours, drop, label
    return None, None, None, None

# ============= State Management =============
def load_state():
    if os.path.isfile(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ============= Portfolio Management =============
def load_portfolio():
    if os.path.isfile(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'cash': VIRTUAL_CASH,
        'holdings': {'BTC': 0.0, 'PAXG': 0.0},
        'avg_buy_price': {'BTC': 0.0, 'PAXG': 0.0},
        'last_buy_price': {'BTC': 0.0, 'PAXG': 0.0},
        'last_buy_time': {'BTC': None, 'PAXG': None},
        'trades_count': {'BTC': 0, 'PAXG': 0},
        'total_trades': 0,
        'start_date': datetime.now().strftime('%Y-%m-%d')
    }

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)

def check_stop_loss_take_profit(coin_name, current_price, portfolio):
    avg_price = portfolio['avg_buy_price'].get(coin_name, 0.0)
    qty = portfolio['holdings'].get(coin_name, 0.0)
    if qty <= 0 or avg_price <= 0:
        return None, None
    change_pct = ((current_price - avg_price) / avg_price) * 100
    if change_pct <= -STOP_LOSS_PERCENT:
        return "SELL", f"⚠️ STOP-LOSS: انخفض {change_pct:.1f}% عن متوسط الشراء (${avg_price:,.0f})"
    elif change_pct >= TAKE_PROFIT_PERCENT:
        return "SELL", f"🎯 TAKE-PROFIT: ارتفع {change_pct:.1f}% عن متوسط الشراء (${avg_price:,.0f})"
    return None, None

def execute_paper_trade(coin_name, decision, price, portfolio, rsi):
    trade_action = "لا يوجد تداول"
    rejection_reason = None
    
    # الفحص 1: Stop-Loss / Take-Profit
    sl_tp_decision, sl_tp_reason = check_stop_loss_take_profit(coin_name, price, portfolio)
    if sl_tp_decision == "SELL" and portfolio['holdings'].get(coin_name, 0.0) > 0:
        qty = portfolio['holdings'][coin_name]
        sell_value = qty * price
        portfolio['cash'] += sell_value
        portfolio['holdings'][coin_name] = 0.0
        portfolio['avg_buy_price'][coin_name] = 0.0
        portfolio['total_trades'] += 1
        trade_action = f"بيع {sl_tp_reason} @ ${price:,.0f} (قيمة: ${sell_value:,.0f})"
        return trade_action
    
    # الفحص 2: قرار الشراء مع نظام الفرص المتدرجة
    if decision == "BUY":
        trade_size, min_hours, min_drop_pct, urgency = get_opportunity_tier(rsi)
        
        if trade_size is None:
            trade_action = "لا يوجد تداول (RSI مرتفع جداً للشراء)"
            return trade_action
        
        if portfolio['trades_count'].get(coin_name, 0) >= MAX_TRADES_PER_ASSET:
            rejection_reason = f"تجاوز الحد الأقصى ({MAX_TRADES_PER_ASSET} صفقة)"
        elif portfolio['cash'] < trade_size:
            rejection_reason = f"كاش غير كافٍ (${portfolio['cash']:.0f} < ${trade_size})"
        else:
            last_time_str = portfolio['last_buy_time'].get(coin_name)
            if last_time_str and min_hours > 0:
                last_time = datetime.fromisoformat(last_time_str)
                hours_since = (datetime.now() - last_time).total_seconds() / 3600
                if hours_since < min_hours:
                    rejection_reason = f"انتظار {min_hours}س ({urgency}) - مرت {hours_since:.0f}س فقط"
            
            if not rejection_reason:
                last_price = portfolio['last_buy_price'].get(coin_name, 0.0)
                if last_price > 0 and min_drop_pct > 0:
                    drop_pct = ((last_price - price) / last_price) * 100
                    if drop_pct < min_drop_pct:
                        rejection_reason = f"انخفاض غير كافٍ ({drop_pct:.1f}% < {min_drop_pct}%) ({urgency})"
        
        if not rejection_reason:
            qty = trade_size / price
            portfolio['holdings'][coin_name] = portfolio['holdings'].get(coin_name, 0.0) + qty
            portfolio['cash'] -= trade_size
            portfolio['total_trades'] += 1
            portfolio['trades_count'][coin_name] = portfolio['trades_count'].get(coin_name, 0) + 1
            
            old_qty = portfolio['holdings'][coin_name] - qty
            old_avg = portfolio['avg_buy_price'].get(coin_name, 0.0)
            if old_qty > 0:
                total_value = (old_qty * old_avg) + (qty * price)
                portfolio['avg_buy_price'][coin_name] = total_value / portfolio['holdings'][coin_name]
            else:
                portfolio['avg_buy_price'][coin_name] = price
            
            portfolio['last_buy_price'][coin_name] = price
            portfolio['last_buy_time'][coin_name] = datetime.now().isoformat()
            
            trade_action = f"شراء {qty:.6f} @ ${price:,.0f} (${trade_size}) [{urgency}] (متوسط: ${portfolio['avg_buy_price'][coin_name]:,.0f})"
        else:
            trade_action = f"رُفض: {rejection_reason}"
    
    elif decision == "SELL" and portfolio['holdings'].get(coin_name, 0.0) > 0:
        qty = portfolio['holdings'][coin_name]
        sell_value = qty * price
        portfolio['cash'] += sell_value
        portfolio['holdings'][coin_name] = 0.0
        portfolio['avg_buy_price'][coin_name] = 0.0
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

# ============= Smart Alerts =============
def should_send_alert(coin, price, rsi, macd, decision, last_state):
    if coin not in last_state:
        return True, "أول تشغيل"
    last = last_state[coin]
    last_price = last['price']
    last_decision = last['decision']
    if decision != last_decision:
        return True, f"تغير القرار من {last_decision} إلى {decision}"
    if rsi < 30 or rsi > 75:
        return True, f"RSI حرج ({rsi:.1f})"
    price_change_pct = abs(price - last_price) / last_price * 100
    if price_change_pct > 3.0:
        return True, f"تغير السعر {price_change_pct:.2f}%"
    last_macd = last.get('macd')
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
    print("Fetching data and running Smart Paper Trading (Tiered)...")
    
    last_state = load_state()
    portfolio = load_portfolio()
    alerts = []
    current_prices = {}
    new_state = {}
    
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
        
        last_rsi = last_state.get(coin_name, {}).get('rsi')
        decision, emoji, reason, confidence = get_decision(rsi, macd, price, ema_9, last_rsi)
        
        trade_action = execute_paper_trade(coin_name, decision, price, portfolio, rsi)
        
        log_decision(coin_name, price, rsi, macd, ema_9, ema_21, decision, reason, confidence, trade_action)
        
        should_alert, alert_reason = should_send_alert(coin_name, price, rsi, macd, decision, last_state)
        
        if "رُفض" in trade_action:
            should_alert = True
            alert_reason = trade_action
        if "STOP-LOSS" in trade_action or "TAKE-PROFIT" in trade_action:
            should_alert = True
            alert_reason = trade_action
        
        if should_alert:
            alerts.append({
                'name': coin_name, 'emoji': emoji, 'price': price, 'rsi': rsi,
                'macd': macd, 'ema_9': ema_9, 'decision': decision, 'reason': reason,
                'confidence': confidence, 'alert_reason': alert_reason, 'trade_action': trade_action
            })
        
        new_state[coin_name] = {
            'price': price, 'rsi': rsi, 'macd': macd, 'decision': decision
        }
        
        macd_str = f"{macd:.2f}" if macd is not None else "N/A"
        trades_count = portfolio['trades_count'].get(coin_name, 0)
        avg_price = portfolio['avg_buy_price'].get(coin_name, 0.0)
        tier_size, tier_hours, tier_drop, tier_label = get_opportunity_tier(rsi)
        print(f"{coin_name}: ${price:,.0f} | RSI: {rsi:.1f} | MACD: {macd_str} | {decision}")
        if tier_size:
            print(f"  Tier: {tier_label} | Size: ${tier_size} | Wait: {tier_hours}h | Drop: {tier_drop}%")
        print(f"  Trades: {trades_count}/{MAX_TRADES_PER_ASSET} | Avg: ${avg_price:,.0f}")
        print(f"  Action: {trade_action}")
    
    save_state(new_state)
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
            msg_lines.append(f"📝 Reason: {alert['reason']}")
            msg_lines.append(f"🎯 Confidence: {alert['confidence']*100:.0f}%")
            msg_lines.append(f"💼 Trade: {alert['trade_action']}")
            msg_lines.append(f"⚡ Alert: {alert['alert_reason']}")
        
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        msg_lines.append(f"\n{'━' * 25}")
        msg_lines.append(f"💰 <b>Portfolio Value:</b> ${total_value:,.2f}")
        msg_lines.append(f"📈 <b>Total PnL:</b> {pnl_emoji} ${total_pnl:+,.2f} ({pnl_pct:+.2f}%)")
        msg_lines.append(f"🔄 <b>Total Trades:</b> {portfolio['total_trades']}")
        msg_lines.append(f"⏰ {timestamp}")
        
        msg = "\n".join(msg_lines)
        success = tg.send(msg)
        print(f"\n🚨 Alert sent: {success}")
    else:
        print("\n💤 No alert needed - market stable")

if __name__ == "__main__":
    analyze()
