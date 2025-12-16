# ============================================================================
# TEST ELITE ORB - A+ SETUPS ONLY!
# ============================================================================

import pandas as pd
import yfinance as yf
from elite_orb_strategy import EliteORBStrategy
from scanner import find_daily_gappers

def fetch_bars(symbol: str, period: str = "60d", interval: str = "5m"):
    """Download stock data"""
    print(f"📥 Downloading {symbol}...")
    df = yf.download(
        symbol, 
        period=period, 
        interval=interval, 
        progress=False, 
        auto_adjust=True,
        prepost=False
    )
    
    if df.empty:
        return pd.DataFrame()
    
    # Fix columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: c.lower() for c in df.columns})
    
    # Fix timezone
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert('US/Eastern')
    else:
        df.index = df.index.tz_convert('US/Eastern')
    df.index = df.index.tz_localize(None)
    
    print(f"✅ Got {len(df)} bars")
    return df

# ============================================================================
# MAIN TEST
# ============================================================================
print("\n" + "="*70)
print("🎯 TESTING ELITE ORB - A++ SETUPS ONLY!")
print("="*70)
print("This only takes trades that match your instructor's screenshots!")
print("="*70 + "\n")

# Initialize strategy
strategy = EliteORBStrategy()

# Get gap stocks from scanner
WATCHLIST = find_daily_gappers()
if not WATCHLIST:
    # Backup list if scanner fails
    WATCHLIST = ["BBAI", "SOUN", "PLUG", "RIOT", "MARA"]

print(f"Testing {len(WATCHLIST)} stocks...\n")

# Track all trades
all_trades = []
total_pnl = 0

for symbol in WATCHLIST[:10]:  # Test first 10
    print(f"Testing {symbol}...")
    
    df = fetch_bars(symbol)
    if df.empty:
        print(f"  ❌ No data")
        continue
    
    trades_found = 0
    
    # Test each day
    for date, day_df in df.groupby(df.index.date):
        # Look for A+ setup
        setup = strategy.scan_for_setup(day_df, symbol, str(date))
        
        if setup:
            # Found A+ setup!
            quality = setup['quality_score']
            gap = setup['gap_pct']
            
            print(f"  ✅ {date}: Quality {quality}/100, Gap {gap}%")
            
            # Backtest the trade
            trade_result = strategy.backtest_trade(day_df, setup)
            
            pnl = trade_result['pnl']
            r = trade_result['r_multiple']
            
            print(f"     Result: {trade_result['result']} | PnL: ${pnl:.2f} ({r:.1f}R)")
            
            all_trades.append(trade_result)
            total_pnl += pnl
            trades_found += 1
    
    if trades_found == 0:
        print(f"  No A+ setups found")

# Summary
print("\n" + "="*70)
print("📊 FINAL RESULTS")
print("="*70)

if all_trades:
    wins = sum(1 for t in all_trades if t['pnl'] > 0)
    total = len(all_trades)
    winrate = wins / total * 100
    
    print(f"Total A+ Trades: {total}")
    print(f"Winners: {wins} ({winrate:.1f}%)")
    print(f"Total PnL: ${total_pnl:.2f}")
    print(f"Average per trade: ${total_pnl/total:.2f}")
    
    # Update strategy performance
    strategy.update_performance(all_trades)
    print(f"Strategy Confidence: {strategy.get_confidence():.2f}")
else:
    print("❌ No A+ setups found!")
    print("\nThis is EXPECTED - A+ setups are RARE!")
    print("Your instructor only shows the best 2-3 per week!")

print("\n✅ Test complete!")