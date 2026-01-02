import ccxt
import pandas as pd
import requests

# --- 使用你儲存的設定 ---
TELEGRAM_TOKEN = '你的_TOKEN'
TELEGRAM_CHAT_ID = '你的_CHAT_ID'

def send_telegram_msg(message):
    """發送訊息至 Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram 發送失敗: {e}")

def check_bitget_signals():
    # 初始化 Bitget
    exchange = ccxt.bitget()
    
    print("正在獲取 Bitget 永續合約列表...")
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print(f"連線交易所失敗: {e}")
        return

    # 篩選 USDT 永續合約
    symbols = [symbol for symbol, market in markets.items() 
               if market.get('linear') and market.get('quote') == 'USDT' and market.get('active')]
    
    hit_symbols = []
    
    print(f"掃描中 (共 {len(symbols)} 個幣種)...")

    for symbol in symbols:
        try:
            # 獲取 3D K線 (取 15 根確保足夠)
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
            if len(ohlcv) < 10:
                continue
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # 邏輯判斷
            last_close = df['close'].iloc[-1]
            # 往前 8 根 K 棒的最低價 (不含最新一根)
            lookback_lows = df['low'].iloc[-9:-1].tolist()
            
            # 排序取第二小
            second_lowest = sorted(lookback_lows)[1]
            
            if last_close > second_lowest:
                hit_symbols.append(f"• `{symbol:10}` (現價: {last_close})")
                
        except:
            continue

    # --- 整理訊息並發送 ---
    if hit_symbols:
        report = "🔔 *Bitget 3D 級別選幣結果*\n"
        report += f"條件：最新收盤價 > 過去8根K棒之次低點\n\n"
        report += "\n".join(hit_symbols)
        send_telegram_msg(report)
        print("✅ 訊號已發送至 Telegram")
    else:
        # send_telegram_msg("掃描完成，目前無符合條件的幣種。")
        print("掃描完成，無符合條件幣種。")

if __name__ == "__main__":
    check_bitget_signals()
