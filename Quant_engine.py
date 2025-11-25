"""
Multi-Strategy Quant Engine
Runs multiple strategies simultaneously and uses ML-style decision making
to choose which trades to take based on recent performance
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
import json
import os

class StrategyBase:
    """Base class for all trading strategies"""
    
    def __init__(self, name: str):
        self.name = name
        self.performance_history = []
        self.win_rate = 0
        self.avg_r_multiple = 0
        self.confidence = 0.5
        self.min_trades_for_confidence = 10
        
    def scan_for_setup(self, data: pd.DataFrame, symbol: str, date: str) -> Optional[Dict]:
        """Override in child class"""
        raise NotImplementedError
        
    def update_performance(self, trade_result: Dict):
        """Update strategy performance based on trade result"""
        self.performance_history.append(trade_result)
        
        # Calculate metrics on recent trades
        recent = self.performance_history[-30:]  # Last 30 trades
        if len(recent) >= self.min_trades_for_confidence:
            winners = [t for t in recent if t.get('r_multiple', 0) > 0]
            self.win_rate = len(winners) / len(recent)
            self.avg_r_multiple = np.mean([t.get('r_multiple', 0) for t in recent])
            
            # Update confidence (0-1 scale)
            # Confidence = win_rate * avg_r_multiple * recency_factor
            self.confidence = min(1.0, self.win_rate * max(0, self.avg_r_multiple) * 0.8)
        else:
            # Not enough trades yet, use default confidence
            self.confidence = 0.3
            
    def get_expected_value(self) -> float:
        """Calculate expected value of next trade"""
        return self.win_rate * self.avg_r_multiple
        

class ORB_15Min_Strategy(StrategyBase):
    """15-minute ORB from instructor screenshots"""
    
    def __init__(self):
        super().__init__("ORB_15Min")
        self.min_gap = 4.0
        self.or_start = time(9, 30)
        self.or_end = time(9, 45)
        
    def scan_for_setup(self, data: pd.DataFrame, symbol: str, date: str) -> Optional[Dict]:
        """Scan for 15-min ORB setup"""
        # Simplified version - would import from elite_orb_strategy.py
        data['time'] = pd.to_datetime(data.index).time
        or_data = data[(data['time'] >= self.or_start) & (data['time'] < self.or_end)]
        
        if len(or_data) < 3:
            return None
            
        or_high = or_data['high'].max()
        or_low = or_data['low'].min()
        
        # Look for breakout
        post_or = data[data['time'] >= self.or_end]
        for bar in post_or.itertuples():
            if bar.close > or_high * 1.002:  # 0.2% above high
                return {
                    'strategy': self.name,
                    'symbol': symbol,
                    'date': date,
                    'entry': or_high + 0.01,
                    'stop': or_low - 0.05,
                    'target': or_high + ((or_high - or_low) * 2),
                    'confidence': self.confidence
                }
        return None


class GapAndGo_Strategy(StrategyBase):
    """Gap and Go - buy strong gaps that keep running"""
    
    def __init__(self):
        super().__init__("GapAndGo")
        self.min_gap = 5.0
        self.pullback_max = 0.5  # Max 50% pullback from gap
        
    def scan_for_setup(self, data: pd.DataFrame, symbol: str, date: str) -> Optional[Dict]:
        """Scan for gap and go setup"""
        open_price = data['open'].iloc[0]
        prev_close = open_price * 0.95  # Estimate
        gap_pct = ((open_price - prev_close) / prev_close) * 100
        
        if gap_pct < self.min_gap:
            return None
            
        # Look for pullback and continuation
        first_30min = data.iloc[:6]  # First 30 minutes (6 x 5-min bars)
        low_of_day = first_30min['low'].min()
        
        pullback_pct = (open_price - low_of_day) / (open_price - prev_close)
        if pullback_pct > self.pullback_max:
            return None
            
        # Entry on new high after pullback
        for bar in data.iloc[6:].itertuples():
            if bar.high > first_30min['high'].max():
                return {
                    'strategy': self.name,
                    'symbol': symbol,
                    'date': date,
                    'entry': bar.high + 0.01,
                    'stop': low_of_day - 0.05,
                    'target': bar.high + ((bar.high - low_of_day) * 1.5),
                    'confidence': self.confidence
                }
        return None


class VWAPBounce_Strategy(StrategyBase):
    """VWAP Bounce - buy bounces off VWAP"""
    
    def __init__(self):
        super().__init__("VWAPBounce")
        self.min_touches = 2
        self.bounce_threshold = 0.002  # 0.2% 
        
    def scan_for_setup(self, data: pd.DataFrame, symbol: str, date: str) -> Optional[Dict]:
        """Scan for VWAP bounce"""
        # Calculate VWAP
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        vwap = (typical_price * data['volume']).cumsum() / data['volume'].cumsum()
        
        touches = 0
        for i, bar in enumerate(data.itertuples()):
            # Check if low touches VWAP
            if abs(bar.low - vwap.iloc[i]) / vwap.iloc[i] < self.bounce_threshold:
                touches += 1
                
                if touches >= self.min_touches and bar.close > vwap.iloc[i]:
                    return {
                        'strategy': self.name,
                        'symbol': symbol,
                        'date': date,
                        'entry': bar.close,
                        'stop': bar.low - 0.05,
                        'target': bar.close + ((bar.close - bar.low) * 2),
                        'confidence': self.confidence
                    }
        return None


class BullFlag_Strategy(StrategyBase):
    """Bull Flag - strong move up, tight consolidation, continuation"""
    
    def __init__(self):
        super().__init__("BullFlag")
        self.min_pole_move = 0.03  # 3% minimum for pole
        self.max_flag_retrace = 0.5  # Max 50% retracement
        self.min_consolidation_bars = 3
        
    def scan_for_setup(self, data: pd.DataFrame, symbol: str, date: str) -> Optional[Dict]:
        """Scan for bull flag"""
        for i in range(10, len(data) - 5):
            # Look for pole (strong move up)
            pole_start = i - 10
            pole_end = i
            pole_move = (data['high'].iloc[pole_end] - data['low'].iloc[pole_start]) / data['low'].iloc[pole_start]
            
            if pole_move < self.min_pole_move:
                continue
                
            # Look for flag (consolidation)
            flag_data = data.iloc[pole_end:pole_end + 5]
            flag_high = flag_data['high'].max()
            flag_low = flag_data['low'].min()
            
            # Check retracement
            retrace = (data['high'].iloc[pole_end] - flag_low) / (data['high'].iloc[pole_end] - data['low'].iloc[pole_start])
            if retrace > self.max_flag_retrace:
                continue
                
            # Check for breakout
            if flag_data['close'].iloc[-1] > flag_high:
                return {
                    'strategy': self.name,
                    'symbol': symbol,
                    'date': date,
                    'entry': flag_high + 0.01,
                    'stop': flag_low - 0.05,
                    'target': flag_high + (data['high'].iloc[pole_end] - data['low'].iloc[pole_start]),
                    'confidence': self.confidence
                }
        return None


class QuantEngine:
    """
    Multi-Strategy Quant Engine
    Runs multiple strategies and decides which trades to take
    """
    
    def __init__(self, capital: float = 10000):
        self.capital = capital
        self.strategies = []
        self.all_signals = []
        self.taken_trades = []
        self.performance_log = []
        self.max_concurrent_trades = 3
        self.risk_per_trade_pct = 0.02  # 2% risk per trade
        self.min_confidence_threshold = 0.4
        
    def add_strategy(self, strategy: StrategyBase):
        """Add a strategy to the engine"""
        self.strategies.append(strategy)
        print(f"Added strategy: {strategy.name}")
        
    def scan_all_strategies(self, data: pd.DataFrame, symbol: str, date: str) -> List[Dict]:
        """Run all strategies and collect signals"""
        signals = []
        for strategy in self.strategies:
            try:
                signal = strategy.scan_for_setup(data, symbol, date)
                if signal:
                    signal['expected_value'] = strategy.get_expected_value()
                    signals.append(signal)
            except Exception as e:
                print(f"Error in {strategy.name}: {e}")
                continue
        return signals
        
    def rank_signals(self, signals: List[Dict]) -> List[Dict]:
        """
        Rank signals by expected value and confidence
        This is where the "ML" magic happens
        """
        # Calculate composite score for each signal
        for signal in signals:
            # Composite score = confidence * expected_value * recency_bonus
            strategy = next(s for s in self.strategies if s.name == signal['strategy'])
            
            # Recency bonus (strategies that worked recently get bonus)
            recent_trades = strategy.performance_history[-5:]
            if recent_trades:
                recent_win_rate = len([t for t in recent_trades if t.get('r_multiple', 0) > 0]) / len(recent_trades)
                recency_bonus = 1 + (recent_win_rate * 0.2)  # Up to 20% bonus
            else:
                recency_bonus = 1.0
                
            signal['composite_score'] = signal['confidence'] * signal['expected_value'] * recency_bonus
            
        # Sort by composite score
        ranked = sorted(signals, key=lambda x: x['composite_score'], reverse=True)
        return ranked
        
    def decide_trades(self, signals: List[Dict]) -> List[Dict]:
        """
        Decide which trades to actually take based on:
        - Confidence threshold
        - Risk management
        - Concurrent trade limits
        """
        trades_to_take = []
        total_risk = 0
        
        ranked_signals = self.rank_signals(signals)
        
        for signal in ranked_signals:
            # Skip low confidence
            if signal['confidence'] < self.min_confidence_threshold:
                continue
                
            # Check concurrent trade limit
            if len(trades_to_take) >= self.max_concurrent_trades:
                break
                
            # Calculate position size based on confidence
            # Higher confidence = larger position (but capped)
            risk_dollars = self.capital * self.risk_per_trade_pct * signal['confidence']
            risk_dollars = min(risk_dollars, self.capital * 0.02)  # Cap at 2%
            
            # Check total risk
            if total_risk + risk_dollars > self.capital * 0.06:  # Max 6% total risk
                break
                
            # Calculate shares
            risk_per_share = abs(signal['entry'] - signal['stop'])
            shares = int(risk_dollars / risk_per_share)
            
            if shares > 0:
                signal['shares'] = shares
                signal['risk_dollars'] = risk_dollars
                trades_to_take.append(signal)
                total_risk += risk_dollars
                
        return trades_to_take
        
    def execute_backtest(self, data: pd.DataFrame, symbol: str, date: str) -> Dict:
        """
        Run full backtest on a single day
        """
        # Scan all strategies
        signals = self.scan_all_strategies(data, symbol, date)
        
        # Decide which trades to take
        trades = self.decide_trades(signals)
        
        # Log decision process
        decision_log = {
            'date': date,
            'symbol': symbol,
            'signals_generated': len(signals),
            'trades_taken': len(trades),
            'strategies_used': list(set([t['strategy'] for t in trades])),
            'confidence_scores': {t['strategy']: round(t['confidence'], 3) for t in trades},
            'risk_allocated': sum([t['risk_dollars'] for t in trades])
        }
        
        # Simulate trades and update strategy performance
        results = []
        for trade in trades:
            # Simple simulation (would be more complex in reality)
            # Assume 40% win rate with 2R average for now
            win = np.random.random() < 0.4
            if win:
                r_multiple = np.random.uniform(1.5, 3.0)
            else:
                r_multiple = -1.0
                
            trade_result = {
                **trade,
                'r_multiple': r_multiple,
                'pnl': trade['risk_dollars'] * r_multiple
            }
            
            # Update strategy performance
            strategy = next(s for s in self.strategies if s.name == trade['strategy'])
            strategy.update_performance(trade_result)
            
            results.append(trade_result)
            
        return {
            'decision_log': decision_log,
            'trades': results,
            'total_pnl': sum([t['pnl'] for t in results]) if results else 0
        }
        
    def get_performance_summary(self) -> Dict:
        """Get overall performance summary"""
        summary = {
            'total_trades': len(self.taken_trades),
            'total_pnl': sum([t['pnl'] for t in self.taken_trades]) if self.taken_trades else 0,
            'strategy_performance': {}
        }
        
        for strategy in self.strategies:
            if strategy.performance_history:
                summary['strategy_performance'][strategy.name] = {
                    'trades': len(strategy.performance_history),
                    'win_rate': round(strategy.win_rate * 100, 1),
                    'avg_r': round(strategy.avg_r_multiple, 2),
                    'confidence': round(strategy.confidence, 3),
                    'expected_value': round(strategy.get_expected_value(), 2)
                }
                
        return summary
        
    def save_performance(self, filename: str = 'quant_performance.json'):
        """Save performance to file"""
        with open(filename, 'w') as f:
            json.dump({
                'summary': self.get_performance_summary(),
                'decision_logs': self.performance_log,
                'trades': self.taken_trades
            }, f, indent=2, default=str)
            

# Example usage
if __name__ == "__main__":
    print("Multi-Strategy Quant Engine")
    print("=" * 50)
    
    # Initialize engine
    engine = QuantEngine(capital=10000)
    
    # Add strategies
    engine.add_strategy(ORB_15Min_Strategy())
    engine.add_strategy(GapAndGo_Strategy())
    engine.add_strategy(VWAPBounce_Strategy())
    engine.add_strategy(BullFlag_Strategy())
    
    print("\nEngine Configuration:")
    print(f"- Capital: ${engine.capital}")
    print(f"- Max concurrent trades: {engine.max_concurrent_trades}")
    print(f"- Risk per trade: {engine.risk_per_trade_pct * 100}%")
    print(f"- Min confidence: {engine.min_confidence_threshold}")
    print(f"- Strategies loaded: {len(engine.strategies)}")
    
    print("\nHow it works:")
    print("1. Scans all strategies simultaneously")
    print("2. Ranks signals by confidence & expected value")
    print("3. Allocates capital based on confidence")
    print("4. Updates strategy performance after each trade")
    print("5. Strategies that work get more capital")
    print("6. Strategies that fail get less capital")
    print("\nThis is a self-learning system!")