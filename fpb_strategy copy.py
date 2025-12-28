"""
==============================================================================
FIRST PULLBACK BUY (FPB) STRATEGY
==============================================================================
Source: Bulls Bootcamp Sessions 64-77 (13 transcripts analyzed)
Instructor: Kunal

This is Kunal's FAVORITE morning setup because:
- Gets you in at LOWER price than ORB
- PREVENTS chasing (killer for most traders)  
- Clear, defined risk (10-20 cents typical)
- Asymmetric R:R (risk pennies, make dollars)
- Works immediately or not at all

THE PATTERN:
1. Stock gaps up / spikes at open (news, PR, earnings, hot daily)
2. Stock does NOT consolidate (no ORB forming)
3. Stock pulls back to 9 EMA or 20 EMA
4. GREEN CANDLE forms at EMA = BUY
5. Stop under the candle low / under EMA
6. Sell half at first spike, trail rest with 9 EMA

WORKS ON SHORTS TOO (inverse - red candle to hold)
==============================================================================
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')


# ==============================================================================
# FPB CONFIGURATION
# ==============================================================================
@dataclass
class FPBConfig:
    """
    First Pullback Buy Configuration
    All parameters derived from bootcamp transcripts
    """
    
    # === TIME WINDOWS ===
    # Morning session only (9:30-11:00 per bootcamp)
    market_open: str = "09:30"
    pullback_start: str = "09:35"   # After first candle, look for pullbacks
    pullback_end: str = "11:00"     # Stop looking after 11am
    hard_exit: str = "11:30"        # Force exit by this time
    
    # === CHART SETTINGS ===
    timeframe: str = "5m"           # 5-minute charts (bootcamp standard)
    ema_fast: int = 9               # 9 EMA (primary pullback level)
    ema_slow: int = 20              # 20 EMA (secondary pullback level)
    atr_length: int = 14            # For position sizing
    
    # === ENTRY FILTERS ===
    min_gap_pct: float = 4.0        # Minimum gap % to consider
    max_gap_pct: float = 30.0       # Avoid extreme gaps that fade
    min_spike_pct: float = 2.0      # Min spike from open before pullback
    max_pullback_candles: int = 6   # Max candles to wait for pullback
    
    # === EMA ZONE SETTINGS ===
    # "Bone Zone" = area between 9 and 20 EMA
    ema_touch_buffer_pct: float = 0.3   # How close to EMA counts as "touch" (0.3%)
    require_green_candle: bool = True    # Must see green candle forming
    
    # === RISK MANAGEMENT ===
    risk_dollars: float = 250.0     # $ risk per trade
    stop_buffer_pct: float = 0.1    # Buffer below candle low (0.1%)
    
    # === TARGETS (Bootcamp: sell half at spike, trail rest) ===
    target_r1: float = 1.5          # First target (sell half)
    target_r2: float = 3.0          # Runner target  
    use_ema_trail: bool = True      # Trail with 9 EMA after R1
    
    # === VOLUME (Optional) ===
    require_volume_confirmation: bool = False  # Bootcamp not strict on this
    min_volume_ratio: float = 1.0   # Breakout vol vs average
    
    def t(self, hhmm: str) -> time:
        """Convert HH:MM string to time object"""
        return datetime.strptime(hhmm, "%H:%M").time()


# ==============================================================================
# TRADE LOGGER (Compatible with your existing system)
# ==============================================================================
class FPBTradeLogger:
    """Records every FPB trade with full context"""
    
    def __init__(self, log_dir: str = "logs/fpb_trades"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trades: List[Dict] = []
        
    def log_trade(self, trade_data: Dict[str, Any]):
        """Log a single trade"""
        trade_data['logged_at'] = datetime.now().isoformat()
        trade_data['strategy'] = 'FPB'
        self.trades.append(trade_data)
        
    def save(self, filename: Optional[str] = None) -> Optional[Path]:
        """Save all trades to CSV"""
        if len(self.trades) == 0:
            print("[FPBLogger] No trades to save")
            return None
            
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fpb_trades_{timestamp}.csv"
            
        filepath = self.log_dir / filename
        df = pd.DataFrame(self.trades)
        df.to_csv(filepath, index=False)
        print(f"[FPBLogger] Saved {len(self.trades)} trades to {filepath}")
        return filepath
        
    def get_trades_df(self) -> pd.DataFrame:
        """Get all trades as DataFrame"""
        return pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
    
    def clear(self):
        """Clear trade history"""
        self.trades = []


# ==============================================================================
# FIRST PULLBACK BUY STRATEGY
# ==============================================================================
class FirstPullbackBuy:
    """
    First Pullback Buy Strategy - Exactly as Bootcamp Teaches
    
    LONG SETUP:
    1. Stock gaps up / spikes up at open
    2. No ORB consolidation - starts pulling back
    3. Pulls back to 9 EMA or 20 EMA zone
    4. GREEN CANDLE starts forming at EMA
    5. BUY when green candle forming (don't wait for close!)
    6. STOP under candle low / under EMA
    7. SELL HALF at first spike, trail rest with 9 EMA
    
    SHORT SETUP (inverse):
    1. Stock gaps down / spikes down
    2. Bounces up toward EMAs
    3. RED CANDLE to hold at EMA
    4. SHORT, stop above
    """
    
    def __init__(self, config: Optional[FPBConfig] = None, 
                 logger: Optional[FPBTradeLogger] = None):
        self.cfg = config or FPBConfig()
        self.logger = logger or FPBTradeLogger()
        self.name = "First Pullback Buy"
        
    # ==========================================================================
    # INDICATOR CALCULATIONS
    # ==========================================================================
    
    def calc_ema(self, series: pd.Series, length: int) -> pd.Series:
        """Calculate EMA"""
        return series.ewm(span=length, adjust=False).mean()
    
    def calc_atr(self, df: pd.DataFrame) -> pd.Series:
        """Calculate ATR"""
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(self.cfg.atr_length).mean()
    
    def calc_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate VWAP"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        return (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    
    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all indicators to dataframe"""
        df = df.copy()
        
        # EMAs
        df['ema9'] = self.calc_ema(df['close'], self.cfg.ema_fast)
        df['ema20'] = self.calc_ema(df['close'], self.cfg.ema_slow)
        
        # ATR
        df['atr'] = self.calc_atr(df)
        
        # VWAP (for reference, bootcamp mentions watching it)
        if 'volume' in df.columns:
            df['vwap'] = self.calc_vwap(df)
        
        # Candle color
        df['is_green'] = df['close'] > df['open']
        df['is_red'] = df['close'] < df['open']
        
        # Distance from EMAs (as % of price)
        df['dist_ema9_pct'] = ((df['low'] - df['ema9']) / df['ema9']) * 100
        df['dist_ema20_pct'] = ((df['low'] - df['ema20']) / df['ema20']) * 100
        
        # For shorts: distance from high
        df['dist_ema9_pct_high'] = ((df['high'] - df['ema9']) / df['ema9']) * 100
        df['dist_ema20_pct_high'] = ((df['high'] - df['ema20']) / df['ema20']) * 100
        
        return df
    
    # ==========================================================================
    # SETUP DETECTION
    # ==========================================================================
    
    def check_initial_spike(self, day_df: pd.DataFrame, prev_close: float) -> Tuple[bool, str]:
        """
        Check if stock had initial spike (required before pullback)
        Returns: (had_spike, direction)
        """
        if len(day_df) < 2:
            return False, "NONE"
        
        # First bar high/low
        first_bar = day_df.iloc[0]
        first_high = first_bar['high']
        first_low = first_bar['low']
        
        # Check gap
        gap_pct = ((first_bar['open'] - prev_close) / prev_close) * 100
        
        # Gap UP scenario
        if gap_pct >= self.cfg.min_gap_pct:
            # Check if made higher high in first few bars (spike up)
            early_bars = day_df.iloc[:3]  # First 15 minutes
            high_of_early = early_bars['high'].max()
            spike_pct = ((high_of_early - prev_close) / prev_close) * 100
            
            if spike_pct >= self.cfg.min_spike_pct:
                return True, "LONG"
        
        # Gap DOWN scenario
        if gap_pct <= -self.cfg.min_gap_pct:
            early_bars = day_df.iloc[:3]
            low_of_early = early_bars['low'].min()
            spike_pct = ((prev_close - low_of_early) / prev_close) * 100
            
            if spike_pct >= self.cfg.min_spike_pct:
                return True, "SHORT"
        
        return False, "NONE"
    
    def check_ema_touch(self, bar: pd.Series, direction: str) -> Tuple[bool, str]:
        """
        Check if bar touches EMA zone ("bone zone")
        Returns: (touched, which_ema)
        """
        buffer = self.cfg.ema_touch_buffer_pct
        
        if direction == "LONG":
            # Check if LOW touches 9 EMA
            dist_9 = abs(bar['dist_ema9_pct'])
            if dist_9 <= buffer or bar['low'] <= bar['ema9']:
                return True, "EMA9"
            
            # Check if LOW touches 20 EMA
            dist_20 = abs(bar['dist_ema20_pct'])
            if dist_20 <= buffer or bar['low'] <= bar['ema20']:
                return True, "EMA20"
            
            # Check if in bone zone (between EMAs)
            if bar['ema20'] <= bar['low'] <= bar['ema9']:
                return True, "BONE_ZONE"
                
        else:  # SHORT
            # Check if HIGH touches 9 EMA
            dist_9 = abs(bar['dist_ema9_pct_high'])
            if dist_9 <= buffer or bar['high'] >= bar['ema9']:
                return True, "EMA9"
            
            # Check if HIGH touches 20 EMA  
            dist_20 = abs(bar['dist_ema20_pct_high'])
            if dist_20 <= buffer or bar['high'] >= bar['ema20']:
                return True, "EMA20"
            
            # Check bone zone
            if bar['ema9'] <= bar['high'] <= bar['ema20']:
                return True, "BONE_ZONE"
        
        return False, "NONE"
    
    def check_confirmation_candle(self, bar: pd.Series, direction: str) -> bool:
        """
        Check if we have confirmation candle
        LONG: Green candle forming at EMA
        SHORT: Red candle forming at EMA
        
        Per bootcamp: Don't wait for close! Enter when candle is forming.
        """
        if direction == "LONG":
            return bar['is_green']
        else:
            return bar['is_red']
    
    def find_pullback_entry(self, day_df: pd.DataFrame, direction: str, 
                           spike_high: float, spike_low: float) -> Optional[Dict]:
        """
        Find first pullback entry opportunity
        
        Returns entry signal dict or None
        """
        # Get bars after initial spike (skip first bar)
        search_df = day_df.iloc[1:]
        
        # Limit search window
        search_df = search_df[
            search_df.index.time <= self.cfg.t(self.cfg.pullback_end)
        ]
        
        if len(search_df) == 0:
            return None
        
        # Track if we're in pullback mode
        in_pullback = False
        candles_since_spike = 0
        
        for idx, bar in search_df.iterrows():
            candles_since_spike += 1
            
            # Too many candles without pullback = skip day
            if candles_since_spike > self.cfg.max_pullback_candles:
                return None
            
            # Check if pulling back (not making new highs/lows)
            if direction == "LONG":
                if bar['high'] < spike_high:
                    in_pullback = True
            else:
                if bar['low'] > spike_low:
                    in_pullback = True
            
            if not in_pullback:
                continue
            
            # Check EMA touch
            touched, ema_level = self.check_ema_touch(bar, direction)
            if not touched:
                continue
            
            # Check confirmation candle
            if self.cfg.require_green_candle:
                if not self.check_confirmation_candle(bar, direction):
                    continue
            
            # === ENTRY SIGNAL FOUND! ===
            
            # Calculate entry, stop, targets
            if direction == "LONG":
                # Entry at current price (close of confirmation candle)
                entry_price = float(bar['close'])
                
                # Stop below candle low or EMA (whichever lower)
                candle_low = float(bar['low'])
                ema_stop = float(bar['ema9']) if ema_level == "EMA9" else float(bar['ema20'])
                stop_price = min(candle_low, ema_stop)
                
                # Add buffer
                buffer = stop_price * (self.cfg.stop_buffer_pct / 100)
                stop_price = stop_price - buffer
                
            else:  # SHORT
                entry_price = float(bar['close'])
                
                candle_high = float(bar['high'])
                ema_stop = float(bar['ema9']) if ema_level == "EMA9" else float(bar['ema20'])
                stop_price = max(candle_high, ema_stop)
                
                buffer = stop_price * (self.cfg.stop_buffer_pct / 100)
                stop_price = stop_price + buffer
            
            # Risk calculation
            risk_per_share = abs(entry_price - stop_price)
            if risk_per_share <= 0.01:  # Too tight
                continue
            
            # Position size
            shares = int(self.cfg.risk_dollars / risk_per_share)
            if shares <= 0:
                continue
            
            # Targets
            if direction == "LONG":
                target_r1 = entry_price + (risk_per_share * self.cfg.target_r1)
                target_r2 = entry_price + (risk_per_share * self.cfg.target_r2)
            else:
                target_r1 = entry_price - (risk_per_share * self.cfg.target_r1)
                target_r2 = entry_price - (risk_per_share * self.cfg.target_r2)
            
            return {
                'entry_time': idx,
                'entry_bar': bar,
                'direction': direction,
                'entry_price': entry_price,
                'stop_price': stop_price,
                'target_r1': target_r1,
                'target_r2': target_r2,
                'shares': shares,
                'risk_per_share': risk_per_share,
                'risk_dollars': risk_per_share * shares,
                'ema_level': ema_level,
                'candles_to_entry': candles_since_spike,
                'ema9_at_entry': float(bar['ema9']),
                'ema20_at_entry': float(bar['ema20']),
            }
        
        return None
    
    # ==========================================================================
    # TRADE SIMULATION
    # ==========================================================================
    
    def simulate_trade(self, df: pd.DataFrame, signal: Dict) -> Dict:
        """
        Simulate trade execution with bootcamp exit rules:
        1. Stop hit = full loss
        2. R1 hit = sell half, move stop to breakeven
        3. R2 hit = close rest
        4. EMA trail after R1 (optional)
        5. EOD exit = close at market
        """
        entry_price = signal['entry_price']
        stop_price = signal['stop_price']
        target_r1 = signal['target_r1']
        target_r2 = signal['target_r2']
        shares = signal['shares']
        direction = signal['direction']
        
        # Get bars after entry
        post_entry = df[df.index > signal['entry_time']]
        
        # Limit to exit time
        post_entry = post_entry[
            post_entry.index.time <= self.cfg.t(self.cfg.hard_exit)
        ]
        
        if len(post_entry) == 0:
            return {
                'exit_reason': 'NO_DATA',
                'exit_price': entry_price,
                'pnl': 0,
                'r_multiple': 0,
                'held_candles': 0
            }
        
        # Track position
        shares_remaining = shares
        shares_half = shares // 2
        total_pnl = 0
        current_stop = stop_price
        hit_r1 = False
        candles_held = 0
        
        for idx, bar in post_entry.iterrows():
            candles_held += 1
            
            if direction == "LONG":
                # Check stop first
                if bar['low'] <= current_stop:
                    pnl = shares_remaining * (current_stop - entry_price)
                    total_pnl += pnl
                    return {
                        'exit_reason': 'STOP' if not hit_r1 else 'STOP_BE',
                        'exit_price': current_stop,
                        'exit_time': idx,
                        'pnl': total_pnl,
                        'r_multiple': total_pnl / signal['risk_dollars'],
                        'held_candles': candles_held,
                        'hit_r1': hit_r1
                    }
                
                # Check R1 target
                if not hit_r1 and bar['high'] >= target_r1:
                    pnl = shares_half * (target_r1 - entry_price)
                    total_pnl += pnl
                    shares_remaining -= shares_half
                    hit_r1 = True
                    current_stop = entry_price  # Move to breakeven
                    
                    if shares_remaining <= 0:
                        return {
                            'exit_reason': 'TARGET_R1',
                            'exit_price': target_r1,
                            'exit_time': idx,
                            'pnl': total_pnl,
                            'r_multiple': total_pnl / signal['risk_dollars'],
                            'held_candles': candles_held,
                            'hit_r1': True
                        }
                
                # Check R2 target
                if hit_r1 and bar['high'] >= target_r2:
                    pnl = shares_remaining * (target_r2 - entry_price)
                    total_pnl += pnl
                    return {
                        'exit_reason': 'TARGET_R2',
                        'exit_price': target_r2,
                        'exit_time': idx,
                        'pnl': total_pnl,
                        'r_multiple': total_pnl / signal['risk_dollars'],
                        'held_candles': candles_held,
                        'hit_r1': True
                    }
                
                # EMA trail (after R1)
                if self.cfg.use_ema_trail and hit_r1:
                    new_stop = bar['ema9'] - (bar['ema9'] * 0.001)  # Tiny buffer
                    if new_stop > current_stop:
                        current_stop = new_stop
                        
            else:  # SHORT
                # Check stop
                if bar['high'] >= current_stop:
                    pnl = shares_remaining * (entry_price - current_stop)
                    total_pnl += pnl
                    return {
                        'exit_reason': 'STOP' if not hit_r1 else 'STOP_BE',
                        'exit_price': current_stop,
                        'exit_time': idx,
                        'pnl': total_pnl,
                        'r_multiple': total_pnl / signal['risk_dollars'],
                        'held_candles': candles_held,
                        'hit_r1': hit_r1
                    }
                
                # Check R1
                if not hit_r1 and bar['low'] <= target_r1:
                    pnl = shares_half * (entry_price - target_r1)
                    total_pnl += pnl
                    shares_remaining -= shares_half
                    hit_r1 = True
                    current_stop = entry_price
                    
                    if shares_remaining <= 0:
                        return {
                            'exit_reason': 'TARGET_R1',
                            'exit_price': target_r1,
                            'exit_time': idx,
                            'pnl': total_pnl,
                            'r_multiple': total_pnl / signal['risk_dollars'],
                            'held_candles': candles_held,
                            'hit_r1': True
                        }
                
                # Check R2
                if hit_r1 and bar['low'] <= target_r2:
                    pnl = shares_remaining * (entry_price - target_r2)
                    total_pnl += pnl
                    return {
                        'exit_reason': 'TARGET_R2',
                        'exit_price': target_r2,
                        'exit_time': idx,
                        'pnl': total_pnl,
                        'r_multiple': total_pnl / signal['risk_dollars'],
                        'held_candles': candles_held,
                        'hit_r1': True
                    }
                
                # EMA trail
                if self.cfg.use_ema_trail and hit_r1:
                    new_stop = bar['ema9'] + (bar['ema9'] * 0.001)
                    if new_stop < current_stop:
                        current_stop = new_stop
        
        # EOD exit
        last_bar = post_entry.iloc[-1]
        last_price = float(last_bar['close'])
        
        if direction == "LONG":
            pnl = shares_remaining * (last_price - entry_price)
        else:
            pnl = shares_remaining * (entry_price - last_price)
        
        total_pnl += pnl
        
        return {
            'exit_reason': 'EOD',
            'exit_price': last_price,
            'exit_time': post_entry.index[-1],
            'pnl': total_pnl,
            'r_multiple': total_pnl / signal['risk_dollars'],
            'held_candles': candles_held,
            'hit_r1': hit_r1
        }
    
    # ==========================================================================
    # MAIN BACKTEST
    # ==========================================================================
    
    def get_previous_close(self, df: pd.DataFrame, date) -> Optional[float]:
        """Get previous day's close"""
        prev_dates = df[df.index.date < date]
        if len(prev_dates) == 0:
            return None
        return float(prev_dates['close'].iloc[-1])
    
    def run_backtest(self, df: pd.DataFrame, symbol: str = "SYMBOL",
                     filter_gap_days: bool = True) -> Dict[str, Any]:
        """
        Run FPB strategy backtest on historical data
        
        Args:
            df: DataFrame with OHLCV data (5-min bars)
            symbol: Stock symbol
            filter_gap_days: If True, only trade days with gaps >= min_gap_pct
            
        Returns:
            Dict with backtest results
        """
        print(f"\n{'='*60}")
        print(f"🎯 FIRST PULLBACK BUY BACKTEST: {symbol}")
        print(f"{'='*60}")
        
        # Prepare data
        df = self.prepare_data(df)
        
        results = []
        days_checked = 0
        days_with_setup = 0
        
        # Process each day
        unique_dates = sorted(set(df.index.date))
        
        for i, date in enumerate(unique_dates):
            # Need previous day for gap calculation
            if i == 0:
                continue
                
            prev_close = self.get_previous_close(df, date)
            if prev_close is None:
                continue
            
            # Get this day's data
            day_df = df[df.index.date == date].copy()
            if len(day_df) < 5:
                continue
            
            # Filter to market hours
            day_df = day_df.between_time(
                self.cfg.t(self.cfg.market_open),
                self.cfg.t(self.cfg.hard_exit)
            )
            
            if len(day_df) < 3:
                continue
            
            days_checked += 1
            
            # Check for initial spike
            had_spike, direction = self.check_initial_spike(day_df, prev_close)
            
            if not had_spike:
                continue
            
            # Gap filter
            gap_pct = ((day_df.iloc[0]['open'] - prev_close) / prev_close) * 100
            
            if filter_gap_days:
                if abs(gap_pct) < self.cfg.min_gap_pct:
                    continue
                if abs(gap_pct) > self.cfg.max_gap_pct:
                    continue
            
            days_with_setup += 1
            
            # Get spike extremes
            early_df = day_df.iloc[:3]
            spike_high = early_df['high'].max()
            spike_low = early_df['low'].min()
            
            # Look for pullback entry
            signal = self.find_pullback_entry(day_df, direction, spike_high, spike_low)
            
            if signal is None:
                continue
            
            # Simulate trade
            trade_result = self.simulate_trade(day_df, signal)
            
            # Build full trade record
            trade = {
                'symbol': symbol,
                'date': str(date),
                'direction': direction,
                'gap_pct': round(gap_pct, 2),
                'entry_time': str(signal['entry_time']),
                'entry_price': round(signal['entry_price'], 2),
                'stop_price': round(signal['stop_price'], 2),
                'target_r1': round(signal['target_r1'], 2),
                'target_r2': round(signal['target_r2'], 2),
                'shares': signal['shares'],
                'risk_dollars': round(signal['risk_dollars'], 2),
                'ema_level': signal['ema_level'],
                'candles_to_entry': signal['candles_to_entry'],
                **trade_result
            }
            
            # Round PnL
            trade['pnl'] = round(trade['pnl'], 2)
            trade['r_multiple'] = round(trade['r_multiple'], 2)
            
            # Log trade
            self.logger.log_trade(trade)
            results.append(trade)
        
        # Calculate summary stats
        if len(results) == 0:
            print(f"\n⚠️  No trades found!")
            print(f"   Days checked: {days_checked}")
            print(f"   Days with setup: {days_with_setup}")
            return {
                'symbol': symbol,
                'trades': 0,
                'days_checked': days_checked,
                'days_with_setup': days_with_setup,
                'winrate': 0,
                'total_pnl': 0,
                'avg_r': 0
            }
        
        total_pnl = sum(r['pnl'] for r in results)
        winners = [r for r in results if r['pnl'] > 0]
        losers = [r for r in results if r['pnl'] < 0]
        
        winrate = len(winners) / len(results) * 100
        avg_r = np.mean([r['r_multiple'] for r in results])
        
        # Print summary
        print(f"\n📊 RESULTS:")
        print(f"   Days Checked: {days_checked}")
        print(f"   Days with Setup: {days_with_setup}")
        print(f"   Total Trades: {len(results)}")
        print(f"   Winners: {len(winners)} ({winrate:.1f}%)")
        print(f"   Losers: {len(losers)}")
        print(f"   Total PnL: ${total_pnl:.2f}")
        print(f"   Avg R-Multiple: {avg_r:.2f}R")
        
        if len(winners) > 0:
            avg_win = np.mean([r['pnl'] for r in winners])
            print(f"   Avg Win: ${avg_win:.2f}")
        
        if len(losers) > 0:
            avg_loss = np.mean([r['pnl'] for r in losers])
            print(f"   Avg Loss: ${avg_loss:.2f}")
        
        # Exit reason breakdown
        print(f"\n📈 EXIT REASONS:")
        for reason in ['TARGET_R2', 'TARGET_R1', 'STOP_BE', 'STOP', 'EOD']:
            count = len([r for r in results if r['exit_reason'] == reason])
            if count > 0:
                pct = count / len(results) * 100
                print(f"   {reason}: {count} ({pct:.1f}%)")
        
        print(f"\n{'='*60}\n")
        
        return {
            'symbol': symbol,
            'trades': len(results),
            'days_checked': days_checked,
            'days_with_setup': days_with_setup,
            'winrate': round(winrate, 1),
            'total_pnl': round(total_pnl, 2),
            'avg_r': round(avg_r, 2),
            'winners': len(winners),
            'losers': len(losers),
            'results': results
        }


# ==============================================================================
# QUICK SCANNER FOR FPB SETUPS (Real-time use)
# ==============================================================================
class FPBScanner:
    """
    Real-time scanner for FPB setups
    Use this during market hours to find opportunities
    """
    
    def __init__(self, config: Optional[FPBConfig] = None):
        self.cfg = config or FPBConfig()
        self.strategy = FirstPullbackBuy(config=self.cfg)
        
    def scan_symbol(self, df: pd.DataFrame, symbol: str, prev_close: float) -> Optional[Dict]:
        """
        Scan single symbol for FPB setup RIGHT NOW
        
        Args:
            df: Today's 5-min data so far
            symbol: Stock symbol
            prev_close: Previous day's close
            
        Returns:
            Signal dict if setup found, None otherwise
        """
        if len(df) < 3:
            return None
        
        # Prepare data
        df = self.strategy.prepare_data(df)
        
        # Check for spike
        had_spike, direction = self.strategy.check_initial_spike(df, prev_close)
        if not had_spike:
            return None
        
        # Get spike extremes  
        early_df = df.iloc[:3]
        spike_high = early_df['high'].max()
        spike_low = early_df['low'].min()
        
        # Look for entry
        signal = self.strategy.find_pullback_entry(df, direction, spike_high, spike_low)
        
        if signal:
            signal['symbol'] = symbol
            gap_pct = ((df.iloc[0]['open'] - prev_close) / prev_close) * 100
            signal['gap_pct'] = round(gap_pct, 2)
            
        return signal


# ==============================================================================
# EXAMPLE USAGE & TESTING
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🎯 FIRST PULLBACK BUY STRATEGY")
    print("="*70)
    print("\nFrom Bulls Bootcamp - Kunal's FAVORITE setup!")
    print("\nKEY POINTS:")
    print("• Time Window: 9:30 AM - 11:00 AM")
    print("• Chart: 5-minute with 9 EMA and 20 EMA")
    print("• Entry: Green candle forming at EMA (don't wait for close!)")
    print("• Stop: Below candle low / below EMA")
    print("• Target: Sell half at spike, trail rest with 9 EMA")
    print("• Works on LONGS (pullback buy) and SHORTS (pullback short)")
    print("\n" + "="*70)
    
    print("\n📋 CONFIGURATION OPTIONS:")
    cfg = FPBConfig()
    print(f"   min_gap_pct: {cfg.min_gap_pct}%")
    print(f"   risk_dollars: ${cfg.risk_dollars}")
    print(f"   target_r1: {cfg.target_r1}R")
    print(f"   target_r2: {cfg.target_r2}R")
    print(f"   ema_fast: {cfg.ema_fast}")
    print(f"   ema_slow: {cfg.ema_slow}")
    
    print("\n✅ Strategy module loaded successfully!")
    print("\nTo run backtest:")
    print("   from fpb_strategy import FirstPullbackBuy, FPBConfig")
    print("   strategy = FirstPullbackBuy()")
    print("   results = strategy.run_backtest(df, 'AAPL')")