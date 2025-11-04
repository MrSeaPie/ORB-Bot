import os
from dataclasses import asdict
from typing import List, Dict, Any

import pandas as pd
import yfinance as yf
import yaml

from strategies.orb_basic import ORBConfig, run


def load_cfg(path: str = "config/paper.yaml") -> ORBConfig:
    """
    Loads ORB settings from YAML if present; otherwise returns sensible defaults.
    Allowed keys:
      or_start, or_end, base_start, base_end, trade_start, trade_end,
      vwap_near_mult, max_base_ratio, atr_length, risk_dollars
    """
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cfg_kwargs = {}
        for k in [
            "or_start", "or_end", "base_start", "base_end",
            "trade_start", "trade_end",
            "vwap_near_mult", "max_base_ratio",
            "atr_length", "risk_dollars",
        ]:
            if k in data:
                cfg_kwargs[k] = data[k]
        return ORBConfig(**cfg_kwargs)
    # defaults
    return ORBConfig()


def _fetch_bars(symbol: str, period: str = "60d", interval: str = "5m") -> pd.DataFrame:
    """
    Yahoo intraday downloader. 5m supports up to ~60 days; 1m is only ~7-30 days.
    """
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False)
    if isinstance(df, pd.DataFrame) and len(df):
        # normalize columns (lowercase)
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            if c in df.columns and c.lower() not in df.columns:
                df[c.lower()] = df[c]
        return df
    return pd.DataFrame()


def run_batch(symbols: List[str], cfg: ORBConfig) -> Dict[str, Any]:
    """
    Runs the ORB strategy for each symbol and prints a compact summary.
    Returns a dict with per-symbol stats and total PnL.
    """
    results: Dict[str, Dict[str, float]] = {}
    total_pnl = 0.0

    for sym in symbols:
        df = _fetch_bars(sym)
        stats = run(df, cfg)
        results[sym] = stats
        total_pnl += float(stats.get("total_pnl", 0.0))

    # pretty print
    print("\n=== ORB Basic Backtest ===")
    for sym in symbols:
        s = results[sym]
        print(f"{sym:>5}  trades={s['trades']:3d}  win%={s['winrate']*100:5.2f}  PF={s['profit_factor']:4.2f}  PnL=${s['total_pnl']:.2f}")

    return {"results": results, "total_pnl": total_pnl, "config": asdict(cfg)}
