import ccxt
import pandas as pd
import requests
import time

# --- 你的設定資訊 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"TG Error: {e}")

def check_bitget_signals():
    # 啟動通知
    send_telegram_msg("🔍 *Bitget 3D 掃描啟動*")
    
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        # 篩選 USDT 永續合約
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and m.get('active')]
        
        hit_symbols = []
        for symbol in symbols:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
                if len(ohlcv) < 10:
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # 取得最新收盤與過去8根次低點
                last_close = df['close'].iloc[-1]
                lookback_lows = df['low'].iloc[-9:-1].tolist()
                second_lowest = sorted(lookback_lows)[1]
                
                if last_close > second_lowest:
                    hit_symbols.append(f"• `{symbol:10}` | {last_close}")
                
                time.sleep(0.1) # 避開限制
            except:
                continue

        if hit_symbols:
            msg = "✅ *符合條件品種:*\n" + "\n".join(hit_symbols)
            send_telegram_msg(msg)
        else:
            send_telegram_msg("⚠️ 目前無符合條件品種")

    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
