"""
==============================================================================
QUANT ENGINE v3.0 - IMPORTS YOUR ACTUAL STRATEGIES
==============================================================================
This engine IMPORTS your real strategy files - no duplicate code!

Your files:
- fpb_strategy.py → 600 lines, tested, 47.7% win rate
- (future) elite_orb_strategy.py

This file just:
1. Loads stocks from scanner
2. Imports YOUR strategies
3. Runs them
4. Handles paper/live trading via Alpaca

==============================================================================
"""

import sys
import os
from datetime import datetime, time
from typing import Dict, List, Optional
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

# === ADD YOUR BOT FOLDER TO PATH ===
# This lets Python find your strategy files
sys.path.insert(0, 'C:/Users/Hassan/ORB-Bot')
sys.path.insert(0, 'C:/Users/Hassan/ORB-Bot/scanners')

# === IMPORT YOUR ACTUAL STRATEGIES ===
try:
    from fpb_strategy import FirstPullbackBuy, FPBConfig, FPBTradeLogger, download_stock_data, load_watchlist_symbols, load_watchlist_full
    FPB_AVAILABLE = True
    print("✅ Imported fpb_strategy.py")
except ImportError as e:
    FPB_AVAILABLE = False
    print(f"⚠️  Could not import fpb_strategy.py: {e}")

# Future: Add more strategies
# try:
#     from elite_orb_strategy import EliteORB, ORBConfig
#     ORB_AVAILABLE = True
# except ImportError:
#     ORB_AVAILABLE = False

# === IMPORT ALPACA FOR PAPER TRADING ===
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("⚠️  alpaca-py not installed. Run: pip install alpaca-py")


# ==============================================================================
# CONFIGURATION
# ==============================================================================
class QuantConfig:
    """
    Quant Engine Configuration
    
    Get your Alpaca keys from: https://app.alpaca.markets/paper/dashboard/overview
    """
    
    def __init__(
        self,
        # Alpaca API (get from dashboard)
        alpaca_api_key: str = "YOUR_API_KEY_HERE",
        alpaca_secret_key: str = "YOUR_SECRET_KEY_HERE",
        
        # Mode: "backtest", "paper", or "live"
        mode: str = "backtest",
        
        # Risk settings
        capital: float = 10000.0,
        risk_per_trade: float = 250.0,
        max_positions: int = 3,
    ):
        self.ALPACA_API_KEY = alpaca_api_key
        self.ALPACA_SECRET_KEY = alpaca_secret_key
        self.mode = mode
        self.capital = capital
        self.risk_per_trade = risk_per_trade
        self.max_positions = max_positions


# ==============================================================================
# ALPACA TRADER (Paper/Live)
# ==============================================================================
class AlpacaTrader:
    """Handles Alpaca API for paper/live trading"""
    
    def __init__(self, config: QuantConfig):
        self.config = config
        self.client = None
        self.connected = False
        
        if not ALPACA_AVAILABLE:
            print("❌ Alpaca not installed")
            return
        
        if config.ALPACA_API_KEY == "YOUR_API_KEY_HERE":
            print("⚠️  Alpaca API keys not set!")
            print("   Get keys: https://app.alpaca.markets/paper/dashboard/overview")
            return
        
        self._connect()
    
    def _connect(self):
        try:
            is_paper = self.config.mode in ["backtest", "paper"]
            
            self.client = TradingClient(
                api_key=self.config.ALPACA_API_KEY,
                secret_key=self.config.ALPACA_SECRET_KEY,
                paper=is_paper
            )
            
            account = self.client.get_account()
            self.connected = True
            
            print(f"✅ Connected to Alpaca ({'Paper' if is_paper else 'LIVE'})")
            print(f"   Equity: ${float(account.equity):,.2f}")
            print(f"   Buying Power: ${float(account.buying_power):,.2f}")
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
    
    def get_positions(self) -> List[Dict]:
        if not self.connected:
            return []
        try:
            positions = self.client.get_all_positions()
            return [{
                'symbol': p.symbol,
                'qty': float(p.qty),
                'entry': float(p.avg_entry_price),
                'pnl': float(p.unrealized_pl),
            } for p in positions]
        except:
            return []
    
    def buy(self, symbol: str, qty: int) -> bool:
        """Place a BUY order"""
        if not self.connected:
            return False
        try:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            self.client.submit_order(order)
            print(f"   ✅ BUY {qty} {symbol}")
            return True
        except Exception as e:
            print(f"   ❌ BUY failed: {e}")
            return False
    
    def sell(self, symbol: str, qty: int) -> bool:
        """Place a SELL order"""
        if not self.connected:
            return False
        try:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            self.client.submit_order(order)
            print(f"   ✅ SELL {qty} {symbol}")
            return True
        except Exception as e:
            print(f"   ❌ SELL failed: {e}")
            return False
    
    def close_all(self):
        """Close all positions"""
        if not self.connected:
            return
        try:
            self.client.close_all_positions(cancel_orders=True)
            print("✅ All positions closed")
        except:
            pass


# ==============================================================================
# QUANT ENGINE
# ==============================================================================
class QuantEngine:
    """
    Multi-Strategy Quant Engine
    
    This engine:
    1. Loads stocks from your scanner (watchlist.json)
    2. Runs YOUR actual strategies (fpb_strategy.py, etc.)
    3. Picks the best trades
    4. Optionally executes via Alpaca (paper/live)
    """
    
    def __init__(self, config: QuantConfig = None):
        self.config = config or QuantConfig()
        self.trader = None
        self.results = []
        
        # Setup logging
        self.log_dir = Path("logs/quant_engine")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Connect to Alpaca if paper/live mode
        if self.config.mode in ["paper", "live"]:
            self.trader = AlpacaTrader(self.config)
    
    def run_fpb_backtest(self) -> Dict:
        """
        Run YOUR fpb_strategy.py on scanner watchlist
        
        This uses your EXACT code - 600 lines, tested, 47.7% win rate
        """
        if not FPB_AVAILABLE:
            print("❌ fpb_strategy.py not available")
            return {}
        
        print("\n" + "="*70)
        print("🎯 RUNNING FPB STRATEGY (Your Actual Code)")
        print("="*70)
        
        # Load stocks from scanner
        symbols = load_watchlist_symbols()
        if not symbols:
            print("❌ No stocks in watchlist!")
            return {}
        
        # Setup YOUR strategy with YOUR config
        fpb_config = FPBConfig(
            min_gap_pct=3.0,
            risk_dollars=self.config.risk_per_trade,
            target_r1=1.5,
            target_r2=3.0,
        )
        
        logger = FPBTradeLogger()
        strategy = FirstPullbackBuy(config=fpb_config, logger=logger)
        
        print(f"\n⚙️  FPB Settings:")
        print(f"   Min Gap: {fpb_config.min_gap_pct}%")
        print(f"   Risk: ${fpb_config.risk_dollars}/trade")
        print(f"   Targets: {fpb_config.target_r1}R / {fpb_config.target_r2}R")
        
        # Run on each stock
        all_results = []
        
        for symbol in symbols:
            df = download_stock_data(symbol, days=60)
            if df is None:
                continue
            
            try:
                result = strategy.run_backtest(df, symbol=symbol)
                all_results.append(result)
            except Exception as e:
                print(f"   ❌ {symbol}: {e}")
        
        # Save trades
        logger.save()
        
        # Summary
        total_trades = sum(r.get('trades', 0) for r in all_results)
        total_pnl = sum(r.get('total_pnl', 0) for r in all_results)
        total_winners = sum(r.get('winners', 0) for r in all_results)
        
        print("\n" + "="*70)
        print("📊 FPB RESULTS")
        print("="*70)
        print(f"   Stocks: {len(all_results)}")
        print(f"   Trades: {total_trades}")
        if total_trades > 0:
            print(f"   Win Rate: {(total_winners/total_trades)*100:.1f}%")
            print(f"   Total PnL: ${total_pnl:.2f}")
        
        self.results = all_results
        return {
            'strategy': 'FPB',
            'stocks': len(all_results),
            'trades': total_trades,
            'winners': total_winners,
            'pnl': total_pnl,
            'results': all_results
        }
    
    def run_fpb_live(self) -> List[Dict]:
        """
        Run FPB strategy and find TODAY's signals (for paper/live trading)
        
        Returns list of trade signals to execute
        """
        if not FPB_AVAILABLE:
            print("❌ fpb_strategy.py not available")
            return []
        
        print("\n" + "="*70)
        print("🔴 LIVE MODE - Finding Today's FPB Setups")
        print("="*70)
        
        # Load watchlist
        watchlist = load_watchlist_full()
        if not watchlist:
            print("❌ No stocks!")
            return []
        
        # Setup strategy
        fpb_config = FPBConfig(
            min_gap_pct=3.0,
            risk_dollars=self.config.risk_per_trade,
        )
        strategy = FirstPullbackBuy(config=fpb_config)
        
        signals = []
        
        for stock in watchlist:
            symbol = stock.get('symbol', '')
            gap_pct = stock.get('gap_pct', 0)
            
            # Skip non-gappers for FPB
            if abs(gap_pct) < 3.0:
                continue
            
            print(f"\n   Checking {symbol} (gap: {gap_pct:+.1f}%)...")
            
            # Get today's data
            df = download_stock_data(symbol, days=5)
            if df is None:
                continue
            
            # Prepare data with indicators
            df = strategy.prepare_data(df)
            
            # Get today only
            today = df.index[-1].date()
            today_df = df[df.index.date == today]
            
            if len(today_df) < 5:
                continue
            
            # Get previous close for gap calculation
            prev_close = strategy.get_previous_close(df, today)
            if prev_close is None:
                continue
            
            # Check for setup
            had_spike, direction = strategy.check_initial_spike(today_df, prev_close)
            if not had_spike:
                continue
            
            # Find entry
            early_df = today_df.iloc[:3]
            spike_high = early_df['high'].max()
            spike_low = early_df['low'].min()
            
            signal = strategy.find_pullback_entry(today_df, direction, spike_high, spike_low)
            
            if signal:
                signal['symbol'] = symbol
                signal['gap_pct'] = gap_pct
                signals.append(signal)
                
                emoji = "🟢" if direction == "LONG" else "🔴"
                print(f"   {emoji} SIGNAL: {direction} @ ${signal['entry_price']:.2f}")
                print(f"      Stop: ${signal['stop_price']:.2f}")
                print(f"      Target: ${signal['target_r1']:.2f} / ${signal['target_r2']:.2f}")
                print(f"      Shares: {signal['shares']}")
        
        print(f"\n📊 Found {len(signals)} signals")
        return signals
    
    def execute_signals(self, signals: List[Dict]):
        """Execute signals via Alpaca"""
        if not self.trader or not self.trader.connected:
            print("⚠️  Not connected to Alpaca")
            return
        
        if not signals:
            print("   No signals to execute")
            return
        
        print("\n" + "="*70)
        print("📤 EXECUTING ORDERS")
        print("="*70)
        
        # Limit to max positions
        signals = signals[:self.config.max_positions]
        
        for signal in signals:
            symbol = signal['symbol']
            shares = signal['shares']
            direction = signal['direction']
            
            if direction == "LONG":
                self.trader.buy(symbol, shares)
            else:
                self.trader.sell(symbol, shares)
    
    def run(self, execute: bool = False):
        """
        Main entry point
        
        Args:
            execute: If True, actually place orders (paper/live)
        """
        print("\n" + "="*70)
        print("🤖 QUANT ENGINE v3.0")
        print(f"   Mode: {self.config.mode.upper()}")
        print(f"   Using: YOUR actual fpb_strategy.py")
        print("="*70)
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.config.mode == "backtest":
            # Run backtest on historical data
            return self.run_fpb_backtest()
        
        else:
            # Paper/Live mode - find today's signals
            signals = self.run_fpb_live()
            
            if execute and signals:
                self.execute_signals(signals)
            elif signals:
                print("\n⚠️  Signals found but execute=False")
                print("   To execute: engine.run(execute=True)")
            
            return {'signals': signals}


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🤖 QUANT ENGINE v3.0")
    print("="*70)
    
    # === CONFIGURATION ===
    config = QuantConfig(
        # Get these from Alpaca dashboard
        alpaca_api_key="YOUR_API_KEY_HERE",
        alpaca_secret_key="YOUR_SECRET_KEY_HERE",
        
        # Mode: "backtest", "paper", or "live"
        mode="backtest",
        
        # Risk settings
        capital=10000,
        risk_per_trade=250,
        max_positions=3,
    )
    
    # === RUN ===
    engine = QuantEngine(config)
    
    if config.mode == "backtest":
        # Backtest mode - test on historical data
        results = engine.run()
        
    else:
        # Paper/Live mode
        # First run without executing to see signals:
        results = engine.run(execute=False)
        
        # To actually execute trades:
        # results = engine.run(execute=True)
    
    print("\n✅ Done!")