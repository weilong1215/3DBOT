import ccxt
import pandas as pd
import requests
import time
import os
from datetime import datetime

# --- 設定資訊 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload, timeout=20)
    except: pass

def check_bitget_signals():
    send_telegram_msg("🔄 *1/4 深度掃描啟動...* (對齊 TV 日曆與 US 標的)")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    current_data = {}
    found_us = False

    try:
        markets = exchange.load_markets()
        # 抓取所有 USDT 合約標的
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and '1000' not in s]
        
        for symbol in symbols:
            try:
                # 為了計算 3D，抓取足夠多的 1D 資料
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                if len(ohlcv_1d) < 40: continue
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['dt'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                # --- 核心邏輯：TV 日曆分組 (12/30-31 獨立, 1/1-1/3 獨立, 1/4 開始新一組) ---
                df_1d['year'] = df_1d['dt'].dt.year
                df_1d['month'] = df_1d['dt'].dt.month
                df_1d['group'] = (df_1d['dt'].dt.day - 1) // 3
                
                # 建立 3D 資料集
                df_3d = df_1d.groupby(['year', 'month', 'group']).agg({
                    'dt':'first', 'high':'max', 'low':'min', 'ts':'first'
                }).sort_values('dt').reset_index(drop=True)
                
                # 最新的一根是 1/4 開始的這週期
                latest_3d = df_3d.iloc[-1]
                # 往前數 8 根作壓力位池 (包含 1/1-1/3, 12/30-31 等)
                lookback_3d = df_3d.iloc[-9:-1]
                
                if len(lookback_3d) < 8: continue
                
                # 計算壓力位 (次低點)
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price = sorted_3d.loc[1, 'low']
                p_date = sorted_3d.loc[1, 'dt'].strftime('%m/%d')

                # 名稱比對 (針對 US 標的)
                clean_name = symbol.split(':')[0].replace('/USDT', '')
                if "US" == clean_name:
                    found_us = True
                    # 強制回報 US 目前的計算狀態，即便不符合也會報
                    send_telegram_msg(f"📊 *US 實時監測*\n計算壓力位: `{p_price}`\n今日最高: `{latest_3d['high']}`\n1/4 週期起點: `{latest_3d['dt'].strftime('%m/%d %H:%M')}`")

                # 條件 1: 最高價摸過壓力
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
                        current_data[clean_name] = f"•{clean_name}\n壓力: `{p_price}` ({p_date})\n進場: `{entry}` / 止損: `{sl}`"
            except: continue

        # --- 輸出結果 ---
        if not found_us:
            send_telegram_msg("⚠️ 掃描中未發現名為 'US' 的合約標的，請檢查交易所代碼。")

        if current_data:
            msg = "🆕 *【1/4 符合標的】*\n\n" + "\n\n".join(current_data.values())
            send_telegram_msg(msg)
        else:
            send_telegram_msg("✅ *掃描完畢*：目前尚未有幣種滿足 3H 收盤突破新壓力位。")

    except Exception as e:
        send_telegram_msg(f"❌ 系統錯誤: `{str(e)}`")

if __name__ == "__main__":
    check_bitget_signals()
