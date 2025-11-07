# ============================================================================
# EMERGENCY DEBUG: Why are we getting ZERO trades?
# ============================================================================

import pandas as pd
import yfinance as yf
from datetime import time

print("="*70)
print("🔍 DEBUGGING: Why no trades?")
print("="*70)

# Download AAPL
print("\n📥 Step 1: Downloading AAPL...")
df = yf.download("AAPL", period="10d", interval="5m", progress=False)

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

df = df.rename(columns={c: c.lower() for c in df.columns})

print(f"✅ Downloaded {len(df)} bars")

# Check timezone
print(f"\n🕐 Step 2: Checking timezone...")
print(f"   Original timezone: {df.index.tz}")

if df.index.tz is None:
    df.index = df.index.tz_localize('UTC').tz_convert('US/Eastern')
else:
    df.index = df.index.tz_convert('US/Eastern')

df.index = df.index.tz_localize(None)

print(f"   After conversion: timezone-naive")

# Check actual bar times
print(f"\n🕐 Step 3: What times do we actually have?")
print(f"   First bar: {df.index[0]}")
print(f"   Last bar: {df.index[-1]}")

# Get a recent complete trading day
recent_days = df.groupby(df.index.date).size()
full_days = recent_days[recent_days > 50]  # At least 50 bars = full day

if len(full_days) > 0:
    test_day = full_days.index[-2]  # Second to last day (avoid today)
    day_df = df[df.index.date == test_day]
    
    print(f"\n📅 Step 4: Checking day {test_day}")
    print(f"   Total bars: {len(day_df)}")
    print(f"   First bar time: {day_df.index[0].time()}")
    print(f"   Last bar time: {day_df.index[-1].time()}")
    
    # Show first 5 bars
    print(f"\n   First 5 bars:")
    for i in range(min(5, len(day_df))):
        bar = day_df.iloc[i]
        print(f"      {day_df.index[i].time()} - O:{bar['open']:.2f} H:{bar['high']:.2f} L:{bar['low']:.2f} C:{bar['close']:.2f}")
    
    # Check time windows
    print(f"\n🔍 Step 5: Checking time windows...")
    
    or_start = time(9, 30)
    or_end = time(9, 35)
    base_start = time(9, 35)
    base_end = time(9, 45)
    trade_start = time(9, 45)
    trade_end = time(15, 30)
    
    or_df = day_df.between_time(or_start, or_end)
    base_df = day_df.between_time(base_start, base_end)
    trade_df = day_df.between_time(trade_start, trade_end)
    
    print(f"   OR bars (9:30-9:35):     {len(or_df)}")
    print(f"   Base bars (9:35-9:45):   {len(base_df)}")
    print(f"   Trade bars (9:45-15:30): {len(trade_df)}")
    
    if len(or_df) == 0:
        print("\n❌ PROBLEM FOUND: No bars in OR window (9:30-9:35)!")
        print("   This means bars don't start at 9:30, or timezone is wrong")
        
        # Find when bars actually start
        morning_bars = day_df[day_df.index.time < time(10, 0)]
        if len(morning_bars) > 0:
            print(f"\n   Bars actually start at: {morning_bars.index[0].time()}")
            print(f"   First morning bars:")
            for i in range(min(3, len(morning_bars))):
                bar = morning_bars.iloc[i]
                print(f"      {morning_bars.index[i].time()} - O:{bar['open']:.2f}")
    else:
        # We have OR bars, check breakout
        or_high = or_df['high'].max()
        or_low = or_df['low'].min()
        
        print(f"\n   OR High: ${or_high:.2f}")
        print(f"   OR Low:  ${or_low:.2f}")
        print(f"   OR Range: ${or_high - or_low:.2f}")
        
        if len(trade_df) > 0:
            breaks_high = (trade_df['high'] > or_high).any()
            breaks_low = (trade_df['low'] < or_low).any()
            
            print(f"\n   Breaks OR High? {breaks_high}")
            print(f"   Breaks OR Low?  {breaks_low}")
            
            if breaks_high or breaks_low:
                print(f"\n✅ This day SHOULD produce a trade!")
                print(f"\n   The problem is likely in the strategy gates.")
                print(f"   Check if you turned OFF all gates:")
                print(f"      base_near_vwap_atr=0")
                print(f"      base_tight_frac=0")
                print(f"      or_width_min_atr=0")
                print(f"      or_width_max_atr=0")
            else:
                print(f"\n   No breakout on this day (price stayed inside OR)")
else:
    print("\n❌ No full trading days found in data!")

print("\n" + "="*70)
print("📋 DIAGNOSIS:")
print("="*70)

if len(full_days) > 0 and len(or_df) == 0:
    print("❌ TIMEZONE ISSUE: Bars don't align with 9:30-9:35 window")
    print("\nFIX: The data might be in a different timezone or format")
    print("Try this in run_framework.py after downloading:")
    print("""
    # Force to Eastern time more aggressively
    if df.index.tz is not None:
        df.index = df.index.tz_convert('America/New_York')
        df.index = df.index.tz_localize(None)
    else:
        # Assume data is already in Eastern
        pass
    """)
elif len(full_days) == 0:
    print("❌ DATA ISSUE: Not enough trading days in the data")
    print("\nFIX: Try downloading more data (period='30d' or '60d')")
else:
    print("❌ LOGIC ISSUE: OR window exists but no trades generated")
    print("\nFIX: Make sure ALL gates are set to 0 in run_framework.py:")
    print("""
    cfg = ORBConfig(
        base_near_vwap_atr=0,
        base_tight_frac=0,
        or_width_min_atr=0,
        or_width_max_atr=0,
    )
    """)

print("\n✅ Debug complete!")