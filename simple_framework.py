# ==============================================================================
# SIMPLIFIED FRAMEWORK - EXACTLY WHAT BOOTCAMP TEACHES
# ==============================================================================
# After reading all transcripts, this is the REAL bootcamp ORB:
# - 15-minute opening range (not 5!)
# - Stop below OR low (simple!)
# - NO complex gates (they don't exist in bootcamp!)
# ==============================================================================

import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, Any, List, Optional
from pathlib import Path


# ==============================================================================
# TRADE LOGGER
# ==============================================================================
class TradeLogger:
    """Records every trade"""
    
    def __init__(self, log_dir: str = "logs/trades"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trades = []
        
    def log_trade(self, trade_data: Dict[str, Any]):
        """Log a single trade"""
        trade_data['logged_at'] = datetime.now().isoformat()
        self.trades.append(trade_data)
            
    def save(self, filename: Optional[str] = None):
        """Save all trades to CSV"""
        if len(self.trades) == 0:
            print("[TradeLogger] No trades to save")
            return None
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trades_{timestamp}.csv"
        filepath = self.log_dir / filename
        df = pd.DataFrame(self.trades)
        df.to_csv(filepath, index=False)
        print(f"[TradeLogger] Saved {len(self.trades)} trades to {filepath}")
        return filepath
        
    def get_trades_df(self) -> pd.DataFrame:
        """Get all trades as DataFrame"""
        if len(self.trades) == 0:
            return pd.DataFrame()
        return pd.DataFrame(self.trades)


# ==============================================================================
# PERFORMANCE ANALYZER
# ==============================================================================
class PerformanceAnalyzer:
    """Analyzes trade performance"""
    
    def __init__(self, trades_df: pd.DataFrame):
        self.df = trades_df
        
    def print_report(self):
        """Print performance report"""
        if len(self.df) == 0:
            print("No trades to analyze")
            return
            
        print("\n" + "="*70)
        print("📊 PERFORMANCE REPORT")
        print("="*70)
        
        winners = (self.df['pnl'] > 0).sum()
        losers = (self.df['pnl'] < 0).sum()
        total_pnl = self.df['pnl'].sum()
        
        print(f"Total Trades: {len(self.df)}")
        print(f"Winners: {winners} ({winners/len(self.df)*100:.1f}%)")
        print(f"Losers: {losers}")
        print(f"Total PnL: ${total_pnl:.2f}")
        
        if winners > 0:
            avg_win = self.df[self.df['pnl'] > 0]['pnl'].mean()
            print(f"Avg Win: ${avg_win:.2f}")
        if losers > 0:
            avg_loss = self.df[self.df['pnl'] < 0]['pnl'].mean()
            print(f"Avg Loss: ${avg_loss:.2f}")


# ==============================================================================
# GAP DAY IDENTIFIER
# ==============================================================================
def identify_gap_days(df: pd.DataFrame, min_gap_pct: float = 4.0) -> set:
    """Find days when stock gapped up 4%+"""
    if df.empty:
        return set()
    
    # Get daily OHLC
    daily = df.groupby(df.index.date).agg({
        'open': 'first',
        'close': 'last',
    })
    
    # Calculate gap %
    daily['prev_close'] = daily['close'].shift(1)
    daily['gap_pct'] = ((daily['open'] - daily['prev_close']) / daily['prev_close']) * 100
    
    # Find gap days
    gap_days = daily[daily['gap_pct'] >= min_gap_pct].index
    
    return set(gap_days)


# ==============================================================================
# SIMPLE ORB CONFIG
# ==============================================================================
@dataclass
class ORBConfig:
    """Simple ORB Configuration - Bootcamp Style"""
    # Time windows (from bootcamp)
    or_start: str = "09:30"
    or_end: str = "09:45"      # 15 minutes (bootcamp standard)
    trade_start: str = "09:45"  
    trade_end: str = "11:00"    # Morning session best
    
    # Risk (from bootcamp)
    risk_dollars: float = 250.0
    target_r1: float = 1.0      # Sell half at 1R
    target_r2: float = 2.0      # Trail rest to 2R
    
    # ATR for stop width
    atr_length: int = 14
    
    def t(self, hhmm: str) -> time:
        return datetime.strptime(hhmm, "%H:%M").time()


# ==============================================================================
# SIMPLE ORB STRATEGY - EXACTLY AS BOOTCAMP TEACHES
# ==============================================================================
class SimpleORB:
    """Bootcamp ORB - No complex gates!"""
    
    def __init__(self, config: ORBConfig, logger: Optional[TradeLogger] = None):
        self.cfg = config
        self.logger = logger or TradeLogger()
        
    def calc_atr(self, df: pd.DataFrame) -> pd.Series:
        """Calculate ATR"""
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([
            high - low, 
            (high - close.shift(1)).abs(), 
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(self.cfg.atr_length).mean()
        
    def run_backtest(self, df: pd.DataFrame, symbol: str = "SYMBOL", 
                     filter_gap_days: bool = True, min_gap_pct: float = 4.0) -> Dict[str, Any]:
        """Run the simple ORB strategy"""
        
        results = []
        
        # Only trade gap days if filtering
        if filter_gap_days:
            gap_days = identify_gap_days(df, min_gap_pct)
            print(f"   Found {len(gap_days)} gap days (≥{min_gap_pct}%)")
            if len(gap_days) == 0:
                return {'trades': 0, 'winrate': 0, 'profit_factor': 0, 'total_pnl': 0}
        else:
            gap_days = None
        
        # Add ATR
        df['atr'] = self.calc_atr(df)
        
        # Process each day
        for date, day_df in df.groupby(df.index.date):
            # Skip non-gap days
            if filter_gap_days and date not in gap_days:
                continue
                
            # Get Opening Range (15 minutes)
            or_df = day_df.between_time(self.cfg.t(self.cfg.or_start), self.cfg.t(self.cfg.or_end))
            if len(or_df) < 2:  # Need at least 2 candles
                continue
                
            or_high = float(or_df["high"].max())
            or_low = float(or_df["low"].min())
            or_range = or_high - or_low
            
            # Skip tiny ranges
            if or_range < 0.10:
                continue
            
            # Get ATR
            atr_val = day_df["atr"].dropna().iloc[-1] if day_df["atr"].dropna().any() else None
            if atr_val is None or atr_val <= 0:
                continue
                
            # Look for breakout
            trade_df = day_df.between_time(self.cfg.t(self.cfg.trade_start), self.cfg.t(self.cfg.trade_end))
            if len(trade_df) == 0:
                continue
                
            # Find first breakout
            long_break = trade_df[trade_df["high"] > or_high]
            short_break = trade_df[trade_df["low"] < or_low]
            
            if len(long_break) == 0 and len(short_break) == 0:
                continue
                
            # Take first signal
            if len(long_break) > 0 and len(short_break) > 0:
                if long_break.index[0] < short_break.index[0]:
                    side = "LONG"
                    entry_bar = long_break.iloc[0]
                else:
                    side = "SHORT"
                    entry_bar = short_break.iloc[0]
            elif len(long_break) > 0:
                side = "LONG"
                entry_bar = long_break.iloc[0]
            else:
                side = "SHORT"
                entry_bar = short_break.iloc[0]
            
            # SIMPLE ENTRY & STOPS (Bootcamp style!)
            if side == "LONG":
                entry_price = or_high
                stop_price = or_low - 0.02  # Just below OR
            else:
                entry_price = or_low
                stop_price = or_high + 0.02  # Just above OR
            
            # If OR is too wide (>2 ATR), tighten stop
            if or_range > (2 * atr_val):
                if side == "LONG":
                    stop_price = entry_price - atr_val
                else:
                    stop_price = entry_price + atr_val
            
            # Position sizing
            stop_distance = abs(entry_price - stop_price)
            if stop_distance <= 0:
                continue
            shares = int(self.cfg.risk_dollars / stop_distance)
            if shares <= 0:
                continue
            
            # Targets
            if side == "LONG":
                target_r1 = entry_price + (self.cfg.target_r1 * stop_distance)
                target_r2 = entry_price + (self.cfg.target_r2 * stop_distance)
            else:
                target_r1 = entry_price - (self.cfg.target_r1 * stop_distance)
                target_r2 = entry_price - (self.cfg.target_r2 * stop_distance)
            
            # Simulate trade
            trade_result = self.simulate_trade(
                day_df[day_df.index >= entry_bar.name],
                side, entry_price, stop_price, target_r1, target_r2, shares
            )
            
            # Record trade
            trade = {
                'symbol': symbol,
                'date': str(date),
                'side': side,
                'entry_price': entry_price,
                'stop_price': stop_price,
                'shares': shares,
                'or_high': or_high,
                'or_low': or_low,
                'target_r1': target_r1,
                'target_r2': target_r2,
                **trade_result
            }
            
            self.logger.log_trade(trade)
            results.append(trade)
        
        # Calculate stats
        if len(results) == 0:
            return {'trades': 0, 'winrate': 0, 'profit_factor': 0, 'total_pnl': 0}
        
        total_pnl = sum(r['pnl'] for r in results)
        wins = sum(1 for r in results if r['pnl'] > 0)
        winrate = wins / len(results)
        
        return {
            'trades': len(results),
            'winrate': winrate,
            'profit_factor': 0,
            'total_pnl': total_pnl,
            'results': results
        }
    
    def simulate_trade(self, df, side, entry, stop, t1, t2, shares):
        """Simulate trade execution"""
        
        shares_half = shares // 2
        remaining = shares
        total_pnl = 0
        exit_reason = "EOD"
        
        for idx, bar in df.iterrows():
            if side == "LONG":
                # Check stop
                if bar["low"] <= stop:
                    total_pnl = remaining * (stop - entry)
                    exit_reason = "STOP"
                    break
                # Check R1
                if remaining == shares and bar["high"] >= t1:
                    total_pnl += shares_half * (t1 - entry)
                    remaining -= shares_half
                    stop = entry  # Move to breakeven
                # Check R2
                if remaining > 0 and bar["high"] >= t2:
                    total_pnl += remaining * (t2 - entry)
                    exit_reason = "TARGET"
                    break
            else:  # SHORT
                # Check stop
                if bar["high"] >= stop:
                    total_pnl = remaining * (entry - stop)
                    exit_reason = "STOP"
                    break
                # Check R1
                if remaining == shares and bar["low"] <= t1:
                    total_pnl += shares_half * (entry - t1)
                    remaining -= shares_half
                    stop = entry
                # Check R2
                if remaining > 0 and bar["low"] <= t2:
                    total_pnl += remaining * (entry - t2)
                    exit_reason = "TARGET"
                    break
        
        # EOD exit
        if remaining > 0 and exit_reason == "EOD":
            last = float(df.iloc[-1]["close"])
            if side == "LONG":
                total_pnl += remaining * (last - entry)
            else:
                total_pnl += remaining * (entry - last)
        
        return {'pnl': total_pnl, 'exit_reason': exit_reason}


print("✅ Simplified Framework loaded!")
print("🎯 This is the REAL bootcamp ORB - simple, no complex gates!")