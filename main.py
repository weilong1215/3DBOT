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
    send_telegram_msg("🔍 *Bitget 3D 壓力監控 (優化穩定版)...*")
    # 開啟 enableRateLimit 讓 CCXT 自動處理頻率限制
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        hit_symbols = []
        for symbol in symbols:
            try:
                # 1. 抓取日K封裝 3D
                # 只需要過去 45 天數據 (limit=45 夠了)
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=45)
                if len(ohlcv_1d) < 30: continue # 數據太少的新幣跳過

                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['date'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True)
                df_1d['group'] = df_1d['date'].dt.year.astype(str) + "_" + ((df_1d['date'].dt.dayofyear - 1) // 3).astype(str)
                
                df_3d = df_1d.groupby('group').agg({
                    'date':'first', 'open':'first', 'high':'max', 'low':'min', 'close':'last', 'ts':'first'
                }).sort_values('date').reset_index(drop=True)
                
                latest_3d = df_3d.iloc[-1]
                lookback_3d = df_3d.iloc[-9:-1]
                if len(lookback_3d) < 8: continue
                
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                pressure_p = sorted_3d.loc[1, 'low']
                pressure_d = sorted_3d.loc[1, 'date'].strftime('%m/%d')

                # 主條件：開盤 < 壓力 且 最高 >= 壓力
                if not (latest_3d['open'] < pressure_p and latest_3d['high'] >= pressure_p):
                    continue

                # --- 3H 過濾邏輯 ---
                status_tag = " (尚未進場)" 
                try:
                    # 增加延遲避免被封鎖
                    time.sleep(0.2) 
                    # 3H 只需要抓最近 3 天的，大約 24 根就夠
                    ohlcv_3h = exchange.fetch_ohlcv(symbol, timeframe='3h', limit=30)
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
                except Exception as e:
                    print(f"3H數據抓取失敗 {symbol}: {e}")
                    status_tag = " (掃描超時)"

                clean_name = symbol.split(':')[0]
                hit_symbols.append(
                    f"• `{clean_name:10}`{status_tag}\n"
                    f"  壓力: `{pressure_p}` (`{pressure_d}`)"
                )
                
            except:
                continue

        if hit_symbols:
            # 將尚未進場的排在最前面
            hit_symbols.sort(key=lambda x: ("尚未進場" not in x))
            for i in range(0, len(hit_symbols), 25):
                msg = "✅ *3D 壓力監控結果 (穩定版):*\n\n" + "\n".join(hit_symbols[i:i + 25])
                send_telegram_msg(msg)
                time.sleep(1)
        else:
            send_telegram_msg("⚠️ 目前無符合觸碰壓力條件之品種。")

    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
