import ccxt
import pandas as pd
import requests
import time
import os
from datetime import datetime

# --- 設定資訊 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'
DB_FILE = "last_symbols.txt" # 儲存上次結果的文件

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
            return set(line.strip() for line in f.readlines())
    return set()

def save_current_symbols(symbols):
    with open(DB_FILE, "w") as f:
        for s in symbols:
            f.write(f"{s}\n")

def check_bitget_signals():
    send_telegram_msg("🔍 *Bitget 策略掃描 (含交易量過濾與比對)...*")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    last_symbols = load_last_symbols()

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        pre_selected = []
        for symbol in symbols:
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=30)
                if len(ohlcv_1d) < 25: continue
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                
                # --- 條件 1: 交易量 > 1000 ---
                if df_1d['vol'].iloc[-1] < 1000: continue
                
                df_1d['date'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True)
                df_1d['group'] = df_1d['date'].dt.year.astype(str) + "_" + ((df_1d['date'].dt.dayofyear - 1) // 3).astype(str)
                
                df_3d = df_1d.groupby('group').agg({
                    'date':'first', 'open':'first', 'high':'max', 'low':'min', 'close':'last', 'ts':'first'
                }).sort_values('date').reset_index(drop=True)
                
                if len(df_3d) < 9: continue
                latest_3d = df_3d.iloc[-1]
                lookback_3d = df_3d.iloc[-9:-1]
                
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                pressure_p = sorted_3d.loc[1, 'low']
                pressure_d = sorted_3d.loc[1, 'date'].strftime('%m/%d')

                if latest_3d['open'] < pressure_p and latest_3d['high'] >= pressure_p:
                    pre_selected.append({
                        'symbol': symbol, 'pressure_p': pressure_p, 'pressure_d': pressure_d, 'start_ts': latest_3d['ts']
                    })
                time.sleep(0.01)
            except: continue

        # 第二階段：3H 檢查
        current_data = {} # 儲存當前符合的所有詳細資訊
        for item in pre_selected:
            try:
                time.sleep(0.3)
                ohlcv_1h = exchange.fetch_ohlcv(item['symbol'], timeframe='1h', limit=80)
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1h = df_1h[df_1h['ts'] >= item['start_ts']].reset_index(drop=True)
                
                # 封裝 3H
                custom_3h = []
                for i in range(0, len(df_1h), 3):
                    chunk = df_1h.iloc[i : i+3]
                    if chunk.empty: break
                    custom_3h.append({'open': chunk.iloc[0]['open'], 'high': chunk['high'].max(), 'low': chunk['low'].min(), 'close': chunk.iloc[-1]['close']})
                
                entry_p, sl, target_p, is_comp = None, None, None, False
                for bar in custom_3h:
                    if entry_p is None:
                        if bar['close'] > item['pressure_p']:
                            entry_p = bar['close']; sl = bar['low']; risk = entry_p - sl
                            target_p = entry_p + (risk * 2) if risk > 0 else entry_p * 10
                    else:
                        if bar['high'] >= target_p: is_comp = True; break
                        if bar['low'] <= sl: entry_p = None # 止損重置
                
                if entry_p and not is_comp:
                    clean_name = item['symbol'].split(':')[0]
                    current_data[clean_name] = f"• `{clean_name:10}`\n  壓力: `{item['pressure_p']}` / 進場: `{entry_p:.4f}`"
            except: continue

        # --- 比對邏輯 ---
        current_symbols = set(current_data.keys())
        new_symbols = current_symbols - last_symbols
        holding_symbols = current_symbols & last_symbols
        removed_symbols = last_symbols - current_symbols

        # --- 發送訊息 ---
        if new_symbols:
            msg = "🆕 *【頁面 1: 本次新增】*\n\n" + "\n".join([current_data[s] for s in new_symbols])
            send_telegram_msg(msg)
        
        if holding_symbols:
            msg = "💎 *【頁面 2: 持續持有】*\n\n" + "\n".join([current_data[s] for s in holding_symbols])
            send_telegram_msg(msg)

        if removed_symbols:
            msg = "🚫 *【頁面 3: 本次刪除】*\n\n" + "\n".join([f"• `{s:10}` (達標/止損/不符)" for s in removed_symbols])
            send_telegram_msg(msg)

        if not current_symbols and not removed_symbols:
            send_telegram_msg("⚠️ 目前清單為空。")

        # 儲存本次結果供下次使用
        save_current_symbols(current_symbols)

    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
