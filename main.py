import ccxt
import pandas as pd
import requests
import time
import os
import calendar
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
    send_telegram_msg("🛡️ *1/4 策略掃描啟動...*\n(邏輯：由下往上突破，觸碰止損即刪除)")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: last_symbols = set(line.strip() for line in f.readlines())
    else: last_symbols = set()
    
    current_data = {}
    scan_count = 0

    try:
        markets = exchange.load_markets()
        # 動態獲取所有 USDT 永續合約標的
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and '1000000' not in s]
        
        for symbol in symbols:
            try:
                # 1. 3D 壓力位計算 (對齊日曆：12/29-31 或 12/30-31)
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['dt'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                def get_3d_group(row):
                    d = row['dt']
                    if d.month == 12:
                        limit = 29 if calendar.isleap(d.year) else 30
                        if d.day >= limit: return f"{d.year}-12-END"
                    return f"{d.year}-{d.month}-{(d.day-1)//3}"

                df_1d['group'] = df_1d.apply(get_3d_group, axis=1)
                df_3d = df_1d.groupby('group').agg({'dt':'first','high':'max','low':'min','ts':'first','close':'last'}).sort_values('dt').reset_index(drop=True)
                
                latest_3d_ts = df_3d.iloc[-1]['ts']
                lookback = df_3d.iloc[-9:-1] 
                p_price = lookback.sort_values('low').iloc[1]['low']
                p_date = lookback.sort_values('low').iloc[1]['dt'].strftime('%m/%d')

                # 2. 獲取 1H 與 3H 數據檢查突破與止損
                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=150)
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1h['dt'] = pd.to_datetime(df_1h['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                # 合成 3H
                df_3h = df_1h.resample('3H', on='dt', origin='start_day', offset='8h').agg({
                    'open':'first', 'high':'max', 'low':'min', 'close':'last', 'ts':'first'
                }).dropna().reset_index()

                # 取得 1/4 08:00 以後的 3H 數據
                df_3h_after = df_3h[df_3h['ts'] >= latest_3d_ts].reset_index(drop=True)
                
                has_valid_breakout = False
                sl, entry, breakout_ts = 0, 0, 0

                # 遍歷尋找：前一根 3H 收盤 <= 壓力 AND 當前 3H 收盤 > 壓力
                for i in range(1, len(df_3h_after)):
                    prev_close = df_3h_after.iloc[i-1]['close']
                    curr_close = df_3h_after.iloc[i]['close']
                    if prev_close <= p_price and curr_close > p_price:
                        has_valid_breakout = True
                        entry = curr_close
                        sl = df_3h_after.iloc[i]['low']
                        breakout_ts = df_3h_after.iloc[i]['ts']
                        break # 紀錄第一次突破
                
                # 3. 判定「碰觸止損」
                if has_valid_breakout:
                    # 檢查自突破那個 3H 區間起，到目前為止的所有 1H K線
                    # 只要任何一根 1H 的 Low < 止損價，就視為失效
                    df_check_sl = df_1h[df_1h['ts'] >= breakout_ts]
                    lowest_touch = df_check_sl['low'].min()
                    
                    if lowest_touch >= sl: # 只有最低點沒碰過止損才保留
                        display_name = symbol.split(':')[0]
                        current_data[display_name] = f"•{display_name}\n壓力: `{p_price}` ({p_date})\n突破進場: `{entry}` / 止損: `{sl}`\n當前最低: `{lowest_touch}`"
                
                scan_count += 1
            except: continue

        # --- 輸出比對 ---
        current_symbols = set(current_data.keys())
        new_s = current_symbols - last_symbols
        hold_s = current_symbols & last_symbols
        rem_s = last_symbols - current_symbols

        if not current_symbols and not rem_s:
            send_telegram_msg(f"✅ 掃描完畢 (共 {len(symbols)} 標的)\n市場目前無符合標的。")
        else:
            if new_s: send_telegram_msg("🆕 *【新增】*\n\n" + "\n\n".join([current_data[s] for s in new_s]))
            if hold_s: send_telegram_msg("💎 *【持續持有】*\n\n" + "\n\n".join([current_data[s] for s in hold_s]))
            if rem_s: send_telegram_msg("🚫 *【刪除】(觸碰止損或換軌不符)*\n\n" + "\n".join([f"• `{s}`" for s in rem_s]))

        with open(DB_FILE, "w") as f:
            for s in current_symbols: f.write(f"{s}\n")
            
    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: `{str(e)}`")

if __name__ == "__main__":
    check_bitget_signals()
