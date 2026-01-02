import ccxt
import pandas as pd
import requests
import time

# --- 設定資訊 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=20)
    except Exception as e:
        print(f"發送失敗: {e}")

def check_bitget_signals():
    send_telegram_msg("🚀 *開始精確掃描 Bitget 永續合約...*\n條件：二級低點 < 目前價 < 三級低點")
    
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        total = len(symbols)
        hit_symbols = []
        processed = 0
        
        for symbol in symbols:
            try:
                # 獲取 3D K線
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
                if len(ohlcv) < 10: 
                    processed += 1
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                last_close = df['close'].iloc[-1]
                
                # 取得過去 8 根 K 棒的最低價列表 (Index -9 到 -2)
                lookback_lows = df['low'].iloc[-9:-1].tolist()
                sorted_lows = sorted(lookback_lows)
                
                # 取得第二低點與第三低點
                second_lowest = sorted_lows[1]
                third_lowest = sorted_lows[2]
                
                # --- 新條件邏輯 ---
                # 1. 收盤價 > 第二低點
                # 2. 收盤價 < 第三低點 (如果大於第三低點則不符合)
                if last_close > second_lowest and last_close < third_lowest:
                    clean_name = symbol.split(':')[0]
                    hit_symbols.append(f"• `{clean_name:10}`\n  現價: `{last_close}`\n  二低: `{second_lowest}`\n  三低: `{third_lowest}`")
                
                processed += 1
                if processed % 100 == 0:
                    print(f"進度: {processed}/{total}...")
                
                time.sleep(0.1) 
            except:
                processed += 1
                continue

        # 結果彙整
        report_header = f"📊 *掃描完成 (3D 級別)*\n總檢查: {total} 個合約\n"
        
        if hit_symbols:
            send_telegram_msg(report_header + "✅ *符合條件 (夾在二三低點間):*")
            # 由於詳細資訊變多，每 15 個幣分一段發送
            for i in range(0, len(hit_symbols), 15):
                chunk = "\n".join(hit_symbols[i:i + 15])
                send_telegram_msg(chunk)
                time.sleep(1)
        else:
            send_telegram_msg(report_header + "⚠️ *目前無任何品種符合此區間條件。*")

    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
