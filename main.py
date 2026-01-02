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
    send_telegram_msg("🚀 *開始掃描 Bitget (529+個合約)...*\n預計耗時 2-3 分鐘，請稍候。")
    
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        total = len(symbols)
        hit_symbols = []
        processed = 0
        
        for symbol in symbols:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
                if len(ohlcv) < 10: 
                    processed += 1
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                last_close = df['close'].iloc[-1]
                lookback_lows = df['low'].iloc[-9:-1].tolist()
                second_lowest = sorted(lookback_lows)[1]
                
                if last_close > second_lowest:
                    clean_name = symbol.split(':')[0]
                    hit_symbols.append(f"• `{clean_name:10}` | {last_close}")
                
                processed += 1
                # 每掃描 100 個幣在日誌噴一次進度，避免 GitHub 認為程式卡死
                if processed % 100 == 0:
                    print(f"目前進度: {processed}/{total}...")
                
                time.sleep(0.1) # 縮短延遲加快速度
            except:
                processed += 1
                continue

        # 最後結果彙整
        report_header = f"📊 *掃描完成 (3D 級別)*\n總計檢查: {total} 個永續合約\n"
        
        if hit_symbols:
            # 如果符合的幣太多，每 30 個分一封信，防止 Telegram 訊息過長
            send_telegram_msg(report_header + "✅ *符合條件清單如下:*")
            for i in range(0, len(hit_symbols), 30):
                chunk = "\n".join(hit_symbols[i:i + 30])
                send_telegram_msg(chunk)
                time.sleep(1)
        else:
            send_telegram_msg(report_header + "⚠️ *目前無任何品種符合條件。*")

    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
