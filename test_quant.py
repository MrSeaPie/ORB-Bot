# ============================================================================
# TEST QUANT ENGINE - Multiple Strategies Fighting for Capital!
# ============================================================================

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time

# Import the quant engine (check if your file has capital Q)
try:
    from quant_engine import QuantEngine, ORB_15Min_Strategy, GapAndGo_Strategy, VWAPBounce_Strategy
except:
    from Quant_engine import QuantEngine, ORB_15Min_Strategy, GapAndGo_Strategy, VWAPBounce_Strategy

def download_stock(symbol, days=30):
    """Download stock data"""
    print(f"Downloading {symbol}...")
    df = yf.download(
        symbol, 
        period=f"{days}d", 
        interval="5m",
        progress=False
    )
    
    if df.empty:
        return None
        
    # Fix columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    
    # Add time column for strategies
    df.index = pd.to_datetime(df.index)
    
    return df

# ============================================================================
# MAIN TEST
# ============================================================================
print("\n" + "="*70)
print("🤖 TESTING QUANT ENGINE - MULTI-STRATEGY SYSTEM")
print("="*70)
print("This is like having 3 traders compete for your money!")
print("The engine tracks who wins and gives them more capital!")
print("="*70 + "\n")

# Step 1: Create the engine with your capital
engine = QuantEngine(capital=5000)  # Your $5,000
print(f"💰 Starting capital: ${engine.capital}")

# Step 2: Add strategies (like hiring traders)
print("\n📊 Adding strategies (hiring traders)...")
engine.add_strategy(ORB_15Min_Strategy())
engine.add_strategy(GapAndGo_Strategy())
engine.add_strategy(VWAPBounce_Strategy())

# Step 3: Test on some stocks
test_stocks = ["BBAI", "SOUN", "PLUG"]
print(f"\n🎯 Testing on: {test_stocks}")

all_results = []

for symbol in test_stocks:
    print(f"\n{'='*50}")
    print(f"Testing {symbol}")
    print("="*50)
    
    # Download data
    df = download_stock(symbol)
    if df is None:
        print(f"  ❌ No data for {symbol}")
        continue
    
    print(f"  ✅ Got {len(df)} bars of data")
    
    # Test on last 10 trading days
    dates = df.index.date
    unique_dates = sorted(set(dates))[-10:]  # Last 10 days
    
    for date in unique_dates:
        # Get that day's data
        day_df = df[df.index.date == date]
        
        if len(day_df) < 20:  # Need enough bars
            continue
        
        # Run the engine!
        result = engine.execute_backtest(day_df, symbol, str(date))
        
        # Show what happened
        if result['trades']:
            print(f"\n  📅 {date}:")
            print(f"    Signals found: {result['decision_log']['signals_generated']}")
            print(f"    Trades taken: {result['decision_log']['trades_taken']}")
            
            for trade in result['trades']:
                strategy = trade['strategy']
                confidence = trade['confidence']
                pnl = trade['pnl']
                print(f"    → {strategy}: Confidence {confidence:.2f}, PnL ${pnl:.2f}")
            
            all_results.append(result)

# ============================================================================
# SHOW RESULTS
# ============================================================================
print("\n" + "="*70)
print("📊 FINAL RESULTS - WHO WON?")
print("="*70)

# Get performance summary
summary = engine.get_performance_summary()

if summary['strategy_performance']:
    print("\n🏆 Strategy Performance (Who's the best trader?):\n")
    
    for strategy_name, stats in summary['strategy_performance'].items():
        print(f"  {strategy_name}:")
        print(f"    Trades: {stats['trades']}")
        print(f"    Win Rate: {stats['win_rate']}%")
        print(f"    Confidence: {stats['confidence']}")
        print(f"    → Gets ${5000 * stats['confidence']:.0f} to trade with!")
        print()
else:
    print("❌ No trades were generated")
    print("\nThis might mean:")
    print("1. No setups matched the patterns")
    print("2. Need to test more stocks")
    print("3. Need to add more strategies")

print("\n" + "="*70)
print("💡 WHAT JUST HAPPENED?")
print("="*70)
print("1. We ran 3 strategies on each stock")
print("2. Engine tracked which strategy worked")
print("3. Winners get more capital next time!")
print("4. This is AUTOMATIC portfolio management!")

print("\n✅ Test complete!")