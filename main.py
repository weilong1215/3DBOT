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
    send_telegram_msg("🔍 *Bitget 3D 自定義掃描 (1/1 重啟邏輯)...*")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        hit_symbols = []
        for symbol in symbols:
            try:
                # 1. 抓取日K線 (1D) 數據
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=60)
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['date'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True)
                
                # 2. 手動計算分組編號 (Group ID)
                # 邏輯：年份 + ((該日在該年的第幾天 - 1) // 3)
                # 這樣 1/1, 1/2, 1/3 會分在同一組；1/1 永遠是新的一組
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
                latest_high = latest_3d['high']
                latest_close = latest_3d['close']
                
                # 往前 8 根 3D K棒 (Index -9 到 -2)
                lookback_3d = df_3d.iloc[-9:-1]
                if len(lookback_3d) < 8: continue
                
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                
                low_p, low_d = sorted_3d.loc[0, 'low'], sorted_3d.loc[0, 'date_str']
                sec_p, sec_d = sorted_3d.loc[1, 'low'], sorted_3d.loc[1, 'date_str']
                third_p = sorted_3d.loc[2, 'low']
                
                # 條件：最高碰過二低，且收盤低於三低
                if latest_high >= sec_p and latest_close < third_p:
                    clean_name = symbol.split(':')[0]
                    hit_symbols.append(
                        f"• `{clean_name:10}`\n"
                        f"  最低: `{low_d}` / `{low_p}`\n"
                        f"  二低: `{sec_d}` / `{sec_p}`"
                    )
                
                time.sleep(0.12)
            except:
                continue

        if hit_symbols:
            for i in range(0, len(hit_symbols), 25):
                msg = "✅ *自定義 3D 掃描結果 (1/1 起算):*\n\n" + "\n".join(hit_symbols[i:i + 25])
                send_telegram_msg(msg)
                time.sleep(1)
        else:
            send_telegram_msg("⚠️ 目前無符合條件品種。")

    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
