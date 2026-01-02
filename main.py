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
    send_telegram_msg("🔍 *Bitget 兩階段精確掃描中...*")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        # 第一階段：初步篩選 3D 符合的幣種
        pre_selected = []
        print(f"開始第一階段掃描，總共 {len(symbols)} 個幣種...")
        
        for symbol in symbols:
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=30)
                if len(ohlcv_1d) < 25: continue
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
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

                # 3D 基礎條件：開盤 < 壓力 且 最高 >= 壓力
                if latest_3d['open'] < pressure_p and latest_3d['high'] >= pressure_p:
                    pre_selected.append({
                        'symbol': symbol,
                        'pressure_p': pressure_p,
                        'pressure_d': pressure_d,
                        'start_ts': latest_3d['ts']
                    })
                
                time.sleep(0.05) # 日K掃描很快，稍微停頓即可
            except:
                continue

        # 第二階段：只針對符合的幣種進行 3H 深度檢查
        print(f"第一階段完成，共有 {len(pre_selected)} 個幣種符合 3D 條件。開始檢查 3H...")
        hit_symbols = []
        
        for item in pre_selected:
            status_tag = " (尚未進場)"
            try:
                # 這裡增加較長的延遲，因為剩下的幣不多了，不需要趕時間
                time.sleep(0.5) 
                ohlcv_3h = exchange.fetch_ohlcv(item['symbol'], timeframe='3h', limit=24)
                
                if ohlcv_3h:
                    df_3h = pd.DataFrame(ohlcv_3h, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                    current_3h_set = df_3h[df_3h['ts'] >= item['start_ts']].copy()

                    entry_price = None
                    for _, row in current_3h_set.iterrows():
                        if entry_price is None:
                            if row['close'] > item['pressure_p']:
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
                
                clean_name = item['symbol'].split(':')[0]
                hit_symbols.append(
                    f"• `{clean_name:10}`{status_tag}\n"
                    f"  壓力: `{item['pressure_p']}` (`{item['pressure_d']}`)"
                )
            except Exception as e:
                # 若 3H 還是掛了，至少保留 3D 結果
                clean_name = item['symbol'].split(':')[0]
                hit_symbols.append(f"• `{clean_name:10}` (3H數據獲取失敗)\n  壓力: `{item['pressure_p']}`")

        # 最後彙整訊息
        if hit_symbols:
            hit_symbols.sort(key=lambda x: ("已抵達" in x))
            for i in range(0, len(hit_symbols), 25):
                msg = "✅ *3D 壓力監控結果 (兩階段掃描版):*\n\n" + "\n".join(hit_symbols[i:i + 25])
                send_telegram_msg(msg)
                time.sleep(1)
        else:
            send_telegram_msg("⚠️ 目前無符合條件之品種。")

    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
