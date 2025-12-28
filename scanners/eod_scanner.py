"""
eod_scanner.py - End-of-Day Pattern Scanner
============================================
Finds daily chart setups for next day's trading.

Run: 4:00 PM - 6:00 PM Eastern (after market close)
Output: watchlist_eod.json

PATTERNS DETECTED:
1. Flat Top Breakout - Multiple resistance touches
2. Bull Flag - Strong pole + tight consolidation
3. Pullback to Moving Average - Bounce off 20/50 EMA
4. Base Breakout - Extended consolidation ready to pop

Per Bulls Bootcamp: These are "hot daily" stocks
that could gap OR give first pullback entries.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np

# Import config
try:
    from config import *
except ImportError:
    MIN_PRICE = 5.0
    MAX_PRICE = 500.0
    MIN_AVG_DAILY_VOLUME = 500000
    DEFAULT_UNIVERSE = ["NVDA", "AMD", "TSLA", "COIN", "MSTR"]


# ==============================================================================
# EOD PATTERN SCANNER
# ==============================================================================
class EODScanner:
    """
    Scans daily charts for tradeable patterns.
    
    Per Bulls Bootcamp:
    - Look for "bone zone" setups (9 EMA > 20 EMA)
    - Find stocks building bases
    - Identify breakout candidates
    """
    
    def __init__(self):
        self.min_price = MIN_PRICE
        self.max_price = MAX_PRICE
        self.min_avg_volume = MIN_AVG_DAILY_VOLUME
        
    def get_universe(self) -> List[str]:
        """Get list of stocks to scan"""
        if os.path.exists('universe.txt'):
            with open('universe.txt', 'r') as f:
                symbols = []
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        symbols.append(line.upper())
            return symbols
        return DEFAULT_UNIVERSE
    
    def get_daily_data(self, symbol: str, days: int = 100) -> Optional[pd.DataFrame]:
        """Download daily OHLCV data"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days}d")
            
            if df is None or len(df) < 50:
                return None
            
            # Standardize columns
            df.columns = [c.lower() for c in df.columns]
            
            return df
            
        except Exception as e:
            return None
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to dataframe"""
        df = df.copy()
        
        # EMAs (bootcamp uses 9, 20, 50)
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['sma200'] = df['close'].rolling(200).mean()
        
        # ATR for volatility
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        # Volume SMA and relative volume
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['relative_volume'] = df['volume'] / df['vol_sma']
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Trend direction (bone zone check)
        df['bone_zone'] = (df['ema9'] > df['ema20']).astype(int)
        df['uptrend'] = ((df['ema9'] > df['ema20']) & (df['ema20'] > df['ema50'])).astype(int)
        
        return df
    
    # ==========================================================================
    # PATTERN DETECTION
    # ==========================================================================
    
    def check_flat_top_breakout(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Detect flat top breakout setup.
        
        Rules (per bootcamp):
        1. Multiple touches of resistance (within 2%)
        2. Price above EMAs
        3. Ready to break out
        """
        if len(df) < 20:
            return None
        
        recent = df.tail(20)
        highs = recent['high'].values
        
        # Find resistance level
        resistance = highs.max()
        
        # Count touches within 2% of resistance
        touch_zone = resistance * 0.98
        touches = sum(1 for h in highs if h >= touch_zone)
        
        if touches < 3:
            return None
        
        # Check if close to breakout (within 3%)
        current_price = df['close'].iloc[-1]
        if current_price < resistance * 0.97:
            return None
        
        # EMAs must be aligned (bone zone)
        last = df.iloc[-1]
        if not (last['ema9'] > last['ema20']):
            return None
        
        return {
            'pattern': 'flat_top_breakout',
            'resistance': round(float(resistance), 2),
            'touches': int(touches),
            'distance_to_breakout_pct': round((resistance - current_price) / current_price * 100, 2),
            'score_bonus': 25
        }
    
    def check_bull_flag(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Detect bull flag pattern.
        
        Rules:
        1. Strong move up (pole): 10%+ in recent days
        2. Tight consolidation (flag)
        3. Flag holds above 50% of pole
        4. Volume decreases in flag
        """
        if len(df) < 30:
            return None
        
        # Look for pole in last 20 days
        recent_20 = df.tail(20)
        
        # Find high point (top of pole)
        pole_high_idx = recent_20['high'].idxmax()
        pole_high = float(recent_20['high'].max())
        
        # Find low before the pole (look back 10 bars)
        try:
            before_pole = df.loc[:pole_high_idx].tail(10)
            if len(before_pole) < 3:
                return None
            pole_low = float(before_pole['low'].min())
        except:
            return None
        
        # Calculate pole size
        pole_pct = (pole_high - pole_low) / pole_low * 100
        if pole_pct < 10:
            return None  # Need 10%+ move for pole
        
        # Check flag (consolidation after pole)
        try:
            after_pole = df.loc[pole_high_idx:].tail(10)
            if len(after_pole) < 3:
                return None
        except:
            return None
        
        flag_low = float(after_pole['low'].min())
        flag_high = float(after_pole['high'].max())
        
        # Flag must hold above 50% of pole
        pole_midpoint = pole_low + (pole_high - pole_low) * 0.5
        if flag_low < pole_midpoint:
            return None
        
        # Volume should decrease in flag
        try:
            pole_vol = before_pole['volume'].mean()
            flag_vol = after_pole['volume'].mean()
            if flag_vol > pole_vol:
                return None
        except:
            pass
        
        return {
            'pattern': 'bull_flag',
            'pole_low': round(pole_low, 2),
            'pole_high': round(pole_high, 2),
            'pole_pct': round(pole_pct, 2),
            'flag_low': round(flag_low, 2),
            'flag_high': round(flag_high, 2),
            'score_bonus': 30
        }
    
    def check_pullback_to_ma(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Detect pullback to moving average setup.
        
        Rules (per bootcamp):
        1. Stock in uptrend (above 50 EMA)
        2. Pullback to 20 or 50 EMA
        3. MA holding as support
        4. Bounce starting (green candle)
        """
        if len(df) < 50:
            return None
        
        last = df.iloc[-1]
        
        # Must be in uptrend (above 50 EMA)
        if last['close'] < last['ema50']:
            return None
        
        # Check for touch of 20 EMA
        near_ema20 = abs(last['low'] - last['ema20']) / last['ema20'] < 0.02
        
        # Check for touch of 50 EMA
        near_ema50 = abs(last['low'] - last['ema50']) / last['ema50'] < 0.02
        
        if not (near_ema20 or near_ema50):
            return None
        
        # Check for bounce (close > open = green candle)
        is_green = last['close'] > last['open']
        if not is_green:
            return None
        
        ma_level = 'ema20' if near_ema20 else 'ema50'
        
        # Calculate bounce strength
        candle_range = last['high'] - last['low']
        if candle_range > 0:
            bounce_strength = (last['close'] - last['low']) / candle_range * 100
        else:
            bounce_strength = 50
        
        return {
            'pattern': 'pullback_to_ma',
            'ma_level': ma_level,
            'ma_price': round(float(last[ma_level]), 2),
            'bounce_strength': round(bounce_strength, 1),
            'score_bonus': 20
        }
    
    def check_base_breakout(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Detect base breakout setup.
        
        Rules:
        1. Extended consolidation (15+ days)
        2. Tight range (< 15% from high to low)
        3. Volume drying up
        4. Ready to break
        """
        if len(df) < 30:
            return None
        
        # Look at last 20 days
        recent = df.tail(20)
        
        range_high = recent['high'].max()
        range_low = recent['low'].min()
        range_pct = (range_high - range_low) / range_low * 100
        
        # Range must be tight (< 15%)
        if range_pct > 15:
            return None
        
        # Current price near top of range
        current = df['close'].iloc[-1]
        if current < range_high * 0.95:
            return None
        
        # Volume drying up (recent vol < avg)
        recent_vol = recent['volume'].tail(5).mean()
        avg_vol = recent['volume'].mean()
        if recent_vol > avg_vol:
            return None
        
        return {
            'pattern': 'base_breakout',
            'range_high': round(float(range_high), 2),
            'range_low': round(float(range_low), 2),
            'range_pct': round(range_pct, 2),
            'vol_ratio': round(recent_vol / avg_vol, 2),
            'score_bonus': 20
        }
    
    # ==========================================================================
    # MAIN SCAN
    # ==========================================================================
    
    def scan_symbol(self, symbol: str) -> Optional[Dict]:
        """Scan single symbol for all patterns"""
        
        df = self.get_daily_data(symbol)
        if df is None or len(df) < 50:
            return None
        
        df = self.add_indicators(df)
        
        # Check each pattern
        patterns_found = []
        
        flat_top = self.check_flat_top_breakout(df)
        if flat_top:
            patterns_found.append(flat_top)
        
        bull_flag = self.check_bull_flag(df)
        if bull_flag:
            patterns_found.append(bull_flag)
        
        pullback = self.check_pullback_to_ma(df)
        if pullback:
            patterns_found.append(pullback)
        
        base = self.check_base_breakout(df)
        if base:
            patterns_found.append(base)
        
        if not patterns_found:
            return None
        
        last = df.iloc[-1]
        
        # Calculate score
        base_score = 50  # Base score for having any pattern
        pattern_bonus = sum(p.get('score_bonus', 0) for p in patterns_found)
        
        # Trend bonus
        trend_bonus = 10 if last['uptrend'] else 0
        
        # RSI bonus (not overbought)
        rsi_bonus = 10 if 40 <= last['rsi'] <= 70 else 0
        
        total_score = min(100, base_score + pattern_bonus + trend_bonus + rsi_bonus)
        
        return {
            'symbol': symbol,
            'price': round(float(last['close']), 2),
            'ema9': round(float(last['ema9']), 2),
            'ema20': round(float(last['ema20']), 2),
            'ema50': round(float(last['ema50']), 2),
            'rsi': round(float(last['rsi']), 1),
            'relative_volume': round(float(last['relative_volume']), 2),
            'bone_zone': bool(last['bone_zone']),
            'uptrend': bool(last['uptrend']),
            'patterns': patterns_found,
            'pattern_names': [p['pattern'] for p in patterns_found],
            'score': total_score,
            'scan_type': 'eod_daily',
            'scan_time': datetime.now().isoformat()
        }
    
    def scan(self, symbols: List[str] = None) -> List[Dict]:
        """Run EOD scan on all symbols"""
        
        if symbols is None:
            symbols = self.get_universe()
        
        print(f"\n{'='*60}")
        print(f"📊 END-OF-DAY PATTERN SCANNER")
        print(f"{'='*60}")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔍 Scanning {len(symbols)} stocks for daily patterns...")
        print(f"{'='*60}\n")
        
        results = []
        
        for i, symbol in enumerate(symbols):
            if (i + 1) % 10 == 0:
                print(f"   Progress: {i+1}/{len(symbols)}...")
            
            try:
                result = self.scan_symbol(symbol)
                if result:
                    results.append(result)
                    patterns = result['pattern_names']
                    print(f"   ✅ {symbol}: {patterns} (Score: {result['score']})")
            except Exception as e:
                continue
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"\n{'='*60}")
        print(f"✅ FOUND {len(results)} DAILY SETUPS")
        print(f"{'='*60}")
        
        return results


# ==============================================================================
# MAIN FUNCTION
# ==============================================================================
def run_eod_scan(save: bool = True) -> List[Dict]:
    """
    Main function to run EOD scan.
    
    Args:
        save: Save results to JSON file
        
    Returns:
        List of stocks with patterns
    """
    scanner = EODScanner()
    results = scanner.scan()
    
    # Print summary
    if results:
        print(f"\n📈 TOP DAILY SETUPS:")
        for i, stock in enumerate(results[:10], 1):
            patterns = ', '.join(stock['pattern_names'])
            trend = "🟢" if stock['uptrend'] else "🟡"
            print(f"   {i}. {stock['symbol']:6} | ${stock['price']:7.2f} | "
                  f"RSI: {stock['rsi']:4.1f} | {trend} | {patterns}")
    
    # Save to file
    if save and results:
        os.makedirs('output', exist_ok=True)
        output = {
            'scan_time': datetime.now().isoformat(),
            'scan_type': 'eod_daily',
            'count': len(results),
            'stocks': results
        }
        
        with open('output/watchlist_eod.json', 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n💾 Saved to output/watchlist_eod.json")
    
    return results


# ==============================================================================
# RUN
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "📊"*30)
    print("\n  END-OF-DAY PATTERN SCANNER")
    print("\n" + "📊"*30)
    
    setups = run_eod_scan()
    
    if setups:
        print(f"\n✅ Found {len(setups)} stocks with daily patterns!")
        
        # Summary by pattern type
        print("\n📋 Pattern breakdown:")
        pattern_counts = {}
        for stock in setups:
            for p in stock['pattern_names']:
                pattern_counts[p] = pattern_counts.get(p, 0) + 1
        
        for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
            print(f"   • {pattern}: {count}")
    else:
        print("\n⚠️  No patterns found")
    
    print("\n✅ Scan complete!")
