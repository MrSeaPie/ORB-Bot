# File: engine/backtest.py
import os
from dataclasses import asdict, fields
from typing import List, Dict, Any

import pandas as pd
import yfinance as yf
import yaml

from strategies.orb_basic import ORBConfig, run


def load_cfg(path: str = "config/paper.yaml") -> ORBConfig:
    """Load ORB config from YAML file"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # Only accept fields that exist in ORBConfig
        allowed = {f.name for f in fields(ORBConfig)}
        cfg_kwargs = {k: v for k, v in data.items() if k in allowed}
        return ORBConfig(**cfg_kwargs)
    
    return ORBConfig()


def fetch_bars(symbol: str, period: str = "60d", interval: str = "5m") -> pd.DataFrame:
    """Download intraday data from Yahoo Finance"""
    print(f"[FETCH] Downloading {symbol} {interval} data...")
    
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=True,  # Simpler data
            prepost=False,     # Regular hours only
            progress=False,
        )
    except Exception as e:
        print(f"[ERROR] Failed to download {symbol}: {e}")
        return pd.DataFrame()
    
    if not isinstance(df, pd.DataFrame) or df.empty:
        print(f"[ERROR] Empty data for {symbol}")
        return pd.DataFrame()
    
    # Handle MultiIndex columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # Normalize column names
    rename = {}
    for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
        if c in df.columns:
            rename[c] = c.lower()
    
    if rename:
        df = df.rename(columns=rename)
    
    # Ensure we have OHLCV columns
    for need in ["open", "high", "low", "close", "volume"]:
        if need not in df.columns:
            df[need] = pd.Series(index=df.index, dtype=float)
    
    # CRITICAL: Force convert to US/Eastern
    if isinstance(df.index, pd.DatetimeIndex):
        if df.index.tz is None:
            # Assume UTC and convert
            print("[INFO] No timezone, assuming UTC and converting to US/Eastern")
            df.index = df.index.tz_localize('UTC').tz_convert('US/Eastern')
        else:
            print(f"[INFO] Converting from {df.index.tz} to US/Eastern")
            df.index = df.index.tz_convert('US/Eastern')
        
        # Make timezone-naive
        df.index = df.index.tz_localize(None)
        
        if len(df) > 0:
            print(f"[INFO] First bar: {df.index[0]} (time: {df.index[0].time()})")
    
    print(f"[FETCH] Got {len(df)} bars for {symbol}")
    return df


def run_batch(symbols: List[str], cfg: ORBConfig) -> Dict[str, Any]:
    """Run ORB backtest on multiple symbols"""
    results = {}
    total_pnl = 0.0
    
    print("\n" + "="*70)
    print("STARTING ORB BACKTEST")
    print("="*70)
    
    for sym in symbols:
        print(f"\n{'='*70}")
        print(f"SYMBOL: {sym}")
        print("="*70)
        
        df = fetch_bars(sym)
        
        if df.empty:
            results[sym] = dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)
            continue
        
        stats = run(df, cfg)
        results[sym] = stats
        total_pnl += float(stats.get("total_pnl", 0.0))
    
    # Print summary
    print("\n" + "="*70)
    print("BACKTEST SUMMARY")
    print("="*70)
    
    for sym in symbols:
        s = results[sym]
        print(
            f"{sym:>5}  trades={s['trades']:3d}  "
            f"win%={s['winrate']*100:5.2f}  "
            f"PF={s['profit_factor']:4.2f}  "
            f"PnL=${s['total_pnl']:.2f}"
        )
    
    print("="*70)
    print(f"TOTAL PnL: ${total_pnl:.2f}")
    print("="*70 + "\n")
    
    return {"results": results, "total_pnl": total_pnl, "config": asdict(cfg)}