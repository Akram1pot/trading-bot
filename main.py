import ccxt
import requests
import os
from datetime import datetime
from dataclasses import dataclass

# ============= Telegram Configuration =============
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = "362387912"

# ============= Telegram Bot Class =============
class TelegramBot:
    def __init__(self, token, chat_id):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
    
    def send(self, text):
        try:
            requests.post(self.url, json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
            return True
        except:
            return False

# ============= Guardrails =============
@dataclass
class TradingGuardrails:
    min_trade_usd: float = 10.0
    max_trade_usd: float = 100.0

class ActionValidator:
    @staticmethod
    def validate(action, guardrails):
        if action.get('type') not in ['BUY', 'SELL', 'HOLD']:
            return False, "نوع إجراء غير صالح"
        if action['type'] == 'HOLD':
            return True, "HOLD مسموح دائماً"
        value = action.get('order_value_usd', 0)
        if value < 0:
            return False, "قيمة سالبة"
        if value < guardrails.min_trade_usd or value > guardrails.max_trade_usd:
            return False, "خارج الحدود"
        if action.get('symbol') not in ['BTC/USDT', 'PAXG/USDT']:
            return False, "رمز غير مدعوم"
        return True, "صالح"

# ============= Technical Analysis Provider =============
class TechnicalAnalysisProvider:
    def propose(self, data):
        rsi = data.get('rsi', 50)
        macd = data.get('macd', 0)
        price = data.get('price', 0)
        ema_9 = data.get('ema_9', 0)
        
        if rsi < 30 and macd > 0 and price > ema_9:
            return {"type": "BUY", "symbol": "BTC/USDT", "order_value_usd": 50,
                    "reason": f"RSI منخفض ({rsi:.1f}) + MACD إيجابي", "confidence": 0.85}
        elif rsi > 70 and macd < 0:
            return {"type": "SELL", "symbol": "BTC/USDT", "order_value_usd": 50,
                    "reason": f"RSI مرتفع ({rsi:.1f}) + MACD سلبي", "confidence": 0.80}
        else:
            return {"type": "HOLD", "symbol": "BTC/USDT", "order_value_usd": 0,
                    "reason": "لا إشارة واضحة", "confidence": 0.50}

# ============= Helpers =============
def calc_ema(prices, period):
    m = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = (p - ema) * m + ema
    return ema

def calc_macd(prices):
    return calc_ema(prices, 12) - calc_ema(prices, 26)

def calc_rsi(candles, period=14):
    closes = [c[4] for c in candles]
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i-1]
        gains.append(ch if ch > 0 else 0)
        losses.append(abs(ch) if ch < 0 else 0)
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0: return 100
    return 100 - (100 / (1 + ag/al))

# ============= Main =============
def analyze_and_notify():
    guardrails = TradingGuardrails()
    validator = ActionValidator()
    provider = TechnicalAnalysisProvider()
    tg = TelegramBot(TELEGRAM_TOKEN, CHAT_ID)
    
    exchange = ccxt.binance({'enableRateLimit': True})
    candles = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=100)
    ticker = exchange.fetch_ticker('BTC/USDT')
    
    price = ticker['last']
    closes = [c[4] for c in candles]
    rsi = calc_rsi(candles, 14)
    macd = calc_macd(closes)
    ema_9 = calc_ema(closes[-20:], 9)
    ema_21 = calc_ema(closes[-30:], 21)
    
    action = provider.propose({'rsi': rsi, 'macd': macd, 'price': price, 'ema_9': ema_9, 'symbol': 'BTC/USDT'})
    is_valid, reason = validator.validate(action, guardrails)
    
    emoji = {"BUY": "", "SELL": "🔴"}.get(action['type'], "🟡")
    v = "✅" if is_valid else "❌"
    
    msg = f"""
 <b>BTC/USDT Analysis</b>
━━━━━━━━━━━━━━━
💰 Price: ${price:,.2f}
📈 RSI: {rsi:.2f} | MACD: {macd:.2f}
 EMA 9: ${ema_9:,.2f} | EMA 21: ${ema_21:,.2f}
━━━━━━━━━━━━━━━
{emoji} Decision: {action['type']}
 Reason: {action['reason']}
🎯 Confidence: {action['confidence']*100:.0f}%
🛡️ Validation: {v} {reason}
 {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    tg.send(msg)
    print(f"Analysis: {action['type']} | Price: ${price:,.2f}")

if __name__ == "__main__":
    analyze_and_notify()
