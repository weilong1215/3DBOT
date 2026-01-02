import ccxt
import pandas as pd
import requests
import time

# --- 你的設定資訊 ---
TELEGRAM_TOKEN = '8320176690:AAFSLaveCTTRWDygX1FZdkeHLi2UnxPtfO0' 
TELEGRAM_CHAT_ID = '1041632710'

def send_telegram_msg(message):
    """發送訊息至 Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            print(f"Telegram 發送失敗: {response.text}")
    except Exception as e:
        print(f"Telegram 連線錯誤: {e}")

def check_bitget_signals():
    # 1. 啟動通知
    start_msg = "🔍 *Bitget 3D 掃描器啟動*\n條件：最新收盤價 > 過去8根K棒之次低點"
    print(start_msg)
    send_telegram_msg(start_msg)

    # 2. 初始化交易所 (Bitget)
    exchange = ccxt.bitget({
        'timeout': 30000,
        'enableRateLimit': True,
    })

    try:
        print("正在獲取 Bitget 市場列表...")
        markets = exchange.load_markets()
        # 篩選 USDT 永續合約
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and m.get('active')]
        print(f"找到 {len(symbols)} 個合約，開始掃描數據...")

        hit_symbols = []
        
        for symbol in symbols:
            try:
                # 獲取 3D K線
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
                if len(ohlcv) < 10:
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # 最新收盤價
                last_close =
