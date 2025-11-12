# ============================================================================
# RUN FRAMEWORK - WITH GAP-DAY FILTERING AND 1.0 ATR STOPS
# ============================================================================
# ✅ NEW: Only tests on days when stock actually gapped!
# ✅ Uses 1.0 ATR stops
# ✅ Uses scanner (or backup list)
# ============================================================================

import pandas as pd
import yfinance as yf
from framework import ORBStrategy, ORBConfig, TradeLogger, PerformanceAnalyzer
from scanner import find_daily_gappers


def fetch_bars(symbol: str, period: str = "60d", interval: str = "5m"):
    """Download stock data"""
    print(f"📥 Downloading {symbol}...")
    df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: c.lower() for c in df.columns})
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert('US/Eastern')
    else:
        df.index = df.index.tz_convert('US/Eastern')
    df.index = df.index.tz_localize(None)
    print(f"✅ Got {len(df)} bars for {symbol}")
    return df


# ============================================================================
# STRATEGY CONFIG WITH 1.0 ATR STOPS
# ============================================================================
cfg = ORBConfig(
    or_start="09:30",
    or_end="09:35",
    base_start="09:35",
    base_end="09:45",
    trade_start="09:45",
    trade_end="15:30",
    base_near_vwap_atr=1.0,
    base_tight_frac=0.5,
    or_width_min_atr=0,
    or_width_max_atr=0,
    breakout_vol_mult=0,
    risk_dollars=250.0,
    target_r1=2.0,
    target_r2=3.0,
    vwap_stop_buffer_atr=1.0,  # 1.0 ATR stops!
)

logger = TradeLogger(log_dir="logs/trades")
strategy = ORBStrategy(config=cfg, logger=logger)

# ============================================================================
# USE SCANNER TO GET WATCHLIST
# ============================================================================
WATCHLIST = find_daily_gappers()

print("\n" + "="*70)
print("🚀 STARTING BACKTEST - GAP DAYS ONLY!")
print("="*70)
print("💡 This will ONLY test on days when the stock actually gapped 3%+")
print("   (Just like your instructor trades!)")
print("="*70)

for symbol in WATCHLIST:
    print(f"\n{'='*70}")
    print(f"Testing {symbol}...")
    print("="*70)
    
    df = fetch_bars(symbol)
    if df.empty:
        continue
    
    # ========================================================================
    # 🎯 THE MAGIC: filter_gap_days=True
    # This tells the strategy to ONLY test on days when the stock gapped!
    # ========================================================================
    results = strategy.run_backtest(
        df, 
        filter_gap_days=True,  # ← THE KEY SETTING!
        min_gap_pct=3.0        # Only test on days with 3%+ gaps
    )
    
    print(f"\n📊 {symbol} Results:")
    print(f"  Trades: {results['trades']}")
    print(f"  Winrate: {results['winrate']*100:.1f}%")
    print(f"  Profit Factor: {results['profit_factor']:.2f}")
    print(f"  Total PnL: ${results['total_pnl']:.2f}")

print("\n" + "="*70)
print("💾 SAVING TRADES...")
print("="*70)
filepath = logger.save()
print(f"✅ Trades saved to: {filepath}")

print("\n" + "="*70)
print("📈 ANALYZING PERFORMANCE...")
print("="*70)
trades_df = logger.get_trades_df()
analyzer = PerformanceAnalyzer(trades_df)
analyzer.print_report()

print("\n✅ BACKTEST COMPLETE!")
print("\n💡 Remember: These results are ONLY from gap-up days!")
print("   This matches how your instructor actually trades!")