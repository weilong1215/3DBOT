import ccxt
import pandas as pd
import requests
import os

# --- 直接填入你的設定 ---
TELEGRAM_TOKEN = '你的_TOKEN'
TELEGRAM_CHAT_ID = '你的_CHAT_ID'

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except:
        pass

def check_bitget_signals():
    exchange = ccxt.bitget()
    print("正在獲取 Bitget 永續合約列表...")
    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and m.get('active')]
        
        hit_symbols = []
        for symbol in symbols:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
                if len(ohlcv) < 10: continue
                df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                last_close = df['c'].iloc[-1]
                lookback_lows = df['l'].iloc[-9:-1].tolist()
                second_lowest = sorted(lookback_lows)[1]
                
                if last_close > second_lowest:
                    hit_symbols.append(f"• `{symbol:10}` (現價: {last_close})")
            except:
                continue

        if hit_symbols:
            report = "🔔 *Bitget 3D 級別選幣結果*\n" + "\n".join(hit_symbols)
            send_telegram_msg(report)
            print("訊號已發送")
    except Exception as e:
        print(f"錯誤: {e}")

if __name__ == "__main__":
    check_bitget_signals()
