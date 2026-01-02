import ccxt
import pandas as pd
import requests
import time

# --- 填入你的設定 ---
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
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram 發送失敗，狀態碼: {response.status_code}, 回傳內容: {response.text}")
    except Exception as e:
        print(f"Telegram 連線錯誤: {e}")

def check_bitget_signals():
    # 1. 啟動通知 (讓你確認程式有在跑)
    start_msg = "🔍 *Bitget 3D 掃描器啟動*\n正在檢查 3D 級別 K 棒符合「收盤 > 過去8根次低點」之品種..."
    print(start_msg)
    send_telegram_msg(start_msg)

    # 2. 初始化交易所
    exchange = ccxt.bitget({
        'timeout': 30000,
        'enableRateLimit': True,
    })

    try:
        print("正在獲取市場列表...")
        markets = exchange.load_markets()
        # 篩選 USDT 永續合約
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and m.get('active')]
        print(f"找到 {len(symbols)} 個合約，開始掃描...")

        hit_symbols = []
        count = 0

        for symbol in symbols:
            try:
                # 獲取 3D K線 (15根)
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='3d', limit=15)
                if len(ohlcv) < 10:
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # 最新收盤價
                last_close = df['close'].iloc[-1]
                
                # 往前 8 根 K 棒 (不含當前這一根)
                lookback_lows = df['low'].iloc[-9:-1].
