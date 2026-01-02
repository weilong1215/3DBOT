import ccxt
import pandas as pd
import requests
import time
from datetime import datetime

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
    send_telegram_msg("🔍 *Bitget 3D+3H 策略掃描 (僅顯示進行中)...*")
    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('type') == 'swap' and m.get('quote') == 'USDT']
        
        pre_selected = []
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
                        'symbol': symbol, 'pressure_p': pressure_p, 'pressure_d': pressure_d, 'start_ts': latest_3d['ts']
                    })
                time.sleep(0.01)
            except:
                continue

        if pre_selected:
            time.sleep(2)

        hit_symbols = []
        for item in pre_selected:
            try:
                time.sleep(0.3)
                # 抓取 1H 數據封裝 3H
                ohlcv_1h = exchange.fetch_ohlcv(item['symbol'], timeframe='1h', limit=80)
                if not ohlcv_1h: continue
                
                df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1h = df_1h[df_1h['ts'] >= item['start_ts']].reset_index(drop=True)
                
                custom_3h_list = []
                for i in range(0, len(df_1h), 3):
                    chunk = df_1h.iloc[i : i + 3]
                    if chunk.empty: break
                    custom_3h_list.append({
                        'open': chunk.iloc[0]['open'],
                        'high': chunk['high'].max(),
                        'low': chunk['low'].min(),
                        'close': chunk.iloc[-1]['close']
                    })
                
                entry_price = None
                is_completed = False
                
                for bar in custom_3h_list:
                    if entry_price is None:
                        # 條件：3H 收盤必須大於壓力
                        if bar['close'] > item['pressure_p']:
                            entry_price = bar['close']
                            stop_loss = bar['low']
                            risk = entry_price - stop_loss
                            target_p = entry_price + (risk * 2) if risk > 0 else entry_price * 10
                    else:
                        # 檢查是否已達成 1:2
                        if bar['high'] >= target_p:
                            is_completed = True
                            break
                
                # 最終篩選：必須已進場，且尚未達成 1:2
                if entry_price and not is_completed:
                    clean_name = item['symbol'].split(':')[0]
                    hit_symbols.append(
                        f"• `{clean_name:10}` (進行中)\n"
                        f"  壓力: `{item['pressure_p']}` (`{item['pressure_d']}`)\n"
                        f"  進場: `{entry_price:.4f}` / 止損: `{stop_loss:.4f}`"
                    )
            except:
                continue

        if hit_symbols:
            for i in range(0, len(hit_symbols), 25):
                msg = "✅ *3D+3H 進行中品種 (排除已達 1:2):*\n\n" + "\n".join(hit_symbols[i:i + 25])
                send_telegram_msg(msg)
                time.sleep(1)
        else:
            send_telegram_msg("⚠️ 目前無符合進場條件之品種。")

    except Exception as e:
        send_telegram_msg(f"❌ 嚴重錯誤: {str(e)}")

if __name__ == "__main__":
    check_bitget_signals()
