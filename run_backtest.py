# File: run_backtest.py
"""
ORB Backtest Runner
Run with: python run_backtest.py
"""

from engine.backtest import run_batch, load_cfg

# Your watchlist
WATCHLIST = ["AAPL", "NVDA", "TSLA", "AMD", "META", "MSFT"]

def main():
    print("\n🚀 ORB BACKTEST STARTING...\n")
    
    # Load config from YAML
    cfg = load_cfg("config/paper.yaml")
    
    print(f"Config loaded:")
    print(f"  OR Window: {cfg.or_start} - {cfg.or_end}")
    print(f"  Base Window: {cfg.base_start} - {cfg.base_end}")
    print(f"  Trade Window: {cfg.trade_start} - {cfg.trade_end}")
    print(f"  ATR Length: {cfg.atr_length}")
    print(f"  Base near VWAP gate: {cfg.base_near_vwap_atr} (0 = OFF)")
    print(f"  Base tightness gate: {cfg.base_tight_frac} (0 = OFF)")
    print(f"  OR width min gate: {cfg.or_width_min_atr} (0 = OFF)")
    print(f"  OR width max gate: {cfg.or_width_max_atr} (0 = OFF)")
    print(f"  Breakout volume gate: {cfg.breakout_vol_mult} (0 = OFF)")
    
    # Run backtest
    results = run_batch(WATCHLIST, cfg)
    
    print("\n✅ BACKTEST COMPLETE!")

if __name__ == "__main__":
    main()