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
    send_telegram_msg("🔍 *策略掃描中...* (嚴格收盤 3H 版)")
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
                # 1D 也剔除最後一根未收盤的 K 棒
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                
                if df_1d['vol'].iloc[-1] < 5000: continue
                
                df_1d['date'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True)
                df_1d['group'] = df_1d['date'].dt.year.astype(str) + "_" + ((df_1d['date'].dt.dayofyear - 1) // 3).astype(str)
                df_3d = df_1d.groupby('group').agg({'date':'first','open':'first','high':'max','low':'min','close':'last','ts':'first'}).sort_values('date').reset_index(drop=True)
                
                if len(df_3d) < 9: continue
                latest_3d, lookback_3d = df_3d.iloc[-1], df_3d.iloc[-9:-1]
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price, p_date = sorted_3d.loc[1, 'low'], sorted_3d.loc[1, 'date'].strftime('%m/%d')

                if latest_3d['open'] < p_price and latest_3d['high'] >= p_price:
                    pre_selected.append({'symbol': symbol, 'p_price': p_price, 'p_date': p_date, 'start_ts': latest_3d['ts']})
                time.sleep(0.01)
            except: continue

        current_data = {}
        for item in pre_selected:
            try:
                time.sleep(0.3)
                ohlcv_1h = exchange.fetch_ohlcv(item['symbol'], timeframe='1h', limit=100)
                # --- 關鍵修正：剔除最後一根未收盤的 1H K 棒 ---
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                
                # 只取 3D K 棒開盤之後的資料
                df_1h = df_1h[df_1h['ts'] >= item['start_ts']].reset_index(drop=True)
                
                # 確保總數是 3 的倍數，捨棄不足 3 根的末尾
                df_1h = df_1h.iloc[: (len(df_1h) // 3) * 3]
                
                entry, sl, target, is_comp = None, None, None, False
                
                for i in range(0, len(df_1h), 3):
                    chunk = df_1h.iloc[i : i+3]
                    last_bar = chunk.iloc[-1] 
                    
                    if entry is None:
                        # 最後一根收盤 > 壓力位
                        if last_bar['close'] > item['p_price']:
                            entry = last_bar['close']
                            # 止損點：該組最後兩根(第2、3根)的最低價
                            sl = chunk.iloc[1:3]['low'].min()
                            risk = entry - sl
                            target = entry + (risk * 15) if risk > 0 else entry * 50
                    else:
                        # 監控後續 K 棒是否達標或止損
                        for _, bar in chunk.iterrows():
                            if bar['high'] >= target: is_comp = True; break
                            if bar['low'] <= sl: entry = None; break
                        if is_comp or entry is None: break
                
                if entry and not is_comp:
                    display_name = item['symbol'].split(':')[0]
                    current_data[display_name] = (
                        f"•{display_name}\n"
                        f"壓力: `{item['p_price']}` (`{item['p_date']}`)\n"
                        f"進場: `{entry:.4f}` / 止損: `{sl:.4f}`"
                    )
            except: continue

        # --- 三頁面比對與發送 (同前) ---
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
