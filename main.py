import ccxt
import pandas as pd
import requests
import time
import os
from datetime import datetime, timedelta

# --- 設定資訊 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'
DB_FILE = os.path.join(os.getcwd(), "last_symbols.txt")

STOCK_SYMBOLS = ['AAPL', 'TSLA', 'NVDA', 'AMZN', 'MSFT', 'GOOGL', 'META', 'NFLX', 'BABA', 'COIN', 'MSTR', 'AMD', 'PYPL', 'DIS', 'NKE', 'INTC', 'V', 'MA', 'UBER', 'LYFT', 'SHOP', 'GME', 'AMC', 'PLTR', 'SNOW']

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=20)
    except: pass

def load_last_symbols():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    return set()

def save_current_symbols(symbols):
    with open(DB_FILE, "w") as f:
        for s in symbols: f.write(f"{s}\n")

def check_bitget_signals():
    send_telegram_msg("🔍 *策略掃描中...* (原始價格精準版)")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    last_symbols = load_last_symbols()

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT' and s.split('/')[0] not in STOCK_SYMBOLS]
        
        pre_selected = []
        for symbol in symbols:
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=31)
                if not ohlcv_1d: continue
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                if df_1d['vol'].iloc[-1] < 5000: continue
                
                df_1d['date'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True)
                df_1d['group'] = df_1d['date'].dt.year.astype(str) + "_" + ((df_1d['date'].dt.dayofyear - 1) // 3).astype(str)
                df_3d = df_1d.groupby('group').agg({'date':'first','open':'first','high':'max','low':'min','close':'last','ts':'first'}).sort_values('date').reset_index(drop=True)
                
                if len(df_3d) < 9: continue
                latest_3d = df_3d.iloc[-1]
                lookback_3d = df_3d.iloc[-9:-1]
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price = sorted_3d.loc[1, 'low']
                p_date = sorted_3d.loc[1, 'date'].strftime('%m/%d')

                if latest_3d['open'] < p_price and latest_3d['high'] >= p_price:
                    pre_selected.append({'symbol': symbol, 'p_price': p_price, 'p_date': p_date, 'start_ts': latest_3d['ts']})
                time.sleep(0.01)
            except: continue

        current_data = {}
        for item in pre_selected:
            try:
                time.sleep(0.3)
                ohlcv_1h = exchange.fetch_ohlcv(item['symbol'], timeframe='1h', limit=150)
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                
                df_1h['dt'] = pd.to_datetime(df_1h['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                start_dt = pd.to_datetime(item['start_ts'], unit='ms', utc=True).tz_convert('Asia/Taipei')
                df_1h = df_1h[df_1h['dt'] >= start_dt].reset_index(drop=True)

                df_1h.set_index('dt', inplace=True)
                # 固定台灣時間 08:00 開始每 3 小時一組
                resampler = df_1h.resample('3H', origin='start_day', offset='8h')
                
                entry, sl, target, is_comp = None, None, None, False
                
                for label, group in resampler:
                    if len(group) < 3: continue 
                    
                    last_bar = group.iloc[-1]
                    
                    if entry is None:
                        if last_bar['close'] > item['p_price']:
                            entry = last_bar['close']
                            sl = group['low'].min()
                            risk = entry - sl
                            # 1:15 目標
                            target = entry + (risk * 15) if risk > 0 else entry * 50
                    else:
                        for _, bar in group.iterrows():
                            if bar['high'] >= target: is_comp = True; break
                            if bar['low'] <= sl: entry = None; break
                        if is_comp or entry is None: break
                
                if entry and not is_comp:
                    display_name = item['symbol'].split(':')[0]
                    # 修改：移除 :.4f，使用原始數值，避免四捨五入
                    current_data[display_name] = (
                        f"•{display_name}\n"
                        f"壓力: `{item['p_price']}` (`{item['p_date']}`)\n"
                        f"進場: `{entry}` / 止損: `{sl}`"
                    )
            except: continue

        current_symbols = set(current_data.keys())
        new_s = current_symbols - last_symbols
        hold_s = current_symbols & last_symbols
        rem_s = last_symbols - current_symbols

        if new_s: send_telegram_msg("🆕 *【頁面 1: 新增訊號】*\n\n" + "\n\n".join([current_data[s] for s in new_s]))
        if hold_s: send_telegram_msg("💎 *【頁面 2: 持續持有】*\n\n" + "\n\n".join([current_data[s] for s in hold_s]))
        if rem_s: send_telegram_msg("🚫 *【頁面 3: 本次刪除】*\n\n" + "\n".join([f"• `{s}`" for s in rem_s]))

        save_current_symbols(current_symbols)
    except Exception as e: send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
