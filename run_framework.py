# ============================================================================
# RUN FRAMEWORK - TESTING GAP-UP STOCKS
# ============================================================================

import pandas as pd
import yfinance as yf
from framework import ORBStrategy, ORBConfig, TradeLogger, PerformanceAnalyzer
from scanner import get_historical_gappers  # ← MAKE SURE THIS IS HERE!


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


# Strategy config
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
    vwap_stop_buffer_atr=0.10,
)

logger = TradeLogger(log_dir="logs/trades")
strategy = ORBStrategy(config=cfg, logger=logger)

# ============================================================================
# 🎯 CRITICAL: USE SCANNER HERE!
# ============================================================================

# OLD (WRONG):
# WATCHLIST = ["AAPL", "NVDA", "TSLA", "AMD", "META", "MSFT"]

# NEW (RIGHT):
WATCHLIST = get_historical_gappers()  # ← THIS CALLS THE SCANNER!

# ============================================================================

print("\n" + "="*70)
print("🚀 STARTING BACKTEST")
print("="*70)

for symbol in WATCHLIST:
    print(f"\n{'='*70}")
    print(f"Testing {symbol}...")
    print("="*70)
    
    df = fetch_bars(symbol)
    if df.empty:
        continue
    
    results = strategy.run_backtest(df)
    
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