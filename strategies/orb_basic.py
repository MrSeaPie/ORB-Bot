# File: strategies/orb_basic.py
# ORB Basic – debug-friendly gates, DIAG counters, volume gate OFF when breakout_vol_mult <= 0

from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, Any, List

import numpy as np
import pandas as pd


# -----------------------------
# Config object (populated via YAML in backtest.load_cfg)
# -----------------------------
@dataclass
class ORBConfig:
    # Windows
    or_start: str = "09:30"
    or_end: str = "09:32"
    base_start: str = "09:33"
    base_end: str = "09:40"
    trade_start: str = "09:40"
    trade_end: str = "10:45"
    hard_flatten: str = "11:05"

    # ATR / EMAs
    atr_length: int = 14
    ema_len_fast: int = 9
    ema_len_slow: int = 20

    # Base gates (debug-loose by YAML if needed)
    base_near_vwap_atr: float = 0.30   # mean |price - vwap| / ATR ≤ this
    base_tight_frac: float = 0.60      # (base_range / OR_range) ≤ this

    # OR width gates (in ATRs)
    or_width_min_atr: float = 0.20
    or_width_max_atr: float = 3.00

    # Breakout volume multiplier (OFF when <= 0)
    breakout_vol_mult: float = 1.20

    # Risk
    stop_buf_vwap_atr: float = 0.10
    stop_buf_base_atr: float = 0.15
    min_stop_atr: float = 0.80
    risk_dollars: float = 100.0

    # Optional extra (not required by logic, kept for compatibility)
    max_vwap_dist_atr: float = 0.45

    def t(self, hhmm: str) -> time:
        return datetime.strptime(hhmm, "%H:%M").time()


# -----------------------------
# Indicators / helpers
# -----------------------------
def ensure_intraday_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Per-session VWAP; no-op if missing columns or index type."""
    if df is None or len(df) == 0:
        return df

    # normalize lowercase columns
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        lc = c.lower()
        if c in df.columns and lc not in df.columns:
            df[lc] = df[c]

    need = ["high", "low", "close", "volume"]
    if any(col not in df.columns for col in need):
        return df

    if not isinstance(df.index, pd.DatetimeIndex):
        return df

    # if already has vwap populated, keep it
    if "vwap" in df.columns and df["vwap"].notna().any():
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
    if any(c not in df.columns for c in ["high", "low", "close"]):
        return pd.Series(index=df.index, dtype=float)
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


# -----------------------------
# Core strategy
# -----------------------------
def run(df: pd.DataFrame, cfg: ORBConfig) -> Dict[str, Any]:
    """
    Returns: dict(trades, winrate, profit_factor, total_pnl)
    Note: PnL here is placeholder (0.0). We’re debugging gates/entries.
    """
    if df is None or len(df) == 0:
        return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)

    # Normalize cols, add indicators
    df = ensure_intraday_vwap(df.copy())
    if not isinstance(df.index, pd.DatetimeIndex):
        return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)

    # lowercased columns expected
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns and c.lower() not in df.columns:
            df[c.lower()] = df[c]

    df["atr"] = calc_atr(df, cfg.atr_length)
    if "close" in df.columns:
        df["ema_fast"] = ema(df["close"], cfg.ema_len_fast)
        df["ema_slow"] = ema(df["close"], cfg.ema_len_slow)

    or_start = cfg.t(cfg.or_start)
    or_end = cfg.t(cfg.or_end)
    base_start = cfg.t(cfg.base_start)
    base_end = cfg.t(cfg.base_end)
    trade_start = cfg.t(cfg.trade_start)
    trade_end = cfg.t(cfg.trade_end)

    diag_keys = [
        "days", "hasOR", "candidates",
        "baseBarsOK", "baseTightOK",
        "vwapNearOK", "vwapSideOK",
        "orWidthMinOK", "orWidthMaxOK",
        "baseVolOK", "volOK",
        "entries",
    ]
    diag = {k: 0 for k in diag_keys}

    results: List[Dict[str, Any]] = []

    # group per session (by date)
    for day, day_df in df.groupby(df.index.date):
        diag["days"] += 1

        # restrict to RTH
        day_df = day_df.between_time("09:30", "16:00")
        if len(day_df) == 0:
            continue

        # Opening range (2 bars 09:30–09:32 by default)
        or_df = day_df.between_time(or_start, or_end)
        if len(or_df) == 0:
            continue
        diag["hasOR"] += 1

        or_high = float(or_df["high"].max())
        or_low = float(or_df["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        # ATR snapshot (use last valid in OR window or early base)
        atr_in_or = or_df["atr"].dropna()
        atr_val = float(atr_in_or.iloc[-1]) if len(atr_in_or) else float(day_df["atr"].dropna().iloc[0]) if day_df["atr"].notna().any() else np.nan
        if not np.isfinite(atr_val) or atr_val <= 0:
            continue

        # OR width gates (in ATRs)
        or_in_atr = or_range / atr_val if atr_val > 0 else np.nan
        if np.isfinite(or_in_atr):
            if or_in_atr >= cfg.or_width_min_atr:
                diag["orWidthMinOK"] += 1
            else:
                continue
            if or_in_atr <= cfg.or_width_max_atr:
                diag["orWidthMaxOK"] += 1
            else:
                continue

        # Base window
        base_df = day_df.between_time(base_start, base_end)
        if len(base_df) == 0:
            continue
        diag["candidates"] += 1

        # Base must have enough bars (>= 1 bar is fine)
        if len(base_df) >= 1:
            diag["baseBarsOK"] += 1
        else:
            continue

        # Base tightness vs OR (range ratio)
        base_high = float(base_df["high"].max())
        base_low = float(base_df["low"].min())
        base_range = base_high - base_low
        tight_ok = (or_range > 0) and (base_range / or_range <= cfg.base_tight_frac)
        if tight_ok:
            diag["baseTightOK"] += 1
        else:
            # still continue to evaluate; in debug you may override with huge base_tight_frac
            continue

        # Base proximity to VWAP (mean abs distance in ATRs)
        if "vwap" in base_df.columns:
            dist = (base_df["close"] - base_df["vwap"]).abs()
            dist = pd.to_numeric(dist, errors="coerce").dropna()
            if len(dist):
                mean_dist_atr = float(dist.mean()) / atr_val if atr_val > 0 else np.inf
            else:
                mean_dist_atr = np.inf
        else:
            mean_dist_atr = np.inf

        if mean_dist_atr <= cfg.base_near_vwap_atr:
            diag["vwapNearOK"] += 1
            # side check: ensure base sits mostly on one side of VWAP
            if "vwap" in base_df.columns:
                above_ratio = float((base_df["close"] > base_df["vwap"]).mean())
                side_ok = (above_ratio >= 0.7) or (above_ratio <= 0.3)
            else:
                side_ok = True  # if no vwap, don't block in debug
            if side_ok:
                diag["vwapSideOK"] += 1
            else:
                continue
        else:
            continue

        # Trade window / triggers
        trade_df = day_df.between_time(trade_start, trade_end)
        if len(trade_df) == 0:
            continue

        entry_long = (trade_df["high"] > or_high).any()
        entry_short = (trade_df["low"] < or_low).any()

        # ---- Breakout volume gate (OFF when cfg.breakout_vol_mult <= 0) ----
        # If OFF, vol_ok = True. If ON, require breakout bar volume >= X * base average.
        vol_ok = True
        base_vol_ok = True
        if getattr(cfg, "breakout_vol_mult", 0.0) and cfg.breakout_vol_mult > 0:
            # baseline = average base volume
            if "volume" in base_df.columns and base_df["volume"].notna().any():
                base_avg_vol = float(base_df["volume"].dropna().mean())
                base_vol_ok = np.isfinite(base_avg_vol) and base_avg_vol > 0
                if base_vol_ok:
                    diag["baseVolOK"] += 1
            else:
                base_vol_ok = False

            if entry_long or entry_short:
                brk_bar = None
                if entry_long:
                    brk_bar = trade_df[trade_df["high"] > or_high].head(1)
                elif entry_short:
                    brk_bar = trade_df[trade_df["low"] < or_low].head(1)

                if brk_bar is not None and len(brk_bar) and "volume" in brk_bar.columns:
                    brk_vol = float(brk_bar["volume"].iloc[0])
                    if not (base_vol_ok and np.isfinite(brk_vol) and brk_vol >= cfg.breakout_vol_mult * base_avg_vol):
                        vol_ok = False
                else:
                    vol_ok = False
        else:
            # gate is OFF in debug mode
            diag["baseVolOK"] += 1  # consider base volume "ok" for DIAG visibility
            vol_ok = True

        if vol_ok:
            diag["volOK"] += 1

        # Final entry decision
        if (entry_long or entry_short) and vol_ok:
            diag["entries"] += 1
            side = "LONG" if entry_long else "SHORT"
            # Placeholder trade record (PnL = 0 while we debug gates)
            results.append(dict(day=str(day), side=side, pnl=0.0))

    # Print DIAG like your examples
    print(
        "[DIAG] days={days} hasOR={hasOR} candidates={candidates} "
        "baseBarsOK={baseBarsOK} baseTightOK={baseTightOK} "
        "vwapNearOK={vwapNearOK} vwapSideOK={vwapSideOK} "
        "orWidthMinOK={orWidthMinOK} orWidthMaxOK={orWidthMaxOK} "
        "baseVolOK={baseVolOK} volOK={volOK} entries={entries}".format(**diag)
    )

    # Summaries
    trades = len(results)
    if trades == 0:
        return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)

    total_pnl = float(sum(r["pnl"] for r in results))
    wins = sum(1 for r in results if r["pnl"] > 0)
    losses = sum(1 for r in results if r["pnl"] < 0)
    winrate = wins / trades if trades else 0.0
    pos_pnl = sum(r["pnl"] for r in results if r["pnl"] > 0)
    neg_pnl = sum(r["pnl"] for r in results if r["pnl"] < 0)
    profit_factor = (pos_pnl / abs(neg_pnl)) if neg_pnl < 0 else 0.0

    return dict(trades=trades, winrate=winrate, profit_factor=profit_factor, total_pnl=total_pnl)
