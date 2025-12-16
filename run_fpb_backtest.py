"""
==============================================================================
RUN FPB BACKTEST
==============================================================================
Downloads data and runs the First Pullback Buy strategy
==============================================================================
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from fpb_strategy import FirstPullbackBuy, FPBConfig, FPBTradeLogger
import warnings
warnings.filterwarnings('ignore')


# ==============================================================================
# DATA LOADER
# ==============================================================================
def load_data(symbol: str, period: str = "60d", interval: str = "5m") -> pd.DataFrame:
    """
    Download 5-minute data from Yahoo Finance
    
    Args:
        symbol: Stock ticker
        period: Lookback period (max 60d for 5m data)
        interval: Bar interval
        
    Returns:
        DataFrame with OHLCV data
    """
    print(f"📥 Downloading {symbol} data ({period}, {interval})...")
    
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    
    if df is None or len(df) == 0:
        raise ValueError(f"No data returned for {symbol}")
    
    # Handle MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # Standardize column names
    df.columns = [c.lower().strip() for c in df.columns]
    
    # Ensure we have required columns
    required = ['open', 'high', 'low', 'close', 'volume']
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    
    df = df[required].dropna()
    
    # Convert timezone to Eastern
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert('America/New_York')
    else:
        df.index = df.index.tz_convert('America/New_York')
    
    print(f"   ✅ Loaded {len(df)} bars from {df.index[0].date()} to {df.index[-1].date()}")
    
    return df


# ==============================================================================
# MAIN BACKTEST RUNNER
# ==============================================================================
def run_fpb_backtest(
    symbols: list = None,
    period: str = "60d",
    config: FPBConfig = None
) -> dict:
    """
    Run FPB backtest on multiple symbols
    
    Args:
        symbols: List of stock tickers (default: gap stocks)
        period: Data period
        config: FPBConfig (uses defaults if None)
        
    Returns:
        Dict with all results
    """
    
    # Default symbols (known gappers / momentum stocks)
    if symbols is None:
        symbols = [
            # High-beta tech
            "NVDA", "AMD", "TSLA", "META", "GOOGL",
            # Momentum names  
            "COIN", "MSTR", "PLTR", "RKLB", "IONQ",
            # Small cap runners
            "SOUN", "BBAI", "UPST", "AFRM",
        ]
    
    # Config
    if config is None:
        config = FPBConfig()
    
    # Initialize strategy
    logger = FPBTradeLogger()
    strategy = FirstPullbackBuy(config=config, logger=logger)
    
    print("\n" + "="*70)
    print("🚀 FIRST PULLBACK BUY - MULTI-SYMBOL BACKTEST")
    print("="*70)
    print(f"Symbols: {len(symbols)}")
    print(f"Period: {period}")
    print(f"Risk/Trade: ${config.risk_dollars}")
    print(f"Min Gap: {config.min_gap_pct}%")
    print("="*70)
    
    all_results = []
    failed_symbols = []
    
    for symbol in symbols:
        try:
            # Load data
            df = load_data(symbol, period=period)
            
            # Run backtest
            result = strategy.run_backtest(df, symbol=symbol, filter_gap_days=True)
            
            all_results.append(result)
            
        except Exception as e:
            print(f"❌ {symbol}: {e}")
            failed_symbols.append(symbol)
            continue
    
    # Save all trades
    logger.save()
    
    # Aggregate results
    print("\n" + "="*70)
    print("📊 AGGREGATE RESULTS")
    print("="*70)
    
    total_trades = sum(r['trades'] for r in all_results)
    total_pnl = sum(r['total_pnl'] for r in all_results)
    total_winners = sum(r.get('winners', 0) for r in all_results)
    total_losers = sum(r.get('losers', 0) for r in all_results)
    
    if total_trades > 0:
        overall_winrate = total_winners / total_trades * 100
        
        # Get all individual trades
        all_trades = []
        for r in all_results:
            if 'results' in r:
                all_trades.extend(r['results'])
        
        avg_r = np.mean([t['r_multiple'] for t in all_trades]) if all_trades else 0
        
        print(f"\nTotal Symbols: {len(all_results)}")
        print(f"Failed Symbols: {len(failed_symbols)}")
        print(f"\nTotal Trades: {total_trades}")
        print(f"Winners: {total_winners} ({overall_winrate:.1f}%)")
        print(f"Losers: {total_losers}")
        print(f"\n💰 Total PnL: ${total_pnl:.2f}")
        print(f"📈 Avg R-Multiple: {avg_r:.2f}R")
        
        # Best/Worst symbols
        sorted_results = sorted(all_results, key=lambda x: x['total_pnl'], reverse=True)
        
        print(f"\n🏆 TOP PERFORMERS:")
        for r in sorted_results[:3]:
            if r['trades'] > 0:
                print(f"   {r['symbol']}: ${r['total_pnl']:.2f} ({r['trades']} trades, {r['winrate']:.0f}% WR)")
        
        print(f"\n😓 WORST PERFORMERS:")
        for r in sorted_results[-3:]:
            if r['trades'] > 0:
                print(f"   {r['symbol']}: ${r['total_pnl']:.2f} ({r['trades']} trades, {r['winrate']:.0f}% WR)")
        
        # Exit reason summary
        print(f"\n📈 EXIT REASONS (All Trades):")
        for reason in ['TARGET_R2', 'TARGET_R1', 'STOP_BE', 'STOP', 'EOD']:
            count = len([t for t in all_trades if t.get('exit_reason') == reason])
            if count > 0:
                pct = count / len(all_trades) * 100
                print(f"   {reason}: {count} ({pct:.1f}%)")
    else:
        print("\n⚠️ No trades executed across any symbols")
    
    print("\n" + "="*70 + "\n")
    
    return {
        'all_results': all_results,
        'total_trades': total_trades,
        'total_pnl': total_pnl,
        'winrate': overall_winrate if total_trades > 0 else 0,
        'failed_symbols': failed_symbols
    }


# ==============================================================================
# SINGLE SYMBOL QUICK TEST
# ==============================================================================
def quick_test(symbol: str = "NVDA", period: str = "30d"):
    """Quick test on a single symbol"""
    
    print(f"\n🧪 QUICK TEST: {symbol}")
    
    # Load data
    df = load_data(symbol, period=period)
    
    # Config with looser settings for testing
    config = FPBConfig(
        min_gap_pct=2.0,         # Lower gap requirement for more trades
        risk_dollars=250.0,
        target_r1=1.5,
        target_r2=3.0,
    )
    
    # Run
    strategy = FirstPullbackBuy(config=config)
    results = strategy.run_backtest(df, symbol=symbol, filter_gap_days=True)
    
    # Save trades
    strategy.logger.save()
    
    return results


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    
    print("\n" + "🎯"*35)
    print("\n  FIRST PULLBACK BUY STRATEGY - BACKTEST RUNNER")
    print("\n" + "🎯"*35)
    
    # Option 1: Quick single-symbol test
    # results = quick_test("NVDA", period="60d")
    
    # Option 2: Multi-symbol backtest
    results = run_fpb_backtest(
        symbols=[
            # Tier 1: Known gappers
            "NVDA", "AMD", "TSLA", "META",
            # Tier 2: Momentum
            "COIN", "MSTR", "PLTR", 
            # Tier 3: Small caps
            "SOUN", "IONQ", "RKLB",
        ],
        period="60d",
        config=FPBConfig(
            min_gap_pct=3.0,      # 3% minimum gap
            risk_dollars=250.0,    # $250 risk per trade
            target_r1=1.5,         # Sell half at 1.5R
            target_r2=3.0,         # Runner at 3R
        )
    )
    
    print("✅ Backtest complete! Check logs/fpb_trades/ for CSV files.")