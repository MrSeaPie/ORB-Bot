# File: engine/backtest.py
import os
from dataclasses import asdict, fields
from typing import List, Dict, Any

import pandas as pd
import yfinance as yf
import yaml

from strategies.orb_basic import ORBConfig, run


def load_cfg(path: str = "config/paper.yaml") -> ORBConfig:
    """
    Load ORB settings from YAML if present; otherwise return defaults.
    IMPORTANT: Automatically maps ANY field defined in ORBConfig, so you
    can add new params to the dataclass and just drop them in YAML.
    """
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # accept only fields that exist in ORBConfig
        allowed = {f.name for f in fields(ORBConfig)}
        cfg_kwargs = {k: v for k, v in data.items() if k in allowed}
        return ORBConfig(**cfg_kwargs)
    return ORBConfig()


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Make sure columns are single-level and lowercased: open, high, low, close, volume."""
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance can return ('Open', ''), etc. Flatten to first level.
        df.columns = df.columns.get_level_values(0)

    # Lowercase canonical columns if present
    rename = {}
    for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
        if c in df.columns:
            rename[c] = c.lower()
    if rename:
        df = df.rename(columns=rename)

    # Ensure we have the expected OHLCV
    for need in ["open", "high", "low", "close", "volume"]:
        if need not in df.columns:
            df[need] = pd.Series(index=df.index, dtype=float)

    return df


def _fetch_bars(symbol: str, period: str = "60d", interval: str = "5m") -> pd.DataFrame:
    """
    Yahoo intraday downloader. 5m supports up to ~60 days.
    """
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            group_by="column",
            threads=True,
        )
    except Exception:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    df = _normalize_ohlcv(df)

    # yfinance may include pre/post; keep everything, strategy will trim RTH
    # Ensure DatetimeIndex tz-naive
    if isinstance(df.index, pd.DatetimeIndex):
        # make tz-naive if tz-aware
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)

    return df


def run_batch(symbols: List[str], cfg: ORBConfig) -> Dict[str, Any]:
    """
    Run the ORB strategy for each symbol and print a compact summary.
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
        print(
            f"{sym:>5}  trades={s['trades']:3d}  "
            f"win%={s['winrate']*100:5.2f}  "
            f"PF={s['profit_factor']:4.2f}  "
            f"PnL=${s['total_pnl']:.2f}"
        )

    return {"results": results, "total_pnl": total_pnl, "config": asdict(cfg)}
