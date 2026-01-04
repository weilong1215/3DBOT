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
    start_run = time.time()
    send_telegram_msg(f"📅 *1/4 換軌掃描開始...*")
    
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    last_symbols = load_last_symbols()

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT' and s.split('/')[0] not in STOCK_SYMBOLS]
        
        pre_selected = []
        for symbol in symbols:
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=40)
                if not ohlcv_1d: continue
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                
                # 以 1/1 為基準進行 3 天分組 (台灣時間)
                df_1d['dt'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                # 計算與 2026-01-01 的天數差距，每 3 天一組
                base_date = pd.Timestamp('2026-01-01').tz_localize('Asia/Taipei')
                df_1d['group_id'] = (df_1d['dt'] - base_date).dt.days // 3
                
                df_3d = df_1d.groupby('group_id').agg({
                    'dt':'first', 'open':'first', 'high':'max', 'low':'min', 'close':'last', 'ts':'first'
                }).sort_values('dt').reset_index(drop=True)

                if len(df_3d) < 9: continue
                
                # 換軌：今天 (1/4) 屬於最新一根
                latest_3d = df_3d.iloc[-1]
                lookback_3d = df_3d.iloc[-9:-1] # 包含 1/1-1/3 那一根
                
                # 計算壓力位 (次低點)
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price = sorted_3d.loc[1, 'low']
                p_date = sorted_3d.loc[1, 'dt'].strftime('%m/%d')

                # 只要目前這組 3D 有摸到壓力位就進入 1H 檢查
                if latest_3d['high'] >= p_price:
                    pre_selected.append({'symbol': symbol, 'p_price': p_price, 'p_date': p_date, 'start_ts': latest_3d['ts']})
            except: continue

        current_data = {}
        for item in pre_selected:
            try:
                ohlcv_1h = exchange.fetch_ohlcv(item['symbol'], timeframe='1h', limit=100)
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                
                # 僅看 1/4 08:00 之後
                df_1h = df_1h[df_1h['ts'] >= item['start_ts']].reset_index(drop=True)
                if len(df_1h) < 3: continue 

                entry, sl, target, is_comp = None, None, None, False
                # 快速模擬 3H 固定區間 (不使用 resample)
                for i in range(0, len(df_1h) - 2, 3):
                    group = df_1h.iloc[i : i+3]
                    if len(group) < 3: break
                    
                    last_bar = group.iloc[-1]
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

        current_symbols = set(current_data.keys())
        new_s = current_symbols - last_symbols
        hold_s = current_symbols & last_symbols
        rem_s = last_symbols - current_symbols

        if new_s: send_telegram_msg("🆕 *【新增】*\n\n" + "\n\n".join([current_data[s] for s in new_s]))
        if hold_s: send_telegram_msg("💎 *【持有】*\n\n" + "\n\n".join([current_data[s] for s in hold_s]))
        if rem_s: send_telegram_msg("🚫 *【刪除】*\n\n" + "\n".join([f"• `{s}`" for s in rem_s]))

        save_current_symbols(current_symbols)
        # 顯示耗時
        print(f"掃描完成，耗時: {time.time() - start_run:.2f}s")
    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
