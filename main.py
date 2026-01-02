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
        requests.post(url, json=payload, timeout=15)
    except:
        pass

def check_bitget_signals():
    send_telegram_msg("🚀 *開始掃描 Bitget 永續合約...*")
    
    # 初始化交易所，開啟詳細市場資訊
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        
        # 精準篩選：USDT 結算的「永續合約」 (Linear Swap)
        # Bitget 的永續合約在 CCXT 中 symbol 通常長這樣: BTC/USDT:USDT
        symbols = [
            s for s, m in markets.items() 
            if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT'
        ]
        
        if not symbols:
            send_telegram_msg("❌ 錯誤：找不到任何 USDT 永續合約，請檢查 API 連線。")
            return

        print(f"找到 {len(symbols)} 個永續合約，開始計算 3D 數據...")
        
        hit_symbols = []
        error_count = 0
        
        for symbol in symbols:
            try:
                # 抓取 3D K線
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
                if len(ohlcv) < 10:
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # 邏輯判斷
                last_close = df['close'].iloc[-1]
                lookback_lows = df['low'].iloc[-9:-1].tolist()
                
                # 排序取第二小
                sorted_lows = sorted(lookback_lows)
                second_lowest = sorted_lows[1]
                
                if last_close > second_lowest:
                    # 格式化名字，拿掉後面的 :USDT 方便閱讀
                    clean_name = symbol.split(':')[0]
                    hit_symbols.append(f"• `{clean_name:10}` | 價: {last_close}")
                
                time.sleep(0.15) # 稍微增加延遲確保穩定
            except:
                error_count += 1
                continue

        # 彙整發送
        report = f"📊 *掃描報告*\n"
        report += f"總計掃描永續合約: {len(symbols)} 個\n"
        report += f"失敗數量: {error_count}\n"
        report += "------------------------\n"
        
        if hit_symbols:
            report += "✅ *符合條件品種:*\n" + "\n".join(hit_symbols)
        else:
            report += "⚠️ 目前無品種符合條件。"
            
        send_telegram_msg(report)

    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
