# ==============================================================================
# ALL-IN-ONE TRADING FRAMEWORK - FIXED VERSION
# ==============================================================================
# Bug fixed: Gates now properly respect 0 value (disabled state)
# ==============================================================================

import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from datetime import datetime, time
from typing import Dict, Any, List, Optional
import json
import os
from pathlib import Path


# ==============================================================================
# PART 1: TRADE LOGGER
# ==============================================================================
class TradeLogger:
    """Records every trade with full context"""
    
    def __init__(self, log_dir: str = "logs/trades"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trades = []
        
    def log_trade(self, trade_data: Dict[str, Any]):
        """Log a single trade"""
        trade_data['logged_at'] = datetime.now().isoformat()
        self.trades.append(trade_data)
        if len(self.trades) % 10 == 0:
            self.save()
            
    def save(self, filename: Optional[str] = None):
        """Save all trades to CSV"""
        if len(self.trades) == 0:
            print("[TradeLogger] No trades to save")
            return
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
# PART 2: PERFORMANCE ANALYZER
# ==============================================================================
class PerformanceAnalyzer:
    """Analyzes trade logs to find patterns"""
    
    def __init__(self, trades_df: pd.DataFrame):
        self.df = trades_df
        
    def generate_report(self) -> Dict[str, Any]:
        """Generate full performance report"""
        if len(self.df) == 0:
            return {"error": "No trades to analyze"}
            
        report = {}
        
        # Overall stats
        report['overall'] = {
            'total_trades': len(self.df),
            'winners': int((self.df['pnl'] > 0).sum()),
            'losers': int((self.df['pnl'] < 0).sum()),
            'winrate': float((self.df['pnl'] > 0).mean()),
            'total_pnl': float(self.df['pnl'].sum()),
            'avg_win': float(self.df[self.df['pnl'] > 0]['pnl'].mean()) if (self.df['pnl'] > 0).any() else 0,
            'avg_loss': float(self.df[self.df['pnl'] < 0]['pnl'].mean()) if (self.df['pnl'] < 0).any() else 0,
            'avg_r_multiple': float(self.df['r_multiple'].mean()) if 'r_multiple' in self.df.columns else 0,
        }
        
        # Profit factor
        pos_pnl = self.df[self.df['pnl'] > 0]['pnl'].sum()
        neg_pnl = abs(self.df[self.df['pnl'] < 0]['pnl'].sum())
        report['overall']['profit_factor'] = float(pos_pnl / neg_pnl) if neg_pnl > 0 else 0.0
        
        # Per-symbol stats
        if 'symbol' in self.df.columns:
            symbol_stats = self.df.groupby('symbol').agg({'pnl': ['count', 'sum', 'mean']}).round(2)
            symbol_stats.columns = ['trades', 'total_pnl', 'avg_pnl']
            symbol_stats = symbol_stats.sort_values('total_pnl', ascending=False)
            report['by_symbol'] = symbol_stats.to_dict('index')
        
        # Per-side stats
        if 'side' in self.df.columns:
            side_stats = self.df.groupby('side').agg({'pnl': ['count', 'sum', lambda x: (x > 0).mean()]}).round(2)
            side_stats.columns = ['trades', 'total_pnl', 'winrate']
            report['by_side'] = side_stats.to_dict('index')
        
        # Exit reason stats
        if 'exit_reason' in self.df.columns:
            exit_stats = self.df.groupby('exit_reason').agg({'pnl': ['count', 'mean']}).round(2)
            exit_stats.columns = ['count', 'avg_pnl']
            report['by_exit_reason'] = exit_stats.to_dict('index')
        
        return report
        
    def print_report(self):
        """Print formatted report"""
        report = self.generate_report()
        if 'error' in report:
            print(f"\n❌ {report['error']}\n")
            return
            
        print("\n" + "="*70)
        print("📊 PERFORMANCE REPORT")
        print("="*70)
        
        o = report['overall']
        print(f"\n📈 OVERALL PERFORMANCE:")
        print(f"  Total Trades:     {o['total_trades']}")
        print(f"  Winners:          {o['winners']} ({o['winrate']*100:.1f}%)")
        print(f"  Losers:           {o['losers']}")
        print(f"  Total PnL:        ${o['total_pnl']:.2f}")
        print(f"  Avg Win:          ${o['avg_win']:.2f}")
        print(f"  Avg Loss:         ${o['avg_loss']:.2f}")
        print(f"  Avg R-Multiple:   {o['avg_r_multiple']:.2f}R")
        print(f"  Profit Factor:    {o['profit_factor']:.2f}")
        
        if 'by_symbol' in report and report['by_symbol']:
            print(f"\n💰 BEST PERFORMING STOCKS:")
            for symbol, stats in list(report['by_symbol'].items())[:5]:
                print(f"  {symbol:>6}: {stats['trades']:3.0f} trades | PnL: ${stats['total_pnl']:>8.2f}")
        
        if 'by_side' in report:
            print(f"\n📊 LONG vs SHORT:")
            for side, stats in report['by_side'].items():
                print(f"  {side:>6}: {stats['trades']:3.0f} trades | PnL: ${stats['total_pnl']:>8.2f} | WR: {stats['winrate']*100:>5.1f}%")
        
        if 'by_exit_reason' in report:
            print(f"\n🚪 EXIT REASONS:")
            for reason, stats in report['by_exit_reason'].items():
                print(f"  {reason:>15}: {stats['count']:3.0f}x | Avg PnL: ${stats['avg_pnl']:>7.2f}")
        
        print("\n" + "="*70 + "\n")


# ==============================================================================
# PART 3: BASE STRATEGY (TEMPLATE)
# ==============================================================================
class BaseStrategy:
    """Template for all strategies"""
    
    def __init__(self, name: str, logger: Optional[TradeLogger] = None):
        self.name = name
        self.logger = logger or TradeLogger()
        
    def scan(self, df: pd.DataFrame, date: Any) -> bool:
        """Check if setup is valid"""
        raise NotImplementedError("Implement scan() in your strategy")
        
    def calculate_entry(self, df: pd.DataFrame, date: Any) -> Optional[Dict[str, Any]]:
        """Calculate entry price, stop, size"""
        raise NotImplementedError("Implement calculate_entry() in your strategy")
        
    def simulate_exit(self, day_df: pd.DataFrame, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate trade to exit"""
        raise NotImplementedError("Implement simulate_exit() in your strategy")
        
    def run_backtest(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Run strategy on historical data"""
        results = []
        
        for date, day_df in df.groupby(df.index.date):
            if not self.scan(day_df, date):
                continue
            entry = self.calculate_entry(day_df, date)
            if entry is None:
                continue
            exit_result = self.simulate_exit(day_df, entry)
            trade = {**entry, **exit_result, 'date': str(date)}
            self.logger.log_trade(trade)
            results.append(trade)
            
        if len(results) == 0:
            return {'trades': 0, 'winrate': 0, 'profit_factor': 0, 'total_pnl': 0}
            
        total_pnl = sum(r['pnl'] for r in results)
        wins = sum(1 for r in results if r['pnl'] > 0)
        winrate = wins / len(results)
        pos_pnl = sum(r['pnl'] for r in results if r['pnl'] > 0)
        neg_pnl = abs(sum(r['pnl'] for r in results if r['pnl'] < 0))
        profit_factor = pos_pnl / neg_pnl if neg_pnl > 0 else 0
        
        return {
            'trades': len(results),
            'wins': wins,
            'losses': len(results) - wins,
            'winrate': winrate,
            'profit_factor': profit_factor,
            'total_pnl': total_pnl,
            'results': results
        }


# ==============================================================================
# PART 4: ORB CONFIG
# ==============================================================================
@dataclass
class ORBConfig:
    """ORB Strategy Configuration"""
    or_start: str = "09:30"
    or_end: str = "09:35"
    base_start: str = "09:35"
    base_end: str = "09:45"
    trade_start: str = "09:45"
    trade_end: str = "15:30"
    hard_flatten: str = "15:55"
    atr_length: int = 14
    ema_len_fast: int = 9
    ema_len_slow: int = 20
    base_near_vwap_atr: float = 0
    base_tight_frac: float = 0
    or_width_min_atr: float = 0
    or_width_max_atr: float = 0
    breakout_vol_mult: float = 0.0
    risk_dollars: float = 250.0
    target_r1: float = 2.0
    target_r2: float = 3.0
    vwap_stop_buffer_atr: float = 0.3
    
    def t(self, hhmm: str) -> time:
        return datetime.strptime(hhmm, "%H:%M").time()


# ==============================================================================
# PART 5: ORB STRATEGY - FIXED GATE LOGIC
# ==============================================================================
class ORBStrategy(BaseStrategy):
    """Opening Range Breakout Strategy"""
    
    def __init__(self, config: ORBConfig, logger: Optional[TradeLogger] = None):
        super().__init__(name="ORB", logger=logger)
        self.cfg = config
        
    def calc_atr(self, df: pd.DataFrame) -> pd.Series:
        """Calculate ATR"""
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        return tr.rolling(self.cfg.atr_length).mean()
        
    def calc_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate VWAP"""
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
        
    def scan(self, day_df: pd.DataFrame, date: Any) -> bool:
        """Check if valid setup"""
        or_df = day_df.between_time(self.cfg.t(self.cfg.or_start), self.cfg.t(self.cfg.or_end))
        base_df = day_df.between_time(self.cfg.t(self.cfg.base_start), self.cfg.t(self.cfg.base_end))
        trade_df = day_df.between_time(self.cfg.t(self.cfg.trade_start), self.cfg.t(self.cfg.trade_end))
        return len(or_df) > 0 and len(base_df) > 0 and len(trade_df) > 0
        
    def calculate_entry(self, day_df: pd.DataFrame, date: Any) -> Optional[Dict[str, Any]]:
        """Calculate entry if gates pass - FIXED GATE LOGIC"""
        day_df = self.calc_vwap(day_df)
        day_df["atr"] = self.calc_atr(day_df)
        
        or_df = day_df.between_time(self.cfg.t(self.cfg.or_start), self.cfg.t(self.cfg.or_end))
        if len(or_df) == 0:
            return None
            
        or_high = float(or_df["high"].max())
        or_low = float(or_df["low"].min())
        or_range = or_high - or_low
        
        # Get ATR value
        atr_in_or = or_df["atr"].dropna()
        if len(atr_in_or) > 0:
            atr_val = float(atr_in_or.iloc[-1])
        else:
            # Fallback to any ATR in the day
            all_atr = day_df["atr"].dropna()
            if len(all_atr) > 0:
                atr_val = float(all_atr.iloc[0])
            else:
                return None
        
        if not np.isfinite(atr_val) or atr_val <= 0:
            return None
            
        # GATE 1: OR WIDTH - FIXED LOGIC
        or_in_atr = or_range / atr_val
        
        # Only check min gate if it's enabled (> 0)
        if self.cfg.or_width_min_atr > 0:
            if or_in_atr < self.cfg.or_width_min_atr:
                return None
        
        # Only check max gate if it's enabled (> 0)
        if self.cfg.or_width_max_atr > 0:
            if or_in_atr > self.cfg.or_width_max_atr:
                return None
            
        base_df = day_df.between_time(self.cfg.t(self.cfg.base_start), self.cfg.t(self.cfg.base_end))
        if len(base_df) == 0:
            return None
            
        base_high = float(base_df["high"].max())
        base_low = float(base_df["low"].min())
        base_range = base_high - base_low
        
        # GATE 2: BASE TIGHTNESS - FIXED LOGIC
        if self.cfg.base_tight_frac > 0:
            tight_ratio = base_range / or_range if or_range > 0 else 999
            if tight_ratio > self.cfg.base_tight_frac:
                return None
                
        # GATE 3: BASE NEAR VWAP - FIXED LOGIC
        if self.cfg.base_near_vwap_atr > 0:
            if "vwap" in base_df.columns:
                dist = (base_df["close"] - base_df["vwap"]).abs()
                dist = pd.to_numeric(dist, errors="coerce").dropna()
                if len(dist) > 0:
                    mean_dist_atr = float(dist.mean()) / atr_val
                    if mean_dist_atr > self.cfg.base_near_vwap_atr:
                        return None
                    
        trade_df = day_df.between_time(self.cfg.t(self.cfg.trade_start), self.cfg.t(self.cfg.trade_end))
        if len(trade_df) == 0:
            return None
            
        entry_long = (trade_df["high"] > or_high).any()
        entry_short = (trade_df["low"] < or_low).any()
        if not entry_long and not entry_short:
            return None
            
        side = "LONG" if entry_long else "SHORT"
        if side == "LONG":
            entry_bar = trade_df[trade_df["high"] > or_high].iloc[0]
            entry_price = or_high
        else:
            entry_bar = trade_df[trade_df["low"] < or_low].iloc[0]
            entry_price = or_low
            
        if "vwap" not in entry_bar or pd.isna(entry_bar["vwap"]):
            return None
        vwap_at_entry = float(entry_bar["vwap"])
        
        vwap_buffer = self.cfg.vwap_stop_buffer_atr * atr_val
        if side == "LONG":
            stop_price = vwap_at_entry - vwap_buffer
        else:
            stop_price = vwap_at_entry + vwap_buffer
            
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return None
        shares = int(self.cfg.risk_dollars / stop_distance)
        if shares <= 0:
            return None
            
        r_amount = stop_distance
        if side == "LONG":
            target_r1_price = entry_price + (self.cfg.target_r1 * r_amount)
            target_r2_price = entry_price + (self.cfg.target_r2 * r_amount)
        else:
            target_r1_price = entry_price - (self.cfg.target_r1 * r_amount)
            target_r2_price = entry_price - (self.cfg.target_r2 * r_amount)
            
        return {
            'symbol': 'SYMBOL',
            'side': side,
            'entry_price': entry_price,
            'entry_time': str(entry_bar.name.time()),
            'stop_price': stop_price,
            'vwap': vwap_at_entry,
            'shares': shares,
            'or_high': or_high,
            'or_low': or_low,
            'or_range': or_range,
            'or_in_atr': or_in_atr,
            'base_range': base_range,
            'atr': atr_val,
            'stop_distance': stop_distance,
            'r_amount': r_amount,
            'target_r1': target_r1_price,
            'target_r2': target_r2_price,
        }
        
    def simulate_exit(self, day_df: pd.DataFrame, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate trade to exit"""
        side = entry['side']
        entry_price = entry['entry_price']
        stop_price = entry['stop_price']
        shares = entry['shares']
        target_r1_price = entry['target_r1']
        target_r2_price = entry['target_r2']
        r_amount = entry['r_amount']
        
        shares_half = shares // 2
        shares_quarter = shares - shares_half
        remaining_shares = shares
        total_pnl = 0.0
        exit_reason = "NO_EXIT"
        exit_price = entry_price
        
        for idx, bar in day_df.iterrows():
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])
            
            if side == "LONG":
                if bar_low <= stop_price:
                    pnl = remaining_shares * (stop_price - entry_price)
                    total_pnl += pnl
                    exit_price = stop_price
                    exit_reason = "STOP_LOSS"
                    remaining_shares = 0
                    break
                if remaining_shares == shares and bar_high >= target_r1_price:
                    pnl = shares_half * (target_r1_price - entry_price)
                    total_pnl += pnl
                    remaining_shares = shares_quarter
                    stop_price = entry_price
                if remaining_shares > 0 and bar_high >= target_r2_price:
                    pnl = remaining_shares * (target_r2_price - entry_price)
                    total_pnl += pnl
                    exit_price = target_r2_price
                    exit_reason = "TARGET_R2"
                    remaining_shares = 0
                    break
            else:
                if bar_high >= stop_price:
                    pnl = remaining_shares * (entry_price - stop_price)
                    total_pnl += pnl
                    exit_price = stop_price
                    exit_reason = "STOP_LOSS"
                    remaining_shares = 0
                    break
                if remaining_shares == shares and bar_low <= target_r1_price:
                    pnl = shares_half * (entry_price - target_r1_price)
                    total_pnl += pnl
                    remaining_shares = shares_quarter
                    stop_price = entry_price
                if remaining_shares > 0 and bar_low <= target_r2_price:
                    pnl = remaining_shares * (entry_price - target_r2_price)
                    total_pnl += pnl
                    exit_price = target_r2_price
                    exit_reason = "TARGET_R2"
                    remaining_shares = 0
                    break
        
        if remaining_shares > 0:
            last_bar = day_df.iloc[-1]
            exit_price = float(last_bar["close"])
            if side == "LONG":
                pnl = remaining_shares * (exit_price - entry_price)
            else:
                pnl = remaining_shares * (entry_price - exit_price)
            total_pnl += pnl
            exit_reason = "EOD_FLATTEN"
        
        return {
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'pnl': total_pnl,
            'r_multiple': total_pnl / (shares * r_amount) if r_amount > 0 else 0
        }


if __name__ == "__main__":
    print("✅ Framework loaded successfully!")
    print("🔧 Bug fixed: Gates now respect 0 value (disabled state)")