import ccxt
import pandas as pd
import requests
import time
import os
from datetime import datetime, timedelta

# --- 使用您的設定 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'
DB_FILE = os.path.join(os.getcwd(), "last_symbols.txt")

STOCK_SYMBOLS = ['AAPL', 'TSLA', 'NVDA', 'AMZN', 'MSFT', 'GOOGL', 'META', 'NFLX', 'BABA', 'COIN', 'MSTR', 'AMD', 'PYPL', 'DIS', 'NKE', 'INTC', 'V', 'MA', 'UBER', 'LYFT', 'SHOP', 'GME', 'AMC', 'PLTR', 'SNOW']

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
    send_telegram_msg(f"📅 *TV 日曆對齊掃描開始* (1/4 新週期)")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    last_symbols = load_last_symbols()

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT' and s.split('/')[0] not in STOCK_SYMBOLS]
        
        pre_selected = []
        for symbol in symbols:
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=60)
                if not ohlcv_1d: continue
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['dt'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                # --- 關鍵修正：模擬 TV 的 3D 分組 (每月/每年重置) ---
                # 邏輯：每個月的 1-3, 4-6... 28-30, 31 是一組
                df_1d['year'] = df_1d['dt'].dt.year
                df_1d['month'] = df_1d['dt'].dt.month
                df_1d['group_in_month'] = (df_1d['dt'].dt.day - 1) // 3
                
                df_3d = df_1d.groupby(['year', 'month', 'group_in_month']).agg({
                    'dt':'first', 'open':'first', 'high':'max', 'low':'min', 'close':'last', 'ts':'first'
                }).sort_values('dt').reset_index(drop=True)

                if len(df_3d) < 10: continue
                
                # latest_3d 就是 1/4 開始的這一組
                latest_3d = df_3d.iloc[-1]
                # lookback_3d 就是包含 TV 上 12/30-31、1/1-1/3 這些特定分組的前 8 根
                lookback_3d = df_3d.iloc[-9:-1]
                
                # 計算壓力位 (次低點)
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price = sorted_3d.loc[1, 'low']
                p_date = sorted_3d.loc[1, 'dt'].strftime('%m/%d')

                # 判定
                if latest_3d['high'] >= p_price:
                    pre_selected.append({'symbol': symbol, 'p_price': p_price, 'p_date': p_date, 'start_ts': latest_3d['ts']})
            except: continue

        current_data = {}
        for item in pre_selected:
            try:
                ohlcv_1h = exchange.fetch_ohlcv(item['symbol'], timeframe='1h', limit=100)
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                
                # 僅看當前 3D 週期起點（1/4 08:00）之後
                df_1h = df_1h[df_1h['ts'] >= item['start_ts']].reset_index(drop=True)

                # 模擬 3H 區間 (08-11, 11-14, 14-17...)
                # 注意：Bitget 1H K棒的 TS 是開盤時間，所以 08, 09, 10 這三根算一組
                entry, sl, target, is_comp = None, None, None, False
                for i in range(0, len(df_1h) - 2, 3):
                    group = df_1h.iloc[i : i+3]
                    if len(group) < 3: break
                    
                    last_bar = group.iloc[-1] # 第 3 根 1H
                    if entry is None:
                        if last_bar['close'] > item['p_price']:
                            entry = last_bar['close']
                            sl = group['low'].min()
                            target = entry + ((entry - sl) * 15) if entry > sl else entry * 50
                    else:
                        for _, bar in group.iterrows():
                            if bar['high'] >= target: is_comp = True; break
                            if bar['low'] <= sl: entry = None; break
                        if is_comp or entry is None: break
                
                if entry and not is_comp:
                    display_name = item['symbol'].split(':')[0]
                    current_data[display_name] = f"•{display_name}\n壓力: `{item['p_price']}` (`{item['p_date']}`)\n進場: `{entry}` / 止損: `{sl}`"
            except: continue

        # 輸出結果
        current_symbols = set(current_data.keys())
        new_s = current_symbols - last_symbols
        hold_s = current_symbols & last_symbols
        rem_s = last_symbols - current_symbols

        if new_s: send_telegram_msg("🆕 *【新增】*\n\n" + "\n\n".join([current_data[s] for s in new_s]))
        if hold_s: send_telegram_msg("💎 *【持有】*\n\n" + "\n\n".join([current_data[s] for s in hold_s]))
        if rem_s: send_telegram_msg("🚫 *【刪除】*\n\n" + "\n".join([f"• `{s}`" for s in rem_s]))

        save_current_symbols(current_symbols)
    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
