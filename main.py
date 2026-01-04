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
    send_telegram_msg("🔍 *正在進行 1/4 邏輯掃描...* (必須從下往上突破)")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: last_symbols = set(line.strip() for line in f.readlines())
    else: last_symbols = set()
    
    current_data = {}
    scan_count = 0

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and '1000000' not in s]
        
        for symbol in symbols:
            try:
                # 1. 3D 壓力位計算
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

                # 2. 獲取 3H 數據
                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=150)
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1h['dt'] = pd.to_datetime(df_1h['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                # 強制對齊 08:00 合成 3H
                df_3h = df_1h.resample('3H', on='dt', origin='start_day', offset='8h').agg({
                    'open':'first', 'high':'max', 'low':'min', 'close':'last', 'ts':'first'
                }).dropna().reset_index()

                df_after = df_3h[df_3h['ts'] >= latest_3d_ts].reset_index(drop=True)
                
                has_valid_breakout = False
                sl, entry = 0, 0

                # 遍歷：必須前一根 <= 壓力，這根 > 壓力
                for i in range(1, len(df_after)):
                    prev_close = df_after.iloc[i-1]['close']
                    curr_close = df_after.iloc[i]['close']
                    if prev_close <= p_price and curr_close > p_price:
                        has_valid_breakout = True
                        entry = curr_close
                        sl = df_after.iloc[i]['low']
                        break
                
                if has_valid_breakout:
                    current_price = df_1h.iloc[-1]['close']
                    if current_price >= sl:
                        display_name = symbol.split(':')[0]
                        current_data[display_name] = f"•{display_name}\n壓力: `{p_price}` ({p_date})\n突破進場: `{entry}` / 止損: `{sl}`"
                
                scan_count += 1
            except: continue

        # --- 輸出邏輯 ---
        current_symbols = set(current_data.keys())
        new_s = current_symbols - last_symbols
        hold_s = current_symbols & last_symbols
        rem_s = last_symbols - current_symbols

        if not current_symbols and not rem_s:
            send_telegram_msg(f"✅ 掃描完畢 (共 {scan_count} 標的)\n目前市場無符合「由下往上突破」且「未止損」的幣。")
        else:
            if new_s: send_telegram_msg("🆕 *【新增】*\n\n" + "\n\n".join([current_data[s] for s in new_s]))
            if hold_s: send_telegram_msg("💎 *【持續持有】*\n\n" + "\n\n".join([current_data[s] for s in hold_s]))
            if rem_s: send_telegram_msg("🚫 *【刪除】*\n\n" + "\n".join([f"• `{s}`" for s in rem_s]))

        with open(DB_FILE, "w") as f:
            for s in current_symbols: f.write(f"{s}\n")
            
    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: `{str(e)}`")

if __name__ == "__main__":
    check_bitget_signals()
