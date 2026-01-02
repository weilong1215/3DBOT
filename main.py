import ccxt
import pandas as pd
import requests
import time
from datetime import datetime, timezone

# --- 設定資訊 ---
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
    send_telegram_msg("🔍 *Bitget 3D 壓力監控 (高成功率修正版)...*")
    # 開啟自動頻率限制
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        hit_symbols = []
        for symbol in symbols:
            try:
                # 1. 抓取日K封裝 3D (抓 30 根夠 9 根 3D)
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=30)
                if len(ohlcv_1d) < 25: continue

                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['date'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True)
                df_1d['group'] = df_1d['date'].dt.year.astype(str) + "_" + ((df_1d['date'].dt.dayofyear - 1) // 3).astype(str)
                
                df_3d = df_1d.groupby('group').agg({
                    'date':'first', 'open':'first', 'high':'max', 'low':'min', 'close':'last', 'ts':'first'
                }).sort_values('date').reset_index(drop=True)
                
                # 確保有足夠 3D 數據
                if len(df_3d) < 9: continue
                latest_3d = df_3d.iloc[-1]
                lookback_3d = df_3d.iloc[-9:-1] # 過去 8 根
                
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                pressure_p = sorted_3d.loc[1, 'low']
                pressure_d = sorted_3d.loc[1, 'date'].strftime('%m/%d')

                # 主條件判斷
                if not (latest_3d['open'] < pressure_p and latest_3d['high'] >= pressure_p):
                    continue

                # --- 3H 過濾邏輯 (僅在符合 3D 條件時執行) ---
                status_tag = " (尚未進場)"
                ohlcv_3h = None
                
                # 嘗試抓取 3H 數據，若失敗重試一次
                for retry in range(2):
                    try:
                        time.sleep(0.3) # 強制喘息
                        ohlcv_3h = exchange.fetch_ohlcv(symbol, timeframe='3h', limit=24)
                        if ohlcv_3h: break
                    except:
                        time.sleep(1) # 失敗後等更久
                
                if ohlcv_3h:
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
                    
                    if entry_price and status_tag != " (已抵達)":
                        status_tag = " (進行中)"
                else:
                    status_tag = " (跳過3H檢查)"

                clean_name = symbol.split(':')[0]
                hit_symbols.append(
                    f"• `{clean_name:10}`{status_tag}\n"
                    f"  壓力: `{pressure_p}` (`{pressure_d}`)"
                )
                
            except:
                continue

        if hit_symbols:
            # 優先顯示尚未進場與進行中
            hit_symbols.sort(key=lambda x: ("已抵達" in x or "跳過" in x))
            for i in range(0, len(hit_symbols), 25):
                msg = "✅ *3D 壓力監控結果 (數據最小化版):*\n\n" + "\n".join(hit_symbols[i:i + 25])
                send_telegram_msg(msg)
                time.sleep(1)
        else:
            send_telegram_msg("⚠️ 目前無符合觸碰壓力條件之品種。")

    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
