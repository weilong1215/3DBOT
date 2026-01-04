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
    except: print(f"TG 發送失敗: {message}")

def check_bitget_signals():
    start_time = time.time()
    send_telegram_msg("🚀 *啟動深度掃描...* (請稍候約 2-3 分鐘)")
    
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    current_data = {}
    
    try:
        markets = exchange.load_markets()
        # 過濾掉非 USDT 合約與股票代碼
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and '1000' not in s]
        
        count = 0
        for symbol in symbols:
            count += 1
            if count % 30 == 0: time.sleep(1.5) # 每 30 個幣休息一下
            
            try:
                # 1. 抓取 1D 資料
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=60)
                if len(ohlcv_1d) < 35: continue
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['dt'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                # 2. TV 日曆分組 (每月/每年重置)
                df_1d['year'] = df_1d['dt'].dt.year
                df_1d['month'] = df_1d['dt'].dt.month
                df_1d['group'] = (df_1d['dt'].dt.day - 1) // 3
                
                df_3d = df_1d.groupby(['year', 'month', 'group']).agg({
                    'dt':'first', 'high':'max', 'low':'min', 'ts':'first'
                }).sort_values('dt').reset_index(drop=True)
                
                latest_3d = df_3d.iloc[-1]
                lookback_3d = df_3d.iloc[-9:-1] # 前 8 根
                
                # 計算壓力 (次低點)
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price = sorted_3d.loc[1, 'low']
                
                # 3. 判定 1/4 區間是否有突破潛力
                if latest_3d['high'] >= p_price:
                    # 抓取 1H 數據進行精確檢查
                    ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
                    df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                    
                    # 只看這組 3D 區間開始後的 1H
                    df_1h = df_1h[df_1h['ts'] >= latest_3d['ts']].reset_index(drop=True)
                    
                    entry, sl = None, None
                    # 3H 模擬 (08-11, 11-14...)
                    for i in range(0, len(df_1h) - 2, 3):
                        group = df_1h.iloc[i : i+3]
                        if len(group) < 3: break
                        last_bar = group.iloc[-1] # 第三根 1H 收盤
                        
                        if last_bar['close'] > p_price:
                            entry = last_bar['close']
                            sl = group['low'].min()
                            break # 找到第一個進場點就跳出
                    
                    if entry:
                        display_name = symbol.split(':')[0]
                        current_data[display_name] = f"•{display_name}\n壓力: `{p_price}`\n進場: `{entry}` / 止損: `{sl}`"
            except: continue
        
        # --- 最終結算 ---
        duration = time.time() - start_time
        if current_data:
            msg = "🆕 *【符合策略之標的】*\n\n" + "\n\n".join(current_data.values())
            send_telegram_msg(msg)
        else:
            send_telegram_msg(f"✅ *掃描完畢*\n耗時: `{duration:.1f}s` \n目前無符合 3H 收盤突破之標的。")
            
    except Exception as e:
        send_telegram_msg(f"❌ 系統崩潰: `{str(e)}`")

if __name__ == "__main__":
    check_bitget_signals()
