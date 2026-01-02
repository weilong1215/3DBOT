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
    try:
        requests.post(url, json=payload, timeout=20)
    except:
        pass

def load_last_symbols():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    return set()

def save_current_symbols(symbols):
    with open(DB_FILE, "w") as f:
        for s in symbols:
            f.write(f"{s}\n")

def check_bitget_signals():
    send_telegram_msg("🔍 *策略掃描中...* (開盤/每3小時排程)")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    last_symbols = load_last_symbols()

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        # 第一階段：3D 篩選
        pre_selected = []
        for symbol in symbols:
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=30)
                if not ohlcv_1d: continue
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                
                # 條件：24H交易量 > 1000 USDT
                if df_1d['vol'].iloc[-1] < 1000: continue
                
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

        # 第二階段：1H 轉 3H 深度檢查
        current_data = {}
        for item in pre_selected:
            try:
                time.sleep(0.3)
                ohlcv_1h = exchange.fetch_ohlcv(item['symbol'], timeframe='1h', limit=80)
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1h = df_1h[df_1h['ts'] >= item['start_ts']].reset_index(drop=True)
                
                custom_3h = []
                for i in range(0, len(df_1h), 3):
                    chunk = df_1h.iloc[i:i+3]
                    if chunk.empty: break
                    custom_3h.append({'open': chunk.iloc[0]['open'], 'high': chunk['high'].max(), 'low': chunk['low'].min(), 'close': chunk.iloc[-1]['close']})
                
                entry, sl, target, is_comp = None, None, None, False
                for bar in custom_3h:
                    if entry is None:
                        if bar['close'] > item['p_price']:
                            entry, sl = bar['close'], bar['low']
                            target = entry + ((entry - sl) * 2) if entry > sl else entry * 10
                    else:
                        if bar['high'] >= target: is_comp = True; break
                        if bar['low'] <= sl: entry = None # 觸碰止損重置
                
                if entry and not is_comp:
                    clean_name = item['symbol'].split(':')[0]
                    current_data[clean_name] = f"•`{clean_name}`/壓力: `{item['p_price']}` (`{item['p_date']}`)\n  進場: `{entry:.4f}` / 止損: `{sl:.4f}`"
            except: continue

        # --- 三頁面比對邏輯 ---
        current_symbols = set(current_data.keys())
        new_s = current_symbols - last_symbols
        hold_s = current_symbols & last_symbols
        rem_s = last_symbols - current_symbols

        if new_s:
            send_telegram_msg("🆕 *【頁面 1: 新增訊號】*\n\n" + "\n".join([current_data[s] for s in new_s]))
        
        if hold_s:
            send_telegram_msg("💎 *【頁面 2: 持續持有】*\n\n" + "\n".join([current_data[s] for s in hold_s]))

        if rem_s:
            send_telegram_msg("🚫 *【頁面 3: 本次刪除】*\n(已達標/已止損/條件消失)\n\n" + "\n".join([f"• `{s}`" for s in rem_s]))

        save_current_symbols(current_symbols)
    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
