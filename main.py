import ccxt
import pandas as pd
import requests
import time
from datetime import datetime, timezone

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
    send_telegram_msg("🔍 *Bitget 3D 壓力測試掃描...*\n條件：開盤 < 壓力 且 最高 >= 壓力")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        hit_symbols = []
        for symbol in symbols:
            try:
                # 1. 抓取日K線 (1D) 數據進行手動封裝 (確保 1/1 對齊)
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=60)
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['date'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True)
                
                # 2. 1/1 重啟邏輯分組
                df_1d['year'] = df_1d['date'].dt.year
                df_1d['day_of_year'] = df_1d['date'].dt.dayofyear
                df_1d['group'] = df_1d['year'].astype(str) + "_" + ((df_1d['day_of_year'] - 1) // 3).astype(str)
                
                # 3. 封裝成 3D 數據
                df_3d = df_1d.groupby('group').agg({
                    'date': 'first',
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last'
                }).sort_values('date').reset_index(drop=True)
                
                df_3d['date_str'] = df_3d['date'].dt.strftime('%m/%d')
                
                # --- 判斷邏輯 ---
                latest_3d = df_3d.iloc[-1]
                latest_open = latest_3d['open']
                latest_high = latest_3d['high']
                
                # 往前 8 根 3D K棒 (不含當前) 找出第二低點作為「壓力」
                lookback_3d = df_3d.iloc[-9:-1]
                if len(lookback_3d) < 8: continue
                
                # 取得第二低點
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                sec_low_p = sorted_3d.loc[1, 'low']
                sec_low_d = sorted_3d.loc[1, 'date_str']
                
                # --- 執行條件 ---
                # 1. 開盤價 < 第二低點 (壓力)
                # 2. 最高價 >= 第二低點 (觸碰壓力)
                if latest_open < sec_low_p and latest_high >= sec_low_p:
                    clean_name = symbol.split(':')[0]
                    hit_symbols.append(
                        f"• `{clean_name:10}`\n"
                        f"  壓力: `{sec_low_p}` (`{sec_low_d}`)"
                    )
                
                time.sleep(0.1)
            except:
                continue

        if hit_symbols:
            for i in range(0, len(hit_symbols), 30):
                msg = "✅ *3D 壓力位觸碰結果 (1/1 起算):*\n\n" + "\n".join(hit_symbols[i:i + 30])
                send_telegram_msg(msg)
                time.sleep(1)
        else:
            send_telegram_msg("⚠️ 目前無符合觸碰壓力條件之品種。")

    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
