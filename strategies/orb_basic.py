# File: strategies/orb_basic.py
# COMPLETE ORB STRATEGY - With Position Sizing, VWAP Stops, Exits, and Real PnL
# Based on Bootcamp Transcripts Rules

from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd


@dataclass
class ORBConfig:
    """ORB Configuration - can be loaded from YAML"""
    # Windows
    or_start: str = "09:30"
    or_end: str = "09:35"          # Opening Range: 1st 5-min candle
    base_start: str = "09:35"       
    base_end: str = "09:45"         # Base: 2 bars consolidation
    trade_start: str = "09:45"      # Trades can happen after base
    trade_end: str = "15:30"
    hard_flatten: str = "15:55"

    # ATR / EMAs
    atr_length: int = 14
    ema_len_fast: int = 9
    ema_len_slow: int = 20

    # Base gates (set to 0 to turn OFF)
    base_near_vwap_atr: float = 0.80
    base_tight_frac: float = 1.50

    # OR width gates (set to 0 to turn OFF)
    or_width_min_atr: float = 0.20
    or_width_max_atr: float = 5.00

    # Breakout volume (set to 0 to turn OFF)
    breakout_vol_mult: float = 0.0

    # Risk management
    risk_dollars: float = 250.0      # How much $ to risk per trade
    target_r1: float = 2.0           # First target: 2R (sell half)
    target_r2: float = 3.0           # Second target: 3R (sell rest)
    
    # VWAP stop buffer (in ATRs)
    vwap_stop_buffer_atr: float = 0.10  # Stop 0.1 ATR below/above VWAP
    
    # Other legacy settings
    stop_buf_vwap_atr: float = 0.10
    stop_buf_base_atr: float = 0.15
    min_stop_atr: float = 0.80
    max_vwap_dist_atr: float = 0.45

    def t(self, hhmm: str) -> time:
        """Convert time string to time object"""
        return datetime.strptime(hhmm, "%H:%M").time()


def calc_atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Calculate Average True Range"""
    if any(c not in df.columns for c in ["high", "low", "close"]):
        return pd.Series(index=df.index, dtype=float)
    
    high, low, close = df["high"], df["low"], df["close"]
    
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    
    return tr.rolling(length).mean()


def calc_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate intraday VWAP (resets each day)"""
    if df is None or len(df) == 0:
        return df
    
    need = ["high", "low", "close", "volume"]
    if any(col not in df.columns for col in need):
        return df
    
    if not isinstance(df.index, pd.DatetimeIndex):
        return df
    
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


def ema(series: pd.Series, length: int) -> pd.Series:
    """Calculate Exponential Moving Average"""
    return series.ewm(span=length, adjust=False).mean()


def simulate_trade(
    day_df: pd.DataFrame,
    side: str,
    entry_price: float,
    stop_price: float,
    target_r1_price: float,
    target_r2_price: float,
    shares: int,
    cfg: ORBConfig
) -> Dict[str, Any]:
    """
    Simulate a trade forward in time.
    Returns dict with exit_price, exit_time, pnl, exit_reason
    """
    
    trade_df = day_df[day_df.index >= day_df.index[0]]
    
    r_amount = abs(entry_price - stop_price)  # Risk amount per share
    shares_half = shares // 2
    shares_quarter = shares - shares_half
    
    remaining_shares = shares
    total_pnl = 0.0
    exit_reason = "NO_EXIT"
    exit_price = entry_price
    
    for idx, bar in trade_df.iterrows():
        bar_high = float(bar["high"])
        bar_low = float(bar["low"])
        bar_close = float(bar["close"])
        
        # Check stop loss first
        if side == "LONG":
            if bar_low <= stop_price:
                # Stopped out
                pnl = remaining_shares * (stop_price - entry_price)
                total_pnl += pnl
                exit_price = stop_price
                exit_reason = "STOP_LOSS"
                remaining_shares = 0
                break
                
            # Check R1 target (sell half)
            if remaining_shares == shares and bar_high >= target_r1_price:
                pnl = shares_half * (target_r1_price - entry_price)
                total_pnl += pnl
                remaining_shares = shares_quarter
                # Move stop to breakeven
                stop_price = entry_price
                
            # Check R2 target (sell rest)
            if remaining_shares > 0 and bar_high >= target_r2_price:
                pnl = remaining_shares * (target_r2_price - entry_price)
                total_pnl += pnl
                exit_price = target_r2_price
                exit_reason = "TARGET_R2"
                remaining_shares = 0
                break
                
        else:  # SHORT
            if bar_high >= stop_price:
                # Stopped out
                pnl = remaining_shares * (entry_price - stop_price)
                total_pnl += pnl
                exit_price = stop_price
                exit_reason = "STOP_LOSS"
                remaining_shares = 0
                break
                
            # Check R1 target (cover half)
            if remaining_shares == shares and bar_low <= target_r1_price:
                pnl = shares_half * (entry_price - target_r1_price)
                total_pnl += pnl
                remaining_shares = shares_quarter
                # Move stop to breakeven
                stop_price = entry_price
                
            # Check R2 target (cover rest)
            if remaining_shares > 0 and bar_low <= target_r2_price:
                pnl = remaining_shares * (entry_price - target_r2_price)
                total_pnl += pnl
                exit_price = target_r2_price
                exit_reason = "TARGET_R2"
                remaining_shares = 0
                break
    
    # If still in trade at end of day, close at hard flatten time or last bar
    if remaining_shares > 0:
        flatten_time = cfg.t(cfg.hard_flatten)
        last_bar = trade_df.iloc[-1]
        exit_price = float(last_bar["close"])
        
        if side == "LONG":
            pnl = remaining_shares * (exit_price - entry_price)
        else:
            pnl = remaining_shares * (entry_price - exit_price)
        
        total_pnl += pnl
        exit_reason = "EOD_FLATTEN"
    
    return {
        "exit_price": exit_price,
        "pnl": total_pnl,
        "exit_reason": exit_reason,
        "r_multiple": total_pnl / (shares * r_amount) if r_amount > 0 else 0
    }


def run(df: pd.DataFrame, cfg: ORBConfig) -> Dict[str, Any]:
    """
    Run ORB strategy on the dataframe.
    Returns dict with: trades, winrate, profit_factor, total_pnl
    """
    
    # ===== STEP 1: Validate and prepare data =====
    if df is None or len(df) == 0:
        print("[ERROR] Empty dataframe")
        return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)
    
    df = df.copy()
    
    # Normalize column names to lowercase
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns and c.lower() not in df.columns:
            df[c.lower()] = df[c]
    
    # ===== CRITICAL: Handle timezone conversion =====
    if isinstance(df.index, pd.DatetimeIndex):
        if df.index.tz is not None:
            print(f"[INFO] Converting from {df.index.tz} to US/Eastern")
            try:
                df.index = df.index.tz_convert('US/Eastern')
            except Exception as e:
                print(f"[WARNING] Timezone conversion failed: {e}")
                try:
                    df.index = df.index.tz_convert('America/New_York')
                except Exception:
                    print("[ERROR] Could not convert timezone")
                    return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)
        
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        
        if len(df) > 0:
            print(f"[INFO] First bar time after conversion: {df.index[0].time()}")
    
    # Check required columns
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"[ERROR] Missing columns: {missing}")
        return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)
    
    if not isinstance(df.index, pd.DatetimeIndex):
        print("[ERROR] Index is not DatetimeIndex")
        return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)
    
    # ===== STEP 2: Calculate indicators =====
    print("[INFO] Calculating indicators...")
    df = calc_vwap(df)
    df["atr"] = calc_atr(df, cfg.atr_length)
    
    if "close" in df.columns:
        df["ema_fast"] = ema(df["close"], cfg.ema_len_fast)
        df["ema_slow"] = ema(df["close"], cfg.ema_len_slow)
    
    # ===== STEP 3: Parse time windows =====
    or_start = cfg.t(cfg.or_start)
    or_end = cfg.t(cfg.or_end)
    base_start = cfg.t(cfg.base_start)
    base_end = cfg.t(cfg.base_end)
    trade_start = cfg.t(cfg.trade_start)
    trade_end = cfg.t(cfg.trade_end)
    
    # ===== STEP 4: Initialize diagnostics =====
    diag = {
        "days": 0,
        "hasOR": 0,
        "candidates": 0,
        "baseBarsOK": 0,
        "baseTightOK": 0,
        "vwapNearOK": 0,
        "vwapSideOK": 0,
        "orWidthMinOK": 0,
        "orWidthMaxOK": 0,
        "baseVolOK": 0,
        "volOK": 0,
        "entries": 0,
    }
    
    results: List[Dict[str, Any]] = []
    
    # ===== STEP 5: Process each trading day =====
    for day, day_df in df.groupby(df.index.date):
        diag["days"] += 1
        
        day_df = day_df.between_time("09:30", "16:00")
        if len(day_df) == 0:
            continue
        
        # ----- Opening Range (OR) - FIRST 5-MIN CANDLE -----
        or_df = day_df.between_time(or_start, or_end)
        if len(or_df) == 0:
            print(f"[{day}] No OR bars")
            continue
        
        diag["hasOR"] += 1
        
        or_high = float(or_df["high"].max())
        or_low = float(or_df["low"].min())
        or_range = or_high - or_low
        
        if or_range <= 0:
            print(f"[{day}] OR range is 0")
            continue
        
        # Get ATR value
        atr_in_or = or_df["atr"].dropna()
        if len(atr_in_or) > 0:
            atr_val = float(atr_in_or.iloc[-1])
        elif day_df["atr"].notna().any():
            atr_val = float(day_df["atr"].dropna().iloc[0])
        else:
            print(f"[{day}] No ATR available")
            continue
        
        if not np.isfinite(atr_val) or atr_val <= 0:
            print(f"[{day}] Invalid ATR: {atr_val}")
            continue
        
        # ----- Gate 1: OR Width (in ATRs) -----
        or_in_atr = or_range / atr_val
        
        if cfg.or_width_min_atr > 0:
            if or_in_atr < cfg.or_width_min_atr:
                print(f"[{day}] OR too narrow: {or_in_atr:.2f} ATR (min {cfg.or_width_min_atr})")
                continue
            diag["orWidthMinOK"] += 1
        else:
            diag["orWidthMinOK"] += 1
        
        if cfg.or_width_max_atr > 0:
            if or_in_atr > cfg.or_width_max_atr:
                print(f"[{day}] OR too wide: {or_in_atr:.2f} ATR (max {cfg.or_width_max_atr})")
                continue
            diag["orWidthMaxOK"] += 1
        else:
            diag["orWidthMaxOK"] += 1
        
        # ----- Base Window (Consolidation) -----
        base_df = day_df.between_time(base_start, base_end)
        if len(base_df) == 0:
            print(f"[{day}] No base bars")
            continue
        
        diag["candidates"] += 1
        
        if len(base_df) >= 1:
            diag["baseBarsOK"] += 1
        else:
            continue
        
        # ----- Gate 2: Base Tightness -----
        base_high = float(base_df["high"].max())
        base_low = float(base_df["low"].min())
        base_range = base_high - base_low
        
        if cfg.base_tight_frac > 0:
            tight_ratio = base_range / or_range if or_range > 0 else 999
            if tight_ratio > cfg.base_tight_frac:
                print(f"[{day}] Base too loose: {tight_ratio:.2f} vs OR (max {cfg.base_tight_frac})")
                continue
            diag["baseTightOK"] += 1
        else:
            diag["baseTightOK"] += 1
        
        # ----- Gate 3: Base near VWAP -----
        if cfg.base_near_vwap_atr > 0 and "vwap" in base_df.columns:
            dist = (base_df["close"] - base_df["vwap"]).abs()
            dist = pd.to_numeric(dist, errors="coerce").dropna()
            
            if len(dist) > 0:
                mean_dist_atr = float(dist.mean()) / atr_val
            else:
                mean_dist_atr = np.inf
            
            if mean_dist_atr > cfg.base_near_vwap_atr:
                print(f"[{day}] Base too far from VWAP: {mean_dist_atr:.2f} ATR (max {cfg.base_near_vwap_atr})")
                continue
            
            diag["vwapNearOK"] += 1
            
            # Check side of VWAP (70% threshold)
            above_ratio = float((base_df["close"] > base_df["vwap"]).mean())
            if not (above_ratio >= 0.7 or above_ratio <= 0.3):
                print(f"[{day}] Base not on one side of VWAP: {above_ratio:.1%} above")
                continue
            
            diag["vwapSideOK"] += 1
        else:
            diag["vwapNearOK"] += 1
            diag["vwapSideOK"] += 1
        
        # ----- Base Volume Check -----
        base_vol_ok = False
        base_avg_vol = 0.0
        
        if "volume" in base_df.columns and base_df["volume"].notna().any():
            base_avg_vol = float(base_df["volume"].dropna().mean())
            base_vol_ok = np.isfinite(base_avg_vol) and base_avg_vol > 0
            if base_vol_ok:
                diag["baseVolOK"] += 1
        
        # ----- Trade Window / Entry Detection -----
        trade_df = day_df.between_time(trade_start, trade_end)
        if len(trade_df) == 0:
            print(f"[{day}] No trade window bars")
            continue
        
        # Check for breakout
        entry_long = (trade_df["high"] > or_high).any()
        entry_short = (trade_df["low"] < or_low).any()
        
        if not entry_long and not entry_short:
            print(f"[{day}] No breakout")
            continue
        
        # ----- Gate 4: Breakout Volume -----
        vol_ok = True
        
        if cfg.breakout_vol_mult > 0 and base_vol_ok:
            brk_bar = None
            if entry_long:
                brk_bar = trade_df[trade_df["high"] > or_high].head(1)
            elif entry_short:
                brk_bar = trade_df[trade_df["low"] < or_low].head(1)
            
            if brk_bar is not None and len(brk_bar) > 0 and "volume" in brk_bar.columns:
                brk_vol = float(brk_bar["volume"].iloc[0])
                required_vol = cfg.breakout_vol_mult * base_avg_vol
                
                if not (np.isfinite(brk_vol) and brk_vol >= required_vol):
                    print(f"[{day}] Breakout volume too low: {brk_vol:.0f} < {required_vol:.0f}")
                    vol_ok = False
            else:
                vol_ok = False
        
        if vol_ok:
            diag["volOK"] += 1
        else:
            continue
        
        # ----- ENTRY! Calculate Position & PnL -----
        diag["entries"] += 1
        side = "LONG" if entry_long else "SHORT"
        
        # Find entry bar
        if side == "LONG":
            entry_bar = trade_df[trade_df["high"] > or_high].iloc[0]
            entry_price = or_high  # Enter at OR high breakout
        else:
            entry_bar = trade_df[trade_df["low"] < or_low].iloc[0]
            entry_price = or_low  # Enter at OR low breakdown
        
        # Get VWAP at entry time
        if "vwap" not in entry_bar or pd.isna(entry_bar["vwap"]):
            print(f"[{day}] No VWAP at entry")
            continue
        
        vwap_at_entry = float(entry_bar["vwap"])
        
        # CRITICAL: Stop goes at VWAP (per bootcamp rules!)
        vwap_buffer = cfg.vwap_stop_buffer_atr * atr_val
        
        if side == "LONG":
            stop_price = vwap_at_entry - vwap_buffer  # Stop UNDER VWAP
        else:
            stop_price = vwap_at_entry + vwap_buffer  # Stop OVER VWAP
        
        # Position sizing
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            print(f"[{day}] Invalid stop distance: {stop_distance}")
            continue
        
        shares = int(cfg.risk_dollars / stop_distance)
        if shares <= 0:
            print(f"[{day}] Invalid share count: {shares}")
            continue
        
        # Calculate R targets
        r_amount = stop_distance
        
        if side == "LONG":
            target_r1_price = entry_price + (cfg.target_r1 * r_amount)
            target_r2_price = entry_price + (cfg.target_r2 * r_amount)
        else:
            target_r1_price = entry_price - (cfg.target_r1 * r_amount)
            target_r2_price = entry_price - (cfg.target_r2 * r_amount)
        
        # Get trade bars (from entry forward)
        entry_idx = entry_bar.name
        trade_forward_df = day_df[day_df.index >= entry_idx]
        
        # Simulate the trade
        trade_result = simulate_trade(
            trade_forward_df,
            side,
            entry_price,
            stop_price,
            target_r1_price,
            target_r2_price,
            shares,
            cfg
        )
        
        pnl = trade_result["pnl"]
        exit_reason = trade_result["exit_reason"]
        r_multiple = trade_result["r_multiple"]
        
        results.append({
            "day": str(day),
            "side": side,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "vwap": vwap_at_entry,
            "shares": shares,
            "or_high": or_high,
            "or_low": or_low,
            "or_range": or_range,
            "atr": atr_val,
            "stop_distance": stop_distance,
            "r_amount": r_amount,
            "target_r1": target_r1_price,
            "target_r2": target_r2_price,
            "exit_reason": exit_reason,
            "r_multiple": r_multiple,
            "pnl": pnl
        })
        
        print(f"[{day}] ✓ ENTRY {side} @ ${entry_price:.2f} | "
              f"Stop: ${stop_price:.2f} (VWAP: ${vwap_at_entry:.2f}) | "
              f"Shares: {shares} | Risk: ${stop_distance * shares:.0f} | "
              f"PnL: ${pnl:.2f} ({r_multiple:.2f}R) | {exit_reason}")
    
    # ===== STEP 6: Print diagnostics =====
    print("\n" + "="*60)
    print("[DIAGNOSTICS]")
    print(f"  Days processed:        {diag['days']}")
    print(f"  Days with OR:          {diag['hasOR']}")
    print(f"  Candidates (has base): {diag['candidates']}")
    print(f"  Base bars OK:          {diag['baseBarsOK']}")
    print(f"  Base tightness OK:     {diag['baseTightOK']}")
    print(f"  Base near VWAP OK:     {diag['vwapNearOK']}")
    print(f"  Base side VWAP OK:     {diag['vwapSideOK']}")
    print(f"  OR width min OK:       {diag['orWidthMinOK']}")
    print(f"  OR width max OK:       {diag['orWidthMaxOK']}")
    print(f"  Base volume OK:        {diag['baseVolOK']}")
    print(f"  Breakout volume OK:    {diag['volOK']}")
    print(f"  TOTAL ENTRIES:         {diag['entries']}")
    print("="*60 + "\n")
    
    # ===== STEP 7: Calculate summary stats =====
    trades = len(results)
    
    if trades == 0:
        return dict(trades=0, winrate=0.0, profit_factor=0.0, total_pnl=0.0)
    
    total_pnl = sum(r["pnl"] for r in results)
    wins = sum(1 for r in results if r["pnl"] > 0)
    losses = sum(1 for r in results if r["pnl"] < 0)
    
    winrate = wins / trades if trades > 0 else 0.0
    
    pos_pnl = sum(r["pnl"] for r in results if r["pnl"] > 0)
    neg_pnl = sum(r["pnl"] for r in results if r["pnl"] < 0)
    profit_factor = (pos_pnl / abs(neg_pnl)) if neg_pnl < 0 else 0.0
    
    avg_r = sum(r["r_multiple"] for r in results) / trades if trades > 0 else 0.0
    
    print("\n" + "="*60)
    print("[TRADE PERFORMANCE]")
    print(f"  Total Trades:     {trades}")
    print(f"  Winners:          {wins} ({winrate*100:.1f}%)")
    print(f"  Losers:           {losses}")
    print(f"  Avg R-Multiple:   {avg_r:.2f}R")
    print(f"  Profit Factor:    {profit_factor:.2f}")
    print(f"  Total PnL:        ${total_pnl:.2f}")
    print("="*60 + "\n")
    
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "profit_factor": profit_factor,
        "total_pnl": total_pnl,
        "avg_r": avg_r,
        "results": results
    }