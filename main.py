import ccxt
import pandas as pd
import requests
import time
from datetime import datetime

# --- 設定資訊 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=20)
    except:
        pass

def check_bitget_signals():
    # 啟動時的簡短通知
    send_telegram_msg("🔍 *Bitget 3D 掃描中...*")
    
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        hit_symbols = []
        for symbol in symbols:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
                if len(ohlcv) < 10: continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = df['timestamp'].apply(lambda x: datetime.fromtimestamp(x/1000).strftime('%m/%d'))
                
                latest_high = df['high'].iloc[-1]
                latest_close = df['close'].iloc[-1]
                
                # 取得過去 8 根 K 棒的數據 (Index -9 到 -2)
                lookback_df = df.iloc[-9:-1].copy()
                
                # 排序找出最低與第二低點
                sorted_df = lookback_df.sort_values(by='low').reset_index(drop=True)
                
                lowest_p = sorted_df.loc[0, 'low']
                lowest_d = sorted_df.loc[0, 'date']
                
                second_p = sorted_df.loc[1, 'low']
                second_d = sorted_df.loc[1, 'date']
                
                third_p = sorted_df.loc[2, 'low'] # 用於邏輯判斷
                
                # --- 核心條件 ---
                # 1. 最高價碰過二低 (latest_high >= second_p)
                # 2. 目前價格未過三低 (latest_close < third_p)
                if latest_high >= second_p and latest_close < third_p:
                    clean_name = symbol.split(':')[0]
                    hit_symbols.append(
                        f"• `{clean_name:10}`\n"
                        f"  最低: `{lowest_d}` / `{lowest_p}`\n"
                        f"  二低: `{second_d}` / `{second_p}`"
                    )
                
                time.sleep(0.1) 
            except:
                continue

        # 結果發送
        if hit_symbols:
            # 每 25 個幣分一段，保持簡潔
            for i in range(0, len(hit_symbols), 25):
                msg = "✅ *3D 掃描結果 (二低 < 最高 & 現價 < 三低):*\n\n" + "\n".join(hit_symbols[i:i + 25])
                send_telegram_msg(msg)
                time.sleep(1)
        else:
            send_telegram_msg("⚠️ 目前無符合條件品種。")

    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
