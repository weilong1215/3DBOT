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

def load_last_symbols():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return set(line.strip() for line in f.readlines() if line.strip())
    return set()

def save_current_symbols(symbols):
    with open(DB_FILE, "w") as f:
        for s in symbols: f.write(f"{s}\n")

def check_bitget_signals():
    send_telegram_msg("🚀 *1/4 原始策略邏輯掃描啟動...*")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    last_symbols = load_last_symbols()
    current_data = {}

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and '1000000' not in s]
        
        for idx, symbol in enumerate(symbols):
            if idx % 50 == 0: time.sleep(1)
            try:
                # 1. 1D 資料抓取
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=60)
                if len(ohlcv_1d) < 35: continue
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['dt'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                # 2. TV 日曆分組
                df_1d['year'] = df_1d['dt'].dt.year
                df_1d['month'] = df_1d['dt'].dt.month
                df_1d['group'] = (df_1d['dt'].dt.day - 1) // 3
                df_3d = df_1d.groupby(['year', 'month', 'group']).agg({
                    'dt':'first', 'high':'max', 'low':'min', 'ts':'first', 'close':'last'
                }).reset_index(drop=True)
                
                latest_3d = df_3d.iloc[-1]
                lookback_3d = df_3d.iloc[-9:-1] # 前 8 根
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price = sorted_3d.loc[1, 'low']
                p_date = sorted_3d.loc[1, 'dt'].strftime('%m/%d')
                
                # 3. 嚴格 3H 收盤突破判定 (僅看 1/4 08:00 之後)
                if latest_3d['high'] >= p_price:
                    ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
                    df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                    df_1h = df_1h[df_1h['ts'] >= latest_3d['ts']].reset_index(drop=True)
                    
                    for i in range(0, len(df_1h) - 2, 3):
                        group = df_1h.iloc[i : i+3]
                        if len(group) < 3: break
                        # 核心邏輯：第三根 1H 收盤價必須大於壓力位
                        if group.iloc[-1]['close'] > p_price:
                            entry = group.iloc[-1]['close']
                            sl = group['low'].min()
                            display_name = symbol.split(':')[0]
                            current_data[display_name] = f"•{display_name}\n壓力: `{p_price}` ({p_date})\n進場: `{entry}` / 止損: `{sl}`"
                            break
            except: continue

        # --- 輸出比對 ---
        current_symbols = set(current_data.keys())
        new_s = current_symbols - last_symbols
        hold_s = current_symbols & last_symbols
        rem_s = last_symbols - current_symbols

        if not current_symbols and not rem_s:
            send_telegram_msg("✅ *1/4 掃描完成*：目前無標的滿足 3H 收盤突破。")
        else:
            if new_s: send_telegram_msg("🆕 *【新增】*\n\n" + "\n\n".join([current_data[s] for s in new_s]))
            if hold_s: send_telegram_msg("💎 *【持續持有】*\n\n" + "\n\n".join([current_data[s] for s in hold_s]))
            if rem_s: send_telegram_msg("🚫 *【刪除】*\n\n" + "\n".join([f"• `{s}`" for s in rem_s]))

        save_current_symbols(current_symbols)
        
    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: `{str(e)}`")

if __name__ == "__main__":
    check_bitget_signals()
