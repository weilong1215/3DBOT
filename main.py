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
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Telegram 發送失敗: {response.text}")
    except Exception as e:
        print(f"Telegram 連線錯誤: {e}")

def check_bitget_signals():
    # 1. 啟動通知
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
        # 篩選 USDT 永續合約 (排除現貨與非USDT結算)
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and m.get('active')]
        print(f"找到 {len(symbols)} 個合約，開始掃描...")

        hit_symbols = []
        
        for symbol in symbols:
            try:
                # 獲取 3D K線 (取 15 根)
                ohlcv
