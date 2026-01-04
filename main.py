import ccxt
import pandas as pd
import requests
import time
import os
import calendar  # 用於判定閏年

# --- 設定資訊 ---
TELEGRAM_TOKEN = '你的_TOKEN'
TELEGRAM_CHAT_ID = '你的_CHAT_ID'
DB_FILE = os.path.join(os.getcwd(), "last_symbols.txt")

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload, timeout=20)
    except: pass

def check_bitget_signals():
    # 獲取當前年份，判定是否為閏年
    current_year = 2026 # 模擬當前時間，實作中可用 datetime.now().year
    is_leap = calendar.isleap(current_year - 1) # 檢查剛過完的那個 12 月所屬年份
    
    msg_header = "📅 *1/4 智能校準啟動*"
    msg_header += f"\n(判定去年是否為閏年: {'是' if is_leap else '否'})"
    send_telegram_msg(msg_header)

    exchange = ccxt.bitget({'timeout': 30000, 'enableRateLimit': True})
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: last_symbols = set(line.strip() for line in f.readlines())
    else: last_symbols = set()
    
    current_data = {}

    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and '1000000' not in s]
        
        for idx, symbol in enumerate(symbols):
            if idx % 50 == 0: time.sleep(1)
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                df_1d = pd.DataFrame(ohlcv_1d, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                df_1d['dt'] = pd.to_datetime(df_1d['ts'], unit='ms', utc=True).dt.tz_convert('Asia/Taipei')
                
                # --- 智能分組邏輯：根據閏年自動調整年底 ---
                def get_group_id(row):
                    dt = row['dt']
                    # 如果是 12 月
                    if dt.month == 12:
                        # 閏年判斷：12/29-31 為一根
                        if calendar.isleap(dt.year) and dt.day >= 29:
                            return f"{dt.year}-12-LAST"
                        # 非閏年判斷：12/30-31 為一根
                        if not calendar.isleap(dt.year) and dt.day >= 30:
                            return f"{dt.year}-12-LAST"
                    
                    # 1/1 之後重新開始 3 天一組
                    return f"{dt.year}-{dt.month}-{(dt.day-1)//3}"

                df_1d['group'] = df_1d.apply(get_group_id, axis=1)
                
                # 合成 3D K 棒
                df_3d = df_1d.groupby('group').agg({
                    'dt':'first', 'high':'max', 'low':'min', 'ts':'first', 'close':'last'
                }).sort_values('dt').reset_index(drop=True)
                
                # 壓力位計算 (包含 1/1-1/3 的最新已收盤 K 棒，往回數 8 根)
                latest_3d = df_3d.iloc[-1]
                lookback_3d = df_3d.iloc[-9:-1]
                
                if len(lookback_3d) < 8: continue
                
                sorted_3d = lookback_3d.sort_values(by='low').reset_index(drop=True)
                p_price = sorted_3d.loc[1, 'low']
                p_date = sorted_3d.loc[1, 'dt'].strftime('%m/%d')
                
                # --- 策略判定 (1/4 08:00 後 3H 收盤突破) ---
                if latest_3d['high'] >= p_price:
                    ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=120)
                    df_1h = pd.DataFrame(ohlcv_1h, columns=['ts', 'open', 'high', 'low', 'close', 'vol']).iloc[:-1]
                    df_1h = df_1h[df_1h['ts'] >= latest_3d['ts']].reset_index(drop=True)
                    
                    for i in range(0, len(df_1h) - 2, 3):
                        group = df_1h.iloc[i : i+3]
                        if len(group) < 3: break
                        if group.iloc[-1]['close'] > p_price:
                            entry = group.iloc[-1]['close']
                            sl = group['low'].min()
                            display_name = symbol.split(':')[0]
                            current_data[display_name] = f"•{display_name}\n壓力: `{p_price}` ({p_date})\n進場: `{entry}`"
                            break
            except: continue

        # --- 輸出比對與檔案儲存 ---
        current_symbols = set(current_data.keys())
        # (這裡省略重複的 Telegram 輸出代碼，同上版)
        save_current_symbols(current_symbols) # 請確保此函式在您的環境中存在
        
    except Exception as e:
        send_telegram_msg(f"❌ 錯誤: `{str(e)}`")

if __name__ == "__main__":
    check_bitget_signals()
