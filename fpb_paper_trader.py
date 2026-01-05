"""
==============================================================================
FPB PAPER TRADER - Uses YOUR EXACT Strategy Code
==============================================================================
This imports your fpb_strategy.py directly - no simplified version.
Your tested 47.7% win rate code runs the signals, Alpaca executes.

SETUP:
1. Get Alpaca paper trading keys from: https://app.alpaca.markets/paper/dashboard/overview
2. Set your API keys below (lines 25-26)
3. Run: python fpb_paper_trader.py

DAILY ROUTINE:
  9:25 AM  - Run scanner: cd scanners && python run_daily.py --now
  9:35 AM  - Run this: python fpb_paper_trader.py
  10:30 AM - Check positions: python fpb_paper_trader.py monitor
  3:55 PM  - Close all: python fpb_paper_trader.py close

==============================================================================
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

# === YOUR ALPACA KEYS (Paper Trading) ===
# Get from: https://app.alpaca.markets/paper/dashboard/overview
ALPACA_API_KEY = "YOUR_API_KEY_HERE"        # <-- PASTE YOUR KEY
ALPACA_SECRET_KEY = "YOUR_SECRET_KEY_HERE"  # <-- PASTE YOUR SECRET

# === SETTINGS ===
RISK_PERCENT = 1.0           # Risk 1% of account per trade
MAX_POSITIONS = 3            # Max simultaneous positions
DEFAULT_CAPITAL = 10000.0    # Fallback if can't get account equity

# === FILE PATHS ===
BOT_DIR = "C:/Users/Hassan/ORB-Bot"
LOG_DIR = f"{BOT_DIR}/logs/paper_trades"

# Add bot directory to path so we can import fpb_strategy
sys.path.insert(0, BOT_DIR)
sys.path.insert(0, f"{BOT_DIR}/scanners")

# ==============================================================================
# IMPORT YOUR ACTUAL FPB STRATEGY
# ==============================================================================
try:
    from fpb_strategy import (
        FirstPullbackBuy, 
        FPBConfig, 
        FPBTradeLogger,
        load_watchlist_symbols,
        load_watchlist_full,
        download_stock_data
    )
    FPB_AVAILABLE = True
    print("✅ Imported YOUR fpb_strategy.py (47.7% win rate code)")
except ImportError as e:
    FPB_AVAILABLE = False
    print(f"❌ Could not import fpb_strategy.py: {e}")
    print("   Make sure you're running from C:\\Users\\Hassan\\ORB-Bot\\")
    sys.exit(1)

# ==============================================================================
# OTHER IMPORTS
# ==============================================================================
try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("❌ Missing pandas/numpy. Run: pip install pandas numpy")
    sys.exit(1)

try:
    import yfinance as yf
except ImportError:
    print("❌ Missing yfinance. Run: pip install yfinance")
    sys.exit(1)

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("⚠️  Alpaca not installed. Run: pip install alpaca-py")
    print("   Will run in SIMULATION mode (no real orders)\n")


# ==============================================================================
# PAPER TRADE LOGGER
# ==============================================================================
class PaperTradeLog:
    """Logs paper trades separately from backtest logs"""
    
    def __init__(self):
        self.log_dir = Path(LOG_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"paper_{self.today}.json"
        self.trades = self._load()
        
    def _load(self) -> List[Dict]:
        if self.log_file.exists():
            with open(self.log_file, 'r') as f:
                return json.load(f)
        return []
    
    def _save(self):
        with open(self.log_file, 'w') as f:
            json.dump(self.trades, f, indent=2)
    
    def log(self, entry: Dict):
        entry['timestamp'] = datetime.now().isoformat()
        self.trades.append(entry)
        self._save()
        
    def get_todays_signals(self) -> List[Dict]:
        return [t for t in self.trades if t.get('type') == 'SIGNAL']


# ==============================================================================
# ALPACA PAPER TRADER
# ==============================================================================
class AlpacaPaper:
    """Handles Alpaca paper trading orders"""
    
    def __init__(self):
        self.client = None
        self.connected = False
        self.equity = DEFAULT_CAPITAL
        
        if not ALPACA_AVAILABLE:
            print("⚠️  Running in SIMULATION mode (no Alpaca)")
            return
            
        if ALPACA_API_KEY == "YOUR_API_KEY_HERE":
            print("⚠️  API keys not set! Edit lines 25-26 in this file.")
            print("   Running in SIMULATION mode\n")
            return
            
        try:
            self.client = TradingClient(
                api_key=ALPACA_API_KEY,
                secret_key=ALPACA_SECRET_KEY,
                paper=True  # ALWAYS paper
            )
            
            account = self.client.get_account()
            self.connected = True
            self.equity = float(account.equity)
            
            print(f"✅ Connected to Alpaca PAPER Trading")
            print(f"   Equity: ${self.equity:,.2f}")
            print(f"   Buying Power: ${float(account.buying_power):,.2f}")
            print(f"   Risk per trade: ${self.equity * RISK_PERCENT / 100:,.2f} ({RISK_PERCENT}%)\n")
            
        except Exception as e:
            print(f"❌ Alpaca connection failed: {e}\n")
    
    def get_risk_dollars(self) -> float:
        """Calculate risk in dollars (1% of equity)"""
        return self.equity * RISK_PERCENT / 100
    
    def get_positions(self) -> Dict:
        if not self.connected:
            return {}
        try:
            positions = self.client.get_all_positions()
            return {p.symbol: {
                'qty': int(p.qty),
                'entry': float(p.avg_entry_price),
                'current': float(p.current_price),
                'pnl': float(p.unrealized_pl),
                'pnl_pct': float(p.unrealized_plpc) * 100
            } for p in positions}
        except:
            return {}
    
    def buy(self, symbol: str, shares: int) -> bool:
        if not self.connected:
            print(f"   [SIM] BUY {shares} {symbol}")
            return True
        try:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=shares,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            self.client.submit_order(order)
            print(f"   ✅ BUY {shares} {symbol}")
            return True
        except Exception as e:
            print(f"   ❌ BUY failed: {e}")
            return False
    
    def sell(self, symbol: str, shares: int) -> bool:
        if not self.connected:
            print(f"   [SIM] SELL {shares} {symbol}")
            return True
        try:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=shares,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            self.client.submit_order(order)
            print(f"   ✅ SELL {shares} {symbol}")
            return True
        except Exception as e:
            print(f"   ❌ SELL failed: {e}")
            return False
    
    def close_all(self):
        if not self.connected:
            print("[SIM] Would close all positions")
            return
        try:
            self.client.close_all_positions(cancel_orders=True)
            print("✅ All positions closed")
        except Exception as e:
            print(f"❌ Error closing: {e}")


# ==============================================================================
# MAIN PAPER TRADING FUNCTION
# ==============================================================================
def run_paper_trading():
    """
    Main function - finds FPB setups using YOUR EXACT STRATEGY CODE
    """
    
    print("\n" + "="*70)
    print("🎯 FPB PAPER TRADER - Using Your Exact Strategy")
    print("="*70)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💰 Risk: {RISK_PERCENT}% of equity | Max positions: {MAX_POSITIONS}")
    print("="*70 + "\n")
    
    # Initialize
    alpaca = AlpacaPaper()
    log = PaperTradeLog()
    
    # Get risk dollars (1% of account)
    risk_dollars = alpaca.get_risk_dollars()
    print(f"💵 Risk this session: ${risk_dollars:.2f} per trade\n")
    
    # Check existing positions
    positions = alpaca.get_positions()
    if positions:
        print(f"📊 Current positions: {list(positions.keys())}")
        if len(positions) >= MAX_POSITIONS:
            print(f"⚠️  Already at max positions ({MAX_POSITIONS}). Not scanning.")
            return
    
    # Load watchlist (uses YOUR load_watchlist_symbols function)
    print("📋 Loading watchlist...")
    symbols = load_watchlist_symbols()
    
    if not symbols:
        print("❌ No symbols in watchlist!")
        return
    
    print(f"   Symbols: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}\n")
    
    # Setup YOUR strategy with DYNAMIC risk (1% of account)
    config = FPBConfig(
        min_gap_pct=3.0,
        risk_dollars=risk_dollars,  # <-- Now uses 1% of account!
        target_r1=1.5,
        target_r2=3.0,
    )
    
    strategy = FirstPullbackBuy(config=config)
    
    # Track signals
    signals_found = []
    trades_entered = []
    
    print("🔍 Scanning for FPB setups...\n")
    
    for symbol in symbols:
        # Skip if already in position
        if symbol in positions:
            continue
        
        # Download TODAY's data (uses YOUR download function)
        df = download_stock_data(symbol, days=5)
        if df is None or len(df) < 10:
            continue
        
        # Prepare data with indicators (YOUR code)
        df = strategy.prepare_data(df)
        
        # Get today only
        today = datetime.now().date()
        today_df = df[df.index.date == today]
        
        if len(today_df) < 3:
            # Not enough bars yet, try yesterday for testing
            dates = sorted(set(df.index.date))
            if len(dates) >= 1:
                today_df = df[df.index.date == dates[-1]]
        
        if len(today_df) < 3:
            continue
        
        # Get previous close (YOUR method)
        prev_close = strategy.get_previous_close(df, today_df.index[0].date())
        if prev_close is None:
            continue
        
        # Check for initial spike (YOUR code)
        had_spike, direction = strategy.check_initial_spike(today_df, prev_close)
        
        if not had_spike:
            continue
        
        # Get spike levels
        early_df = today_df.iloc[:3]
        spike_high = early_df['high'].max()
        spike_low = early_df['low'].min()
        
        # Find pullback entry (YOUR code - the exact 47.7% logic)
        signal = strategy.find_pullback_entry(today_df, direction, spike_high, spike_low)
        
        if signal is None:
            continue
        
        # === SIGNAL FOUND! ===
        gap_pct = ((today_df.iloc[0]['open'] - prev_close) / prev_close) * 100
        
        signal_data = {
            'type': 'SIGNAL',
            'symbol': symbol,
            'direction': direction,
            'gap_pct': round(gap_pct, 2),
            'entry_price': round(signal['entry_price'], 2),
            'stop_price': round(signal['stop_price'], 2),
            'target_r1': round(signal['target_r1'], 2),
            'target_r2': round(signal['target_r2'], 2),
            'shares': signal['shares'],
            'risk_dollars': round(signal['risk_dollars'], 2),
            'ema_level': signal['ema_level'],
            'account_equity': alpaca.equity,
            'risk_percent': RISK_PERCENT,
        }
        
        signals_found.append(signal_data)
        
        print(f"🟢 SIGNAL: {symbol} ({direction})")
        print(f"   Gap: {gap_pct:+.1f}%")
        print(f"   Entry: ${signal['entry_price']:.2f}")
        print(f"   Stop: ${signal['stop_price']:.2f} (below {signal['ema_level']})")
        print(f"   Targets: ${signal['target_r1']:.2f} / ${signal['target_r2']:.2f}")
        print(f"   Shares: {signal['shares']} (${signal['risk_dollars']:.0f} risk = {RISK_PERCENT}%)")
        
        # Log signal
        log.log(signal_data)
        
        # Enter trade?
        current_positions = len(positions) + len(trades_entered)
        if current_positions < MAX_POSITIONS:
            print(f"   → Entering trade...")
            
            if direction == "LONG":
                success = alpaca.buy(symbol, signal['shares'])
            else:
                success = alpaca.sell(symbol, signal['shares'])  # Short
            
            if success:
                trades_entered.append(symbol)
                log.log({
                    'type': 'ENTRY',
                    'symbol': symbol,
                    'direction': direction,
                    'shares': signal['shares'],
                    'price': signal['entry_price']
                })
        else:
            print(f"   → Max positions reached, signal only")
        
        print()
    
    # Summary
    print("="*70)
    print("📊 SESSION SUMMARY")
    print("="*70)
    print(f"Account equity: ${alpaca.equity:,.2f}")
    print(f"Risk per trade: ${risk_dollars:.2f} ({RISK_PERCENT}%)")
    print(f"Symbols scanned: {len(symbols)}")
    print(f"Signals found: {len(signals_found)}")
    print(f"Trades entered: {len(trades_entered)}")
    
    if signals_found:
        print(f"\nSignals: {', '.join(s['symbol'] for s in signals_found)}")
    
    if trades_entered:
        print(f"Entered: {', '.join(trades_entered)}")
    
    # Show current positions
    positions = alpaca.get_positions()
    if positions:
        print(f"\n📈 Open Positions:")
        for sym, pos in positions.items():
            emoji = "🟢" if pos['pnl'] > 0 else "🔴"
            print(f"   {emoji} {sym}: {pos['qty']} @ ${pos['entry']:.2f} | PnL: ${pos['pnl']:.2f} ({pos['pnl_pct']:+.1f}%)")
    
    print(f"\n📁 Log: {LOG_DIR}/paper_{log.today}.json")
    print("\n✅ Done!")


def monitor_positions():
    """Show current positions"""
    print("\n" + "="*70)
    print("👀 POSITION MONITOR")
    print("="*70)
    
    alpaca = AlpacaPaper()
    positions = alpaca.get_positions()
    
    if not positions:
        print("No open positions\n")
        return
    
    print(f"\n📈 Open Positions ({len(positions)}):\n")
    
    total_pnl = 0
    for symbol, pos in positions.items():
        emoji = "🟢" if pos['pnl'] > 0 else "🔴"
        print(f"{emoji} {symbol}")
        print(f"   Shares: {pos['qty']}")
        print(f"   Entry: ${pos['entry']:.2f}")
        print(f"   Current: ${pos['current']:.2f}")
        print(f"   PnL: ${pos['pnl']:.2f} ({pos['pnl_pct']:+.1f}%)")
        print()
        total_pnl += pos['pnl']
    
    print(f"💰 Total PnL: ${total_pnl:.2f}")
    print(f"📊 Account Equity: ${alpaca.equity:,.2f}\n")


def close_all_positions():
    """Close everything (end of day)"""
    print("\n🔴 CLOSING ALL POSITIONS\n")
    
    alpaca = AlpacaPaper()
    alpaca.close_all()
    print()


def show_todays_log():
    """Show today's trading log"""
    log = PaperTradeLog()
    
    print("\n" + "="*70)
    print(f"📋 TODAY'S LOG ({log.today})")
    print("="*70 + "\n")
    
    if not log.trades:
        print("No trades logged today\n")
        return
    
    for entry in log.trades:
        t = entry.get('timestamp', '')[:19]
        typ = entry.get('type', '?')
        sym = entry.get('symbol', '?')
        
        if typ == 'SIGNAL':
            print(f"[{t}] 🟢 SIGNAL: {sym} {entry.get('direction')}")
            print(f"           Entry: ${entry.get('entry_price')} | Stop: ${entry.get('stop_price')}")
            print(f"           Risk: ${entry.get('risk_dollars')} ({entry.get('risk_percent')}% of ${entry.get('account_equity'):,.0f})")
        elif typ == 'ENTRY':
            print(f"[{t}] 📥 ENTRY: {sym} {entry.get('shares')} shares")
        else:
            print(f"[{t}] {typ}: {sym}")
    
    print()


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        
        if cmd in ['monitor', 'm', 'watch', 'positions']:
            monitor_positions()
        elif cmd in ['close', 'c', 'exit', 'flatten']:
            close_all_positions()
        elif cmd in ['log', 'l', 'today']:
            show_todays_log()
        elif cmd in ['help', 'h', '-h', '--help']:
            print("""
FPB Paper Trader - Uses YOUR exact strategy code

Commands:
  python fpb_paper_trader.py           Scan for setups and trade
  python fpb_paper_trader.py monitor   Show open positions
  python fpb_paper_trader.py close     Close all positions
  python fpb_paper_trader.py log       Show today's log

Settings (edit at top of file):
  RISK_PERCENT = 1.0    # Risk 1% of account per trade
  MAX_POSITIONS = 3     # Max simultaneous positions

Daily routine:
  9:25 AM  - Run scanner (cd scanners && python run_daily.py --now)
  9:35 AM  - Run this script
  10:30 AM - Check positions (monitor)
  3:55 PM  - Close all positions (close)
""")
        else:
            run_paper_trading()
    else:
        run_paper_trading()