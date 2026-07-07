import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime

# --- CONFIGURATION (PAPER TRADING SETTINGS) ---
SYMBOL = 'SOLUSDT'
TIMEFRAME = '5m'
LEVERAGE = 10
MARGIN_PER_TRADE = 3.0  # $3.00 USD (Approx ₹250 INR)
INITIAL_VIRTUAL_BALANCE = 100.0

print(f"🚀 Live Paper Trading Bot Starting for {SYMBOL}...")
print(f"💰 Virtual Starting Capital: ${INITIAL_VIRTUAL_BALANCE:.2f} | Margin: ${MARGIN_PER_TRADE:.2f} | Leverage: {LEVERAGE}x")
print("==================================================================")

# --- LIVE DATA STREAM FUNCTION ---
def get_live_candles(symbol, interval, limit=50):
    url = "https://api.binance.com/api/v3/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        res = requests.get(url, params=params).json()
        df = pd.DataFrame(res, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"⚠️ Live Data Fetch Error: {e}")
        return None

# --- INDICATOR CALCULATOR ---
def calculate_indicators(df):
    df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    return df

# --- CORE STATE VARIABLES ---
virtual_balance = INITIAL_VIRTUAL_BALANCE
position = None  # 'LONG', 'SHORT', None
entry_price, stop_loss, take_profit, qty = 0.0, 0.0, 0.0, 0.0
alert_candle = None  # Stores the alert candle series

# --- LIVE ENGINE LOOP ---
while True:
    try:
        # 1. Fetch Latest Data
        df_raw = get_live_candles(SYMBOL, TIMEFRAME)
        if df_raw is None or df_raw.empty:
            time.sleep(5)
            continue
            
        df = calculate_indicators(df_raw)
        
        # Live Candle (Running candle)
        curr_candle = df.iloc[-1]
        current_price = curr_candle['close']
        
        # Closed Candle (Fully formed candle to avoid repainting)
        prev_candle = df.iloc[-2]
        prev_2_candle = df.iloc[-3]
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # ----------------------------------------------------
        # PHASE 1: LIVE POSITION MONITORING & EXIT CHECK
        # ----------------------------------------------------
        if position == 'LONG':
            if curr_candle['low'] <= stop_loss:
                pnl = (stop_loss - entry_price) * qty * LEVERAGE
                virtual_balance += pnl
                print(f"❌ [SL HIT] | {now} | Long Position Closed at ${stop_loss:.2f} | PnL: ${pnl:.2f} | Balance: ${virtual_balance:.2f}")
                position = None
            elif curr_candle['high'] >= take_profit:
                pnl = (take_profit - entry_price) * qty * LEVERAGE
                virtual_balance += pnl
                print(f"🎯 [TARGET HIT] | {now} | Long Position Closed at ${take_profit:.2f} | PnL: ${pnl:.2f} | Balance: ${virtual_balance:.2f}")
                position = None
            elif prev_candle['ema5'] < prev_candle['ema20'] and prev_2_candle['ema5'] >= prev_2_candle['ema20']:
                pnl = (current_price - entry_price) * qty * LEVERAGE
                virtual_balance += pnl
                print(f"📉 [EMA EXIT] | {now} | Bearish Cross Under! Long Closed at ${current_price:.2f} | PnL: ${pnl:.2f} | Balance: ${virtual_balance:.2f}")
                position = None

        elif position == 'SHORT':
            if curr_candle['high'] >= stop_loss:
                pnl = (entry_price - stop_loss) * qty * LEVERAGE
                virtual_balance += pnl
                print(f"❌ [SL HIT] | {now} | Short Position Closed at ${stop_loss:.2f} | PnL: ${pnl:.2f} | Balance: ${virtual_balance:.2f}")
                position = None
            elif curr_candle['low'] <= take_profit:
                pnl = (entry_price - take_profit) * qty * LEVERAGE
                virtual_balance += pnl
                print(f"🎯 [TARGET HIT] | {now} | Short Position Closed at ${take_profit:.2f} | PnL: ${pnl:.2f} | Balance: ${virtual_balance:.2f}")
                position = None
            elif prev_candle['ema5'] > prev_candle['ema20'] and prev_2_candle['ema5'] <= prev_2_candle['ema20']:
                pnl = (entry_price - current_price) * qty * LEVERAGE
                virtual_balance += pnl
                print(f"📈 [EMA EXIT] | {now} | Bullish Cross Over! Short Closed at ${current_price:.2f} | PnL: ${pnl:.2f} | Balance: ${virtual_balance:.2f}")
                position = None

        # ----------------------------------------------------
        # PHASE 2: LIVE ENTRY MONITORING & LOGIC
        # ----------------------------------------------------
        if position is None:
            # Check for standard conditions on the closed candle
            
            # --- LONG ENTRY CHECK ---
            if prev_candle['high'] < prev_candle['ema5']:
                if alert_candle is None or alert_candle['type'] != 'LONG':
                    alert_candle = {'type': 'LONG', 'high': prev_candle['high'], 'low': prev_candle['low'], 'time': prev_candle['timestamp']}
                    print(f"🔔 [ALERT) New LONG Alert Candle Formed at {alert_candle['time']} | High: {alert_candle['high']} | Low: {alert_candle['low']}")
            
            if alert_candle is not None and alert_candle['type'] == 'LONG':
                # Invalidation Rule
                if curr_candle['low'] < alert_candle['low']:
                    print(f"🗑️ [INVALIDATED] Price broke Alert Low. Resetting Long Setup.")
                    alert_candle = None
                # Execution Rule
                elif curr_candle['high'] > alert_candle['high']:
                    entry_price = alert_candle['high']
                    stop_loss = alert_candle['low']
                    risk = entry_price - stop_loss
                    if risk > 0:
                        take_profit = entry_price + (3 * risk)
                        qty = MARGIN_PER_TRADE / entry_price
                        position = 'LONG'
                        alert_candle = None
                        print(f"🟢 [VIRTUAL LONG ENTRY] Triggered at ${entry_price:.2f} | SL: ${stop_loss:.2f} | TP (1:3): ${take_profit:.2f}")
            
            # --- SHORT ENTRY CHECK ---
            if prev_candle['low'] > prev_candle['ema5']:
                if alert_candle is None or alert_candle['type'] != 'SHORT':
                    alert_candle = {'type': 'SHORT', 'high': prev_candle['high'], 'low': prev_candle['low'], 'time': prev_candle['timestamp']}
                    print(f"🔔 [ALERT] New SHORT Alert Candle Formed at {alert_candle['time']} | High: {alert_candle['high']} | Low: {alert_candle['low']}")
            
            if alert_candle is not None and alert_candle['type'] == 'SHORT':
                # Invalidation Rule
                if curr_candle['high'] > alert_candle['high']:
                    print(f"🗑️ [INVALIDATED] Price broke Alert High. Resetting Short Setup.")
                    alert_candle = None
                # Execution Rule
                elif curr_candle['low'] < alert_candle['low']:
                    entry_price = alert_candle['low']
                    stop_loss = alert_candle['high']
                    risk = stop_loss - entry_price
                    if risk > 0:
                        take_profit = entry_price - (3 * risk)
                        qty = MARGIN_PER_TRADE / entry_price
                        position = 'SHORT'
                        alert_candle = None
                        print(f"🔴 [VIRTUAL SHORT ENTRY] Triggered at ${entry_price:.2f} | SL: ${stop_loss:.2f} | TP (1:3): ${take_profit:.2f}")

        # Console dashboard refresh log (Har 10 second mein updates dikhane ke liye)
        if position is not None:
            print(f"⏳ Live Monitoring {position} Trade... Current Price: ${current_price:.2f} | Live PnL: ${((current_price - entry_price) * qty * LEVERAGE if position == 'LONG' else (entry_price - current_price) * qty * LEVERAGE):.2f}", end='\r')
            
        time.sleep(2) # 2-2 second ke loop par updates refresh honge

    except KeyboardInterrupt:
        print("\n🛑 Paper Trading Bot manually stopped by user.")
        break
    except Exception as e:
        print(f"\n⚠️ Runtime Exception loop error: {e}")
        time.sleep(5)