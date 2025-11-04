"""
ORB Basic Strategy – NaN-safe + VWAP + simple config (v3: ATR empty-guard)
"""

from dataclasses import dataclass
from datetime import time, datetime
import numpy as np
import pandas as pd


# -----------------------------
# Config object expected by backtest.py
# -----------------------------
@dataclass
class ORBConfig:
    # opening range (inclusive) — 2 bars
    or_start: str = "09:30"
    or_end: str = "09:32"
    # base window after OR
    base_start: str = "09:33"
    base_end: str = "09:39"
    # trade window
    trade_start: str = "09:40"
    trade_end: str = "10:45"

    # rules
    vwap_near_mult: float = 0.35   # mean |price - vwap| ≤ 0.35 × ATR
    max_base_ratio: float = 0.60   # base range ≤ 60% of OR width
    atr_length: int = 14

    # risk (placeholder; exits not implemented yet)
    risk_dollars: float = 100.0

    def t(self, hhmm: str) -> time:
        return datetime.strptime(hhmm, "%H:%M").time()


# -----------------------------
# Helpers
# -----------------------------
def ensure_intraday_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Build a per-session VWAP if missing; safe for NaNs/empty."""
    if df is None or len(df) == 0:
        return df

    # normalize column names to lowercase if needed
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        lc = c.lower()
        if c in df.columns and lc not in df.columns:
            df[lc] = df[c]

    need = ["high", "low", "close", "volume"]
    if any(col not in df.columns for col in need):
        return df

    # already has usable VWAP?
    if "vwap" in df.columns and df["vwap"].notna().any():
        return df

    if not isinstance(df.index, pd.DatetimeIndex):
        return df

    w = df.copy()
    w["session_date"] = w.index.date
    w["tp"] = (w["high"] + w["low"] + w["close"]) / 3.0
    w["vol"] = pd.to_numeric(w["volume"], errors="coerce").fillna(0.0)
    w["pv"] = w["tp"] * w["vol"]
    w["cum_pv"] = w.groupby("session_date")["pv"].cumsum()
    w["cum_vol"] = w.groupby("session_date")["vol"].cumsum().replace(0.0, np.nan)

    out = df.copy()
    out["vwap"] = w["cum_pv"] / w["cum_vol"]
    return out


def calc_atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    if any(col not in df.columns for col in ["high", "low", "close"]):
        return pd.Series(index=df.index, dtype=float)

    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(length).mean()


# -----------------------------
# Core strategy
# -----------------------------
def run(df: pd.DataFrame, cfg: ORBConfig):
    """
    Returns dict: {trades, winrate, profit_factor, total_pnl}
    (PnL is dummy until real exits are wired)
    """
    if df is None or len(df) == 0:
        print("[ORB] Empty dataframe; skipping.")
        return dict(trades=0, winrate=0, profit_factor=0, total_pnl=0.0)

    df = ensure_intraday_vwap(df.copy())
    df["atr"] = calc_atr(df, cfg.atr_length)

    # normalize to Eastern if tz-aware, then remove tz for between_time()
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df = df.tz_convert("America/New_York")
        df.index = df.index.tz_localize(None)

    or_start = cfg.t(cfg.or_start)
    or_end = cfg.t(cfg.or_end)
    base_start = cfg.t(cfg.base_start)
    base_end = cfg.t(cfg.base_end)
    trade_start = cfg.t(cfg.trade_start)
    trade_end = cfg.t(cfg.trade_end)

    results = []
    diag = {"days": 0, "hasOR": 0, "candidates": 0, "baseOK": 0,
            "vwapOK": 0, "entries": 0}

    # loop per session
    for day, day_df in df.groupby(df.index.date):
        diag["days"] += 1

        # restrict to RTH
        day_df = day_df.between_time("09:30", "16:00")
        if len(day_df) == 0:
            continue

        # opening range
        or_df = day_df.between_time(or_start, or_end)
        if len(or_df) == 0:
            continue
        diag["hasOR"] += 1
        or_high = float(or_df["high"].max())
        or_low = float(or_df["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        # base window
        base_df = day_df.between_time(base_start, base_end)
        if len(base_df) == 0:
            continue
        diag["candidates"] += 1

        # ATR guard (use last non-NaN ATR in base window) — with empty check
        atr_window = day_df.between_time(base_start, base_end)
        if len(atr_window) == 0 or "atr" not in atr_window.columns:
            continue
        atr_series = pd.to_numeric(atr_window["atr"], errors="coerce").dropna()
        if atr_series.empty:
            continue
        atr_value = float(atr_series.iloc[-1])
        if not np.isfinite(atr_value) or atr_value <= 0:
            continue

        # VWAP proximity (NaN-safe)
        if "vwap" not in base_df.columns:
            continue
        dist_series = (base_df["close"] - base_df["vwap"]).abs()
        dist_series = pd.to_numeric(dist_series, errors="coerce").dropna()
        if dist_series.empty:
            continue

        mean_dist = float(dist_series.mean())
        if not (mean_dist <= (cfg.vwap_near_mult * atr_value)):
            continue
        diag["vwapOK"] += 1

        # base tightness
        base_high, base_low = float(base_df["high"].max()), float(base_df["low"].min())
        base_range = base_high - base_low
        if base_range > cfg.max_base_ratio * or_range:
            continue
        diag["baseOK"] += 1

        # triggers in trade window
        trade_df = day_df.between_time(trade_start, trade_end)
        entry_long = (trade_df["high"] > or_high).any() if len(trade_df) else False
        entry_short = (trade_df["low"] < or_low).any() if len(trade_df) else False

        if entry_long or entry_short:
            diag["entries"] += 1
            side = "LONG" if entry_long else "SHORT"
            # placeholder PnL (replace later with proper exits)
            pnl = atr_value * 2.0 if side == "LONG" else -atr_value
            results.append(dict(day=str(day), side=side, or_high=or_high,
                                or_low=or_low, atr=atr_value, pnl=pnl))

    print(
        f"[DIAG] days={diag['days']} hasOR={diag['hasOR']} "
        f"candidates={diag['candidates']} baseOK={diag['baseOK']} "
        f"vwapOK={diag['vwapOK']} entries={diag['entries']}"
    )

    if not results:
        return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)

    total_pnl = float(sum(r["pnl"] for r in results))
    wins = sum(1 for r in results if r["pnl"] > 0)
    losses = sum(1 for r in results if r["pnl"] <= 0)
    winrate = wins / len(results) if results else 0.0
    pos_pnl = sum(r["pnl"] for r in results if r["pnl"] > 0)
    neg_pnl = sum(r["pnl"] for r in results if r["pnl"] < 0)
    profit_factor = (pos_pnl / abs(neg_pnl)) if neg_pnl < 0 else 0.0

    return dict(trades=len(results),
                winrate=winrate,
                profit_factor=profit_factor,
                total_pnl=total_pnl)
