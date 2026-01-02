import ccxt
import pandas as pd
import requests
import time
from datetime import datetime, timezone

# --- 設定資訊 ---
# 已從您的記憶中讀取 TELEGRAM_TOKEN 與 TELEGRAM_CHAT_ID
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=20)
    except:
        pass

def check_bitget_signals():
    send_telegram_msg("🔍 *Bitget 3D 壓力監控 (含 1:2 過濾標註)...*")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        hit_symbols = []
        for symbol in symbols:
            try:
                # 1. 抓取日K並手動封裝 3D (1/1 重啟邏輯)
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=60)
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['date'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True)
                df_1d['group'] = df_1d['year'] = df_1d['date'].dt.year.astype(str) + "_" + ((df_1d['date'].dt.dayofyear - 1) // 3).astype(str)
                
                df_3d = df_1d.groupby('group').agg({
                    'date':'first', 'open':'first', 'high':'max', 'low':'min', 'close':'last', 'ts':'first'
                }).sort_values('date').reset_index(drop=True)
                
                if len(df_3d) < 10: continue
                latest_3d = df_3d.iloc[-1]
                
                # 壓力位 (過去8根之二低)
                lookback_3d = df_3d.iloc[-9:-1]
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                pressure_p = sorted_3d.loc[1, 'low']
                pressure_d = sorted_3d.loc[1, 'date'].strftime('%m/%d')

                # --- 核心主條件 (不符合則直接跳過此幣) ---
                if not (latest_3d['open'] < pressure_p and latest_3d['high'] >= pressure_p):
                    continue

                # --- 輔助標註邏輯 (3H 過濾) ---
                status_tag = "" 
                try:
                    ohlcv_3h = exchange.fetch_ohlcv(symbol, timeframe='3h', limit=40)
                    df_3h = pd.DataFrame(ohlcv_3h, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                    current_3h_set = df_3h[df_3h['ts'] >= latest_3d['ts']].copy()

                    entry_price = None
                    for _, row in current_3h_set.iterrows():
                        if entry_price is None:
                            if row['close'] > pressure_p:
                                entry_price = row['close']
                                stop_loss = row['low']
                                risk = entry_price - stop_loss
                                target_p = entry_price + (risk * 2) if risk > 0 else entry_price * 10
                        else:
                            if row['high'] >= target_p:
                                status_tag = " (已抵達)"
                                break
                    
                    if entry_price and status_tag == "":
                        status_tag = " (進行中)"
                    elif entry_price is None:
                        status_tag = " (尚未進場)"
                except:
                    status_tag = " (數據不足)"

                # --- 格式化訊息 ---
                clean_name = symbol.split(':')[0]
                hit_symbols.append(
                    f"• `{clean_name:10}`{status_tag}\n"
                    f"  壓力: `{pressure_p}` (`{pressure_d}`)"
                )
                time.sleep(0.05)
            except:
                continue

        if hit_symbols:
            for i in range(0, len(hit_symbols), 25):
                msg = "✅ *3D 壓力觸碰全清單 (1/1 起算):*\n\n" + "\n".join(hit_symbols[i:i + 25])
                send_telegram_msg(msg)
                time.sleep(1)
        else:
            send_telegram_msg("⚠️ 目前無符合觸碰壓力條件之品種。")

    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
