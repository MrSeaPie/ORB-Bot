# ============================================================================
# RUN SIMPLIFIED ORB - THIS IS THE MAIN FILE!
# ============================================================================
# Based on reading all 6 bootcamp transcripts:
# - 15-minute OR (not 5!)
# - Stop below OR (simple!)
# - NO complex gates!
# ============================================================================

import pandas as pd
import yfinance as yf
from simple_framework import SimpleORB, ORBConfig, TradeLogger, PerformanceAnalyzer


def fetch_bars(symbol: str, period: str = "60d", interval: str = "5m"):
    """Download stock data"""
    print(f"📥 Downloading {symbol}...")
    try:
        df = yf.download(
            symbol, 
            period=period, 
            interval=interval, 
            progress=False, 
            auto_adjust=True,
            prepost=False  # Regular hours only
        )
        
        if df.empty:
            print(f"   ⚠️ No data")
            return pd.DataFrame()
        
        # Fix MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Lowercase columns
        df = df.rename(columns={c: c.lower() for c in df.columns})
        
        # Fix timezone to Eastern
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert('US/Eastern')
        else:
            df.index = df.index.tz_convert('US/Eastern')
        df.index = df.index.tz_localize(None)
        
        print(f"   ✅ Got {len(df)} bars")
        return df
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return pd.DataFrame()


# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    
    print("\n" + "="*70)
    print("🎯 BOOTCAMP EXACT ORB - SIMPLIFIED VERSION")
    print("="*70)
    print("What I fixed based on the transcripts:")
    print("✅ 15-minute OR (you had 5-minute)")
    print("✅ NO complex gates (they don't exist!)")
    print("✅ Stop at OR low (simple!)")
    print("✅ 4%+ gap filter (bootcamp standard)")
    print("="*70 + "\n")
    
    # Simple config - exactly as bootcamp teaches
    cfg = ORBConfig(
        or_start="09:30",
        or_end="09:45",      # 15 minutes
        trade_start="09:45",
        trade_end="11:00",   # Morning only
        risk_dollars=250.0,
        target_r1=1.0,       # Sell half at 1R
        target_r2=2.0,       # Trail to 2R
    )
    
    # Initialize
    logger = TradeLogger(log_dir="logs/trades")
    strategy = SimpleORB(config=cfg, logger=logger)
    
    # Watchlist - known gap stocks
    WATCHLIST = [
        # Big movers
        "TSLA", "NVDA", "AMD", "PLTR", "COIN",
        
        # Your original list
        "RIOT", "MARA", "BBAI", "SOUN", "PLUG",
        "ATOS", "OCGN", "GEVO", "WKHS", "SPCE",
    ]
    
    print(f"Testing {len(WATCHLIST)} stocks...\n")
    
    # Track results
    total_pnl = 0
    total_trades = 0
    all_results = []
    
    # Test each stock
    for symbol in WATCHLIST:
        print(f"{'='*70}")
        print(f"Testing {symbol}")
        print("="*70)
        
        df = fetch_bars(symbol, period="60d")
        if df.empty:
            continue
        
        # Run with 4% gap filter (bootcamp standard)
        results = strategy.run_backtest(
            df,
            symbol=symbol,
            filter_gap_days=True,  # Only gap days
            min_gap_pct=4.0        # 4%+ gaps
        )
        
        if results['trades'] > 0:
            print(f"   ✅ Trades: {results['trades']}")
            print(f"   📈 Winrate: {results['winrate']*100:.1f}%")
            print(f"   💰 PnL: ${results['total_pnl']:.2f}")
            
            total_pnl += results['total_pnl']
            total_trades += results['trades']
            all_results.extend(results.get('results', []))
        else:
            print(f"   No trades (no setups on gap days)")
    
    # Summary
    print("\n" + "="*70)
    print("📊 FINAL RESULTS")
    print("="*70)
    print(f"Total trades: {total_trades}")
    print(f"Total PnL: ${total_pnl:.2f}")
    
    if total_trades > 0:
        wins = sum(1 for r in all_results if r['pnl'] > 0)
        winrate = wins / total_trades
        print(f"Overall winrate: {winrate*100:.1f}%")
        print(f"Avg per trade: ${total_pnl/total_trades:.2f}")
    else:
        print("\n⚠️ NO TRADES GENERATED!")
        print("\nPossible issues:")
        print("1. No 4%+ gap days in data")
        print("2. No OR breakouts on gap days")
        print("3. Try without gap filter")
    
    # Save trades
    if total_trades > 0:
        print("\n" + "="*70)
        print("💾 SAVING TRADES")
        print("="*70)
        filepath = logger.save(filename="simple_orb_results.csv")
        if filepath:
            print(f"✅ Saved to: {filepath}")
        
        # Analysis
        trades_df = logger.get_trades_df()
        if not trades_df.empty:
            analyzer = PerformanceAnalyzer(trades_df)
            analyzer.print_report()
    
    print("\n✅ Complete!")
    print("\nIf no trades, try:")
    print("1. Set filter_gap_days=False to test all days")
    print("2. Lower min_gap_pct to 2.0")
    print("3. Check individual stocks manually")