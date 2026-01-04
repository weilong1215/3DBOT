import ccxt
import pandas as pd
import requests
import time
import os
from datetime import datetime

# --- 設定資訊 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'
DB_FILE = os.path.join(os.getcwd(), "last_symbols.txt")

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload, timeout=20)
    except: pass

def check_bitget_signals():
    send_telegram_msg("🔄 *1/4 換軌掃描啟動* (針對 US 標的對齊)")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    current_data = {}
    us_debug_info = "尚未找到 US 標的"

    try:
        markets = exchange.load_markets()
        # 抓取 USDT 合約，移除 1000 等特殊字眼
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and '1000' not in s]
        
        for symbol in symbols:
            try:
                # 抓取足夠的 1D 資料
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=80)
                if len(ohlcv_1d) < 40: continue
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['dt'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                # --- 模擬 TV 的 3D 分組邏輯 (1/1-1/3 為一組, 1/4 為新一組) ---
                df_1d['year'] = df_1d['dt'].dt.year
                df_1d['month'] = df_1d['dt'].dt.month
                df_1d['day'] = df_1d['dt'].dt.day
                df_1d['group'] = (df_1d['day'] - 1) // 3
                
                df_3d = df_1d.groupby(['year', 'month', 'group']).agg({
                    'dt':'first', 'high':'max', 'low':'min', 'ts':'first'
                }).sort_values('dt').reset_index(drop=True)
                
                # 1/4 號是最新的一根 (iloc[-1])
                latest_3d = df_3d.iloc[-1]
                # 前 8 根 (iloc[-9:-1]) -> 這是計算新壓力的範圍
                lookback_3d = df_3d.iloc[-9:-1]
                
                # 計算壓力位 (這 8 根 3D K 的次低點)
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price = sorted_3d.loc[1, 'low']
                p_date = sorted_3d.loc[1, 'dt'].strftime('%m/%d')

                # --- 針對 US 標的進行強制調試 ---
                clean_name = symbol.split(':')[0].replace('/USDT', '')
                if clean_name == "US":
                    us_debug_info = (f"📊 *US 數據調試 (1/4 換軌)*\n"
                                     f"新週期壓力位: `{p_price}`\n"
                                     f"壓力位來源日期: `{p_date}`\n"
                                     f"今日最高價: `{latest_3d['high']}`\n"
                                     f"當前 1D 數量: `{len(df_1d)}`")

                # 判定：最高價摸到新壓力位
                if latest_3d['high'] >= p_price:
                    ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
                    df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                    # 只看 1/4 08:00 以後的資料
                    df_1h = df_1h[df_1h['ts'] >= latest_3d['ts']].reset_index(drop=True)
                    
                    entry, sl = None, None
                    # 模擬 3H 固定區間 (08-11, 11-14...)
                    for i in range(0, len(df_1h) - 2, 3):
                        group = df_1h.iloc[i : i+3]
                        if len(group) < 3: break
                        last_bar = group.iloc[-1]
                        if last_bar['close'] > p_price:
                            entry = last_bar['close']
                            sl = group['low'].min()
                            break
                    
                    if entry:
                        display_name = clean_name
                        current_data[display_name] = f"•{display_name}\n壓力: `{p_price}`\n進場: `{entry}` / 止損: `{sl}`"
            except: continue

        # 發送調試報告
        send_telegram_msg(us_debug_info)
        
        if current_data:
            msg = "🆕 *符合 1/4 策略標的*\n\n" + "\n\n".join(current_data.values())
            send_telegram_msg(msg)
        else:
            send_telegram_msg("✅ *掃描完畢*：目前尚未有幣種滿足 3H 收盤突破新壓力位。")

    except Exception as e:
        send_telegram_msg(f"❌ 系統錯誤: `{str(e)}`")

if __name__ == "__main__":
    check_bitget_signals()
