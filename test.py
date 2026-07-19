import pandas as pd
import numpy as np
import requests
import time
import os
from datetime import datetime
import http.server
import threading
# Render ka port check bypass karne ke liye dummy server
threading.Thread(target=lambda: http.server.HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), http.server.BaseHTTPRequestHandler).serve_forever(), daemon=True).start()

# =========================================================================
# BYBIT FUTURES: LIVE PAPER TRADING BOT (ANTI-SPAM REPORTING FIXED)
# =========================================================================
SYMBOL = "DOGEUSDT"
MAX_ALLOWED_SLIPPAGE_PCT = 0.005 
EXCEL_FILE = "trading_report.csv"

def log_trade_to_excel(trade_data):
    df_new = pd.DataFrame(trade_data, index=[0]) 
    if not os.path.isfile(EXCEL_FILE):
        df_new.to_csv(EXCEL_FILE, index=False)
    else:
        df_new.to_csv(EXCEL_FILE, mode='a', header=False, index=False)
    print(f"\n📝 Trade successfully recorded in '{EXCEL_FILE}'!")

print(f"🚀 Live Paper Trading Bot Started for {SYMBOL} (via Bybit)...")
print(f"📊 Tracking live market. Reports will be saved to: {EXCEL_FILE}\n")

active_short_alert_price = None
active_long_alert_price = None

# --- Spam se bachne ke liye tracking variables ---
last_processed_candle_time = None  # Taaki ek hi closed candle baar-baar alert lock na kare
short_breakout_done = False        # Taaki ek hi alert par live loop baar-baar entry na daale
long_breakout_done = False

url = "https://api.bybit.com/v5/market/kline"

while True:
    try:
        params = {"category": "linear", "symbol": SYMBOL, "interval": "5", "limit": 100}
        res = requests.get(url, params=params, timeout=10).json()
        
        if res.get("retCode") != 0 or not res.get("result", {}).get("list"):
            time.sleep(5)
            continue
            
        raw_list = res["result"]["list"]
        raw_list.reverse()
        
        all_rows = []
        for candle in raw_list:
            all_rows.append({
                'timestamp': int(candle[0]), 'open': float(candle[1]), 'high': float(candle[2]),
                'low': float(candle[3]), 'close': float(candle[4]), 'volume': float(candle[5])
            })
            
        df = pd.DataFrame(all_rows)
        
        # Indicators
        df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['vol_sma20'] = df['volume'].rolling(window=20).mean()
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
            
        prev = df.iloc[-2]  # Just closed candle
        curr = df.iloc[-1]  # Live candle
        
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Nayi candle shuru hone par flags reset karein
        if last_processed_candle_time != prev['timestamp']:
            last_processed_candle_time = prev['timestamp']
            active_short_alert_price = None
            active_long_alert_price = None
            short_breakout_done = False
            long_breakout_done = False
        
        print(f"👀 [{current_time_str}] Price: {curr['close']} | 5 EMA: {round(curr['ema5'], 5)} | Short Locked: {active_short_alert_price} | Long Locked: {active_long_alert_price}      ", end="\r")
        
        # ----------------------------------------------------
        # SHART 1: DYNAMIC RESET (EMA TOUCH CONTROL)
        # ----------------------------------------------------
        if active_short_alert_price is not None and prev['low'] <= prev['ema5']:
            print(f"\n⏱️ [{current_time_str}] SHORT Alert Cancelled: Candle touched 5 EMA.")
            active_short_alert_price = None
            
        if active_long_alert_price is not None and prev['high'] >= prev['ema5']:
            print(f"\n⏱️ [{current_time_str}] LONG Alert Cancelled: Candle touched 5 EMA.")
            active_long_alert_price = None

        # ----------------------------------------------------
        # SHART 2: FRESH SIGNAL DETECTION (ALERT SETTING)
        # ----------------------------------------------------
        if prev['low'] > prev['ema5'] and active_short_alert_price is None and not short_breakout_done:
            active_short_alert_price = prev['low']
            print(f"\n🚨 [{current_time_str}] SHORT Alert Locked! Target Low: {active_short_alert_price}")
            
        if prev['high'] < prev['ema5'] and active_long_alert_price is None and not long_breakout_done:
            active_long_alert_price = prev['high']
            print(f"\n🚨 [{current_time_str}] LONG Alert Locked! Target High: {active_long_alert_price}")

        # ----------------------------------------------------
        # SHART 3: LIVE BREAKOUT DETECTION & EXCEL LOGGING
        # ----------------------------------------------------
        if active_short_alert_price is not None and not short_breakout_done:
            if curr['low'] < active_short_alert_price:
                volume_pass = prev['volume'] >= (prev['vol_sma20'] * 1.5)
                rsi_pass = prev['rsi'] >= 50
                slippage = (active_short_alert_price - curr['close']) / active_short_alert_price
                slippage_pass = slippage <= MAX_ALLOWED_SLIPPAGE_PCT
                
                trade_status = "EXECUTED" if (volume_pass and rsi_pass and slippage_pass) else "FILTERED_OUT"
                reason = "SUCCESS" if trade_status == "EXECUTED" else ("Low Volume" if not volume_pass else ("RSI Fail" if not rsi_pass else "High Slippage"))
                
                trade_log = {
                    "Timestamp": current_time_str, "Type": "SHORT", "Alert_Trigger_Price": active_short_alert_price,
                    "Live_Execution_Price": curr['close'], "Candle_Volume": prev['volume'], "Avg_Volume_20": prev['vol_sma20'],
                    "RSI_Value": prev['rsi'], "Slippage_Pct": round(slippage * 100, 3), "Status": trade_status, "Remarks": reason
                }
                print(f"\n⚡ BREAKOUT DETECTED! Status: {trade_status} | Reason: {reason}")
                log_trade_to_excel(trade_log)
                short_breakout_done = True # Lock breakout for this candle
                active_short_alert_price = None 

        if active_long_alert_price is not None and not long_breakout_done:
            if curr['high'] > active_long_alert_price:
                volume_pass = prev['volume'] >= (prev['vol_sma20'] * 1.5)
                rsi_pass = prev['rsi'] <= 50
                slippage = (curr['close'] - active_long_alert_price) / active_long_alert_price
                slippage_pass = slippage <= MAX_ALLOWED_SLIPPAGE_PCT
                
                trade_status = "EXECUTED" if (volume_pass and rsi_pass and slippage_pass) else "FILTERED_OUT"
                reason = "SUCCESS" if trade_status == "EXECUTED" else ("Low Volume" if not volume_pass else ("RSI Fail" if not rsi_pass else "High Slippage"))
                
                trade_log = {
                    "Timestamp": current_time_str, "Type": "LONG", "Alert_Trigger_Price": active_long_alert_price,
                    "Live_Execution_Price": curr['close'], "Candle_Volume": prev['volume'], "Avg_Volume_20": prev['vol_sma20'],
                    "RSI_Value": prev['rsi'], "Slippage_Pct": round(slippage * 100, 3), "Status": trade_status, "Remarks": reason
                }
                print(f"\n⚡ BREAKOUT DETECTED! Status: {trade_status} | Reason: {reason}")
                log_trade_to_excel(trade_log)
                long_breakout_done = True # Lock breakout for this candle
                active_long_alert_price = None 

        time.sleep(3) 
        
    except Exception as e:
        print(f"\n❌ Error: {e}. Retrying in 5 seconds...")
        time.sleep(5)
