"""
==============================================================================
FPB PAPER TRADER v3 - CONTINUOUS SCANNING + MONITORING
==============================================================================
WHAT'S NEW IN v3:
- Continuous entry scanning from 9:35 AM to 11:00 AM (every 5 minutes)
- Simultaneously monitors existing positions (every 10 seconds)
- Stops scanning when max positions reached, resumes if position closes
- Single command does everything: scan, enter, monitor, exit

THE FPB TIMELINE:
  9:30 AM      - Market opens, stock gaps up
  9:30-9:45 AM - Stock spikes higher (initial move)
  9:40-10:30 AM - Stock pulls back to EMA (THIS is when entries form)
  
  Old bot: Scanned once at 9:35, found nothing, gave up
  New bot: Keeps scanning every 5 min until setups appear

COMMANDS:
  python fpb_paper_trader.py              # THE MAIN ONE - does everything
  python fpb_paper_trader.py scan         # One-time scan (no monitoring)
  python fpb_paper_trader.py monitor      # Just monitor existing positions
  python fpb_paper_trader.py status       # Show current state
  python fpb_paper_trader.py close        # Close all positions
  python fpb_paper_trader.py log          # Today's activity + slippage
  python fpb_paper_trader.py slippage     # All-time slippage analysis

DAILY ROUTINE (SIMPLIFIED):
  9:25 AM  - Run scanner: python scanners/run_daily.py --now
  9:35 AM  - Run: python fpb_paper_trader.py
             (That's it! Bot handles everything until 4 PM)

==============================================================================
"""

import os
import sys
import json
import time
import random
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# === YOUR ALPACA KEYS (Paper Trading) ===
# Keys live in the .env file next to this script (never uploaded to GitHub).
# See .env.example for the format.
def _load_env_file(path: Path):
    """Read KEY=value lines from .env into os.environ (real env vars win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_env_file(Path(__file__).resolve().parent / ".env")
ALPACA_API_KEY =os.getenv("ALPACA_API_KEY", "YOUR_API_KEY_HERE")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "YOUR_SECRET_KEY_HERE")

# === RISK SETTINGS ===
RISK_PERCENT = 1.0              # Risk 1% of account per trade
MAX_POSITIONS = 3               # Max simultaneous positions
MAX_DAILY_LOSS = 500.0          # Stop trading if down $500 today
DEFAULT_CAPITAL = 10000.0       # Fallback if can't get account equity

# === TIMING SETTINGS ===
SCAN_INTERVAL = 300             # Scan for NEW entries every 5 minutes (300 sec)
MONITOR_INTERVAL = 10           # Check EXISTING positions every 10 seconds
EMA_CHECK_INTERVAL = 6          # Update trailing stop every 6th monitor cycle (60 sec)
SYNC_CHECK_INTERVAL = 6         # Re-check positions with Alpaca every 6th monitor cycle (60 sec)
FILL_WAIT_SECONDS = 10          # How long to wait for Alpaca to confirm an order filled
SCAN_START_TIME = "09:35"       # Start scanning for entries
SCAN_END_TIME = "11:00"         # Stop scanning for new entries
EOD_EXIT_TIME = "15:55"         # Close all positions
MARKET_CLOSE_TIME = "16:00"     # Stop everything

# === STRATEGY SETTINGS ===
TARGET_R1 = 1.5                 # First target (sell half)
TARGET_R2 = 3.0                 # Second target (close rest)
USE_EMA_TRAIL = True            # Trail with 9 EMA after R1
ALLOW_SHORTS = True             # True = trade LONG and SHORT setups. False = longs only

# === SIMULATION SETTINGS ===
SIM_SLIPPAGE_PCT = 0.15         # Simulate 0.15% slippage in sim mode

# === FILE PATHS ===
# Found from this file's location, so the bot runs from any folder or computer
BOT_DIR = str(Path(__file__).resolve().parent)
LOG_DIR = f"{BOT_DIR}/logs/paper_trades"
STATE_FILE = f"{BOT_DIR}/logs/paper_trades/position_state.json"

# Add bot directory to path
sys.path.insert(0, BOT_DIR)
sys.path.insert(0, f"{BOT_DIR}/scanners")

# ==============================================================================
# IMPORTS
# ==============================================================================
try:
    from fpb_strategy import (
        FirstPullbackBuy, 
        FPBConfig, 
        load_watchlist_symbols,
        download_stock_data
    )
    print("✅ Imported fpb_strategy.py")
except ImportError as e:
    print(f"❌ Could not import fpb_strategy.py: {e}")
    sys.exit(1)

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
    from alpaca.trading.requests import MarketOrderRequest, ClosePositionRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("⚠️  Alpaca not installed. Run: pip install alpaca-py")
    print("   Will run in SIMULATION mode\n")


# ==============================================================================
# POSITION STATE MANAGER
# ==============================================================================
class PositionStateManager:
    """Tracks position state, survives restarts"""
    
    def __init__(self):
        self.state_file = Path(STATE_FILE)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.positions: Dict[str, Dict] = self._load()
        self.lock = threading.Lock()
    
    def _load(self) -> Dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                today = datetime.now().strftime("%Y-%m-%d")
                if data.get('date') == today:
                    return data.get('positions', {})
            except:
                pass
        return {}
    
    def _save(self):
        data = {
            'date': datetime.now().strftime("%Y-%m-%d"),
            'last_updated': datetime.now().isoformat(),
            'positions': self.positions
        }
        with open(self.state_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_position(self, symbol: str, entry_price: float, signal_price: float,
                     stop_price: float, target_r1: float, target_r2: float, 
                     shares: int, direction: str, risk_dollars: float):
        with self.lock:
            entry_slippage = abs(entry_price - signal_price)
            entry_slippage_pct = (entry_slippage / signal_price) * 100 if signal_price > 0 else 0
            
            self.positions[symbol] = {
                'entry_price': entry_price,
                'signal_price': signal_price,
                'stop_price': stop_price,
                'current_stop': stop_price,
                'target_r1': target_r1,
                'target_r2': target_r2,
                'original_shares': shares,
                'shares_remaining': shares,
                'direction': direction,
                'risk_dollars': risk_dollars,
                'hit_r1': False,
                'entry_time': datetime.now().isoformat(),
                'realized_pnl': 0.0,
                'entry_slippage': entry_slippage,
                'entry_slippage_pct': entry_slippage_pct,
                'exit_slippage_total': 0.0,
            }
            self._save()
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        with self.lock:
            return self.positions.get(symbol)
    
    def update_position(self, symbol: str, **kwargs):
        with self.lock:
            if symbol in self.positions:
                self.positions[symbol].update(kwargs)
                self._save()
    
    def remove_position(self, symbol: str):
        with self.lock:
            if symbol in self.positions:
                del self.positions[symbol]
                self._save()
    
    def get_all_positions(self) -> Dict:
        with self.lock:
            return dict(self.positions)
    
    def position_count(self) -> int:
        with self.lock:
            return len(self.positions)
    
    def has_position(self, symbol: str) -> bool:
        with self.lock:
            return symbol in self.positions


# ==============================================================================
# TRADE LOGGER
# ==============================================================================
class PaperTradeLog:
    """Logs all trading activity"""
    
    def __init__(self):
        self.log_dir = Path(LOG_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"paper_{self.today}.json"
        self.trades = self._load()
        self.lock = threading.Lock()
        
    def _load(self) -> List[Dict]:
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _save(self):
        with open(self.log_file, 'w') as f:
            json.dump(self.trades, f, indent=2)
    
    def log(self, entry: Dict):
        with self.lock:
            entry['timestamp'] = datetime.now().isoformat()
            self.trades.append(entry)
            self._save()
    
    def get_daily_pnl(self) -> float:
        with self.lock:
            pnl = 0.0
            for t in self.trades:
                if t.get('type') in ['SELL_R1', 'SELL_R2', 'SELL_STOP', 'SELL_EOD', 'SELL_TRAIL']:
                    pnl += t.get('pnl', 0)
            return pnl
    
    def get_daily_slippage(self) -> Dict:
        with self.lock:
            entry_slippage = 0.0
            exit_slippage = 0.0
            entry_count = 0
            exit_count = 0
            
            for t in self.trades:
                if t.get('type') == 'ENTRY':
                    entry_slippage += t.get('slippage', 0)
                    entry_count += 1
                elif t.get('type') in ['SELL_R1', 'SELL_R2', 'SELL_STOP', 'SELL_EOD', 'SELL_TRAIL']:
                    exit_slippage += t.get('slippage', 0)
                    exit_count += 1
            
            return {
                'entry_total': entry_slippage,
                'exit_total': exit_slippage,
                'total': entry_slippage + exit_slippage,
                'entry_count': entry_count,
                'exit_count': exit_count,
                'avg_entry': entry_slippage / entry_count if entry_count > 0 else 0,
                'avg_exit': exit_slippage / exit_count if exit_count > 0 else 0,
            }
    
    def get_symbols_traded_today(self) -> set:
        """Get symbols we've already traded today (avoid re-entry)"""
        with self.lock:
            return {t.get('symbol') for t in self.trades if t.get('type') == 'ENTRY'}


# ==============================================================================
# ALPACA CLIENT
# ==============================================================================
class AlpacaClient:
    """Handles all Alpaca API interactions"""
    
    def __init__(self):
        self.trading_client = None
        self.data_client = None
        self.connected = False
        self.equity = DEFAULT_CAPITAL
        self.sim_mode = False
        self.shorting_enabled = True
        self._shortable: Dict[str, bool] = {}

        if not ALPACA_AVAILABLE:
            print("⚠️  Running in SIMULATION mode (no Alpaca)")
            self.sim_mode = True
            return
            
        if ALPACA_API_KEY == "YOUR_API_KEY_HERE":
            print("⚠️  API keys not set! Add them to the .env file (see .env.example).")
            print("   Running in SIMULATION mode\n")
            self.sim_mode = True
            return
            
        try:
            self.trading_client = TradingClient(
                api_key=ALPACA_API_KEY,
                secret_key=ALPACA_SECRET_KEY,
                paper=True
            )
            
            self.data_client = StockHistoricalDataClient(
                api_key=ALPACA_API_KEY,
                secret_key=ALPACA_SECRET_KEY
            )
            
            account = self.trading_client.get_account()
            self.connected = True
            self.equity = float(account.equity)
            self.shorting_enabled = bool(account.shorting_enabled)

            print(f"✅ Connected to Alpaca PAPER Trading")
            print(f"   Equity: ${self.equity:,.2f}")
            print(f"   Buying Power: ${float(account.buying_power):,.2f}")
            if not self.shorting_enabled:
                print("   ⚠️  Shorting is disabled on this Alpaca account: SHORT setups will be skipped")

        except Exception as e:
            # Keys are set, so real positions may exist. Pretending (simulation) here would let the
            # bot "close" trades on paper while the real ones stay open, so stop instead.
            print(f"❌ Alpaca connection failed: {e}")
            print("   Stopping. Check your internet connection and the keys in .env, then try again.")
            sys.exit(1)
    
    def get_risk_dollars(self) -> float:
        return self.equity * RISK_PERCENT / 100
    
    def _add_sim_slippage(self, price: float, direction: str, is_entry: bool) -> float:
        slip_pct = random.uniform(0, SIM_SLIPPAGE_PCT) / 100
        slip_amount = price * slip_pct
        if is_entry:
            return price + slip_amount if direction == "LONG" else price - slip_amount
        else:
            return price - slip_amount if direction == "LONG" else price + slip_amount
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        if self.sim_mode:
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.history(period="1d", interval="1m")
                if len(data) > 0:
                    return float(data['Close'].iloc[-1])
            except:
                pass
            return None
        
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quote = self.data_client.get_stock_latest_quote(request)
            if symbol in quote:
                bid = float(quote[symbol].bid_price)
                ask = float(quote[symbol].ask_price)
                return (bid + ask) / 2
        except:
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.history(period="1d", interval="1m")
                if len(data) > 0:
                    return float(data['Close'].iloc[-1])
            except:
                pass
        return None
    
    def get_current_ema9(self, symbol: str) -> Optional[float]:
        try:
            df = yf.download(symbol, period="5d", interval="5m", progress=False)
            if df is not None and len(df) > 9:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                ema9 = df['Close'].ewm(span=9, adjust=False).mean()
                return float(ema9.iloc[-1])
        except:
            pass
        return None
    
    def get_positions(self) -> Optional[Dict]:
        """
        What Alpaca actually holds: {symbol: {'qty', 'side', ...}}. 'qty' is always
        positive; 'side' is 'long' or 'short'. Returns None if Alpaca can't be reached,
        which callers must treat as "unknown", never as "we own nothing".
        """
        if self.sim_mode:
            return {}
        try:
            positions = self.trading_client.get_all_positions()
            return {p.symbol: {
                'qty': abs(int(float(p.qty))),
                'side': str(getattr(p.side, 'value', p.side)).lower(),
                'entry': float(p.avg_entry_price),
                'current': float(p.current_price),
                'pnl': float(p.unrealized_pl),
                'pnl_pct': float(p.unrealized_plpc) * 100
            } for p in positions}
        except Exception as e:
            print(f"   ⚠️  Could not get positions from Alpaca: {e}")
            return None

    def get_open_order_symbols(self) -> Optional[set]:
        """Symbols with an order still working at Alpaca. None if Alpaca can't be reached."""
        if self.sim_mode:
            return set()
        try:
            orders = self.trading_client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
            return {o.symbol for o in orders}
        except Exception as e:
            print(f"   ⚠️  Could not get open orders from Alpaca: {e}")
            return None

    def can_short(self, symbol: str) -> bool:
        """True if Alpaca lets us short this stock today (shortable and easy to borrow)."""
        if self.sim_mode:
            return True
        if not self.shorting_enabled:
            return False
        if symbol not in self._shortable:
            try:
                asset = self.trading_client.get_asset(symbol)
                self._shortable[symbol] = bool(asset.shortable and asset.easy_to_borrow)
            except Exception as e:
                print(f"   ⚠️  Could not check if {symbol} can be shorted: {e}")
                return False
        return self._shortable[symbol]

    def _wait_for_fill(self, order_id) -> Tuple[Optional[float], int]:
        """
        Ask Alpaca how an order actually filled: (average fill price, shares filled).
        If it's still not done after FILL_WAIT_SECONDS, cancel the rest so it can't
        fill later without the bot knowing.
        """
        done = {'filled', 'canceled', 'expired', 'rejected', 'done_for_day'}
        deadline = time.time() + FILL_WAIT_SECONDS
        order = None
        while True:
            try:
                order = self.trading_client.get_order_by_id(order_id)
            except Exception as e:
                print(f"   ⚠️  Could not check order status: {e}")
            status = str(getattr(order.status, 'value', order.status)).lower() if order else ''
            if status in done or time.time() >= deadline:
                break
            time.sleep(0.5)

        if order is None:
            return None, 0
        if status not in done:
            print(f"   ⚠️  Order not finished after {FILL_WAIT_SECONDS}s ({status}). Cancelling the rest.")
            try:
                self.trading_client.cancel_order_by_id(order_id)
                time.sleep(1)
                order = self.trading_client.get_order_by_id(order_id)
            except Exception as e:
                print(f"   ⚠️  Cancel failed: {e}")

        filled = int(float(order.filled_qty or 0))
        price = float(order.filled_avg_price) if order.filled_avg_price else None
        return (price, filled) if filled > 0 else (None, 0)
    
    def buy(self, symbol: str, shares: int, direction: str = "LONG") -> Tuple[Optional[float], int]:
        if self.sim_mode:
            price = self.get_current_price(symbol)
            if price:
                fill_price = self._add_sim_slippage(price, direction, is_entry=True)
                print(f"   [SIM] BUY {shares} {symbol} @ ${fill_price:.2f}")
                return fill_price, shares
            return None, 0
        
        try:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=shares,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            submitted = self.trading_client.submit_order(order)
            fill_price, filled = self._wait_for_fill(submitted.id)
            if filled:
                print(f"   ✅ BUY {filled} {symbol} @ ${fill_price:.2f}")
            else:
                print(f"   ❌ BUY {shares} {symbol} did not fill")
            return fill_price, filled

        except Exception as e:
            print(f"   ❌ BUY failed: {e}")
            return None, 0
    
    def sell_short(self, symbol: str, shares: int) -> Tuple[Optional[float], int]:
        """Open a SHORT position. Only for entries; exits must use close()."""
        if self.sim_mode:
            price = self.get_current_price(symbol)
            if price:
                fill_price = self._add_sim_slippage(price, "SHORT", is_entry=True)
                print(f"   [SIM] SELL SHORT {shares} {symbol} @ ${fill_price:.2f}")
                return fill_price, shares
            return None, 0

        try:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=shares,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            submitted = self.trading_client.submit_order(order)
            fill_price, filled = self._wait_for_fill(submitted.id)
            if filled:
                print(f"   ✅ SELL SHORT {filled} {symbol} @ ${fill_price:.2f}")
            else:
                print(f"   ❌ SELL SHORT {shares} {symbol} did not fill")
            return fill_price, filled

        except Exception as e:
            print(f"   ❌ SELL SHORT failed: {e}")
            return None, 0

    def close(self, symbol: str, shares: int, direction: str) -> Tuple[Optional[float], int]:
        """
        Exit part or all of a position (targets, stops, trail, end of day).
        Uses Alpaca's close-position order: Alpaca picks the side itself (SELL a long,
        BUY back a short), and it can only shrink a position, never grow or flip it.
        """
        action = "SELL" if direction == "LONG" else "BUY TO COVER"
        if self.sim_mode:
            price = self.get_current_price(symbol)
            if price:
                fill_price = self._add_sim_slippage(price, direction, is_entry=False)
                print(f"   [SIM] {action} {shares} {symbol} @ ${fill_price:.2f}")
                return fill_price, shares
            return None, 0

        try:
            submitted = self.trading_client.close_position(symbol, ClosePositionRequest(qty=str(shares)))
            fill_price, filled = self._wait_for_fill(submitted.id)
            if filled:
                print(f"   ✅ {action} {filled} {symbol} @ ${fill_price:.2f}")
            else:
                print(f"   ❌ {action} {shares} {symbol} did not fill")
            return fill_price, filled

        except Exception as e:
            print(f"   ❌ {action} failed: {e}")
            return None, 0
    
    def close_all(self):
        if self.sim_mode:
            print("[SIM] Would close all positions")
            return
        try:
            self.trading_client.close_all_positions(cancel_orders=True)
            print("✅ All positions closed")
        except Exception as e:
            print(f"❌ Error closing: {e}")


# ==============================================================================
# BROKER SYNC (Alpaca is the truth; the bot's records must match it)
# ==============================================================================
class BrokerSync:
    """
    Compares the bot's records with what Alpaca actually holds and fixes the bot's side:
    - Alpaca no longer holds a position  -> remove it from the bot's records
    - Alpaca holds a different share count -> use Alpaca's number
    - Alpaca holds something the bot didn't open -> leave it alone, warn, never trade it
    If Alpaca can't be reached, sync() returns False and no new trades should be placed.
    """

    def __init__(self, alpaca: AlpacaClient, state: PositionStateManager, log: PaperTradeLog):
        self.alpaca = alpaca
        self.state = state
        self.log = log
        self.broker_positions: Dict[str, Dict] = {}
        self.open_order_symbols: set = set()
        self.unknown: set = set()       # held at Alpaca, not opened by the bot
        self._warned: set = set()

    def sync(self) -> bool:
        if self.alpaca.sim_mode:
            return True     # simulation: the bot's records are the only truth

        positions = self.alpaca.get_positions()
        open_orders = self.alpaca.get_open_order_symbols()
        if positions is None or open_orders is None:
            print("   ⚠️  Can't confirm positions with Alpaca. No new trades until it answers.")
            return False

        for symbol, pos in self.state.get_all_positions().items():
            held = positions.get(symbol)
            bot_side = 'long' if pos['direction'] == "LONG" else 'short'
            if held is None:
                just_entered = datetime.now() - datetime.fromisoformat(pos['entry_time']) < timedelta(seconds=60)
                if symbol in open_orders or just_entered:
                    continue    # an order is still working or Alpaca hasn't listed it yet; look again next time
                self._drop(symbol, pos, "Alpaca no longer holds it (closed outside the bot)")
            elif held['side'] != bot_side:
                self._drop(symbol, pos, f"Alpaca holds a {held['side'].upper()} position, "
                                        f"the bot thought {pos['direction']}")
            elif held['qty'] != pos['shares_remaining']:
                print(f"   🔄 {symbol}: bot had {pos['shares_remaining']} shares, "
                      f"Alpaca has {held['qty']}. Using Alpaca's number.")
                self.state.update_position(symbol, shares_remaining=held['qty'])
                self.log.log({'type': 'SYNC_QTY', 'symbol': symbol,
                              'bot_shares': pos['shares_remaining'], 'alpaca_shares': held['qty']})

        self.broker_positions = positions
        self.open_order_symbols = open_orders
        self.unknown = set(positions) - set(self.state.get_all_positions())
        for symbol in sorted(self.unknown - self._warned):
            held = positions[symbol]
            print(f"   ⚠️  {symbol}: Alpaca holds {held['qty']} shares {held['side'].upper()} that the bot "
                  f"didn't open today. The bot won't trade or close it; close it in Alpaca if unwanted.")
            self._warned.add(symbol)
        return True

    def _drop(self, symbol: str, pos: Dict, reason: str):
        print(f"   🔄 {symbol}: {reason}. Removed from the bot's records.")
        self.state.remove_position(symbol)
        self.log.log({'type': 'SYNC_REMOVED', 'symbol': symbol,
                      'shares': pos['shares_remaining'], 'reason': reason})

    def slots_used(self) -> int:
        """Positions counting toward MAX_POSITIONS, including ones the bot didn't open."""
        return self.state.position_count() + len(self.unknown)

    def is_busy(self, symbol: str) -> bool:
        """True if Alpaca already holds this stock or has an order working for it."""
        return symbol in self.broker_positions or symbol in self.open_order_symbols


# ==============================================================================
# ENTRY SCANNER (runs periodically)
# ==============================================================================
class EntryScanner:
    """Scans for new FPB entries"""
    
    def __init__(self, alpaca: AlpacaClient, state: PositionStateManager,
                 log: PaperTradeLog, sync: Optional[BrokerSync] = None):
        self.alpaca = alpaca
        self.state = state
        self.log = log
        self.sync = sync or BrokerSync(alpaca, state, log)
        self.strategy = None
        self.symbols = []
        self.last_scan_time = None
        self.skipped_shorts = set()

    def load_watchlist(self):
        """Load watchlist once"""
        self.symbols = load_watchlist_symbols()
        print(f"📋 Loaded {len(self.symbols)} symbols from watchlist")
        
    def initialize_strategy(self):
        """Initialize FPB strategy"""
        risk_dollars = self.alpaca.get_risk_dollars()
        config = FPBConfig(
            min_gap_pct=3.0,
            risk_dollars=risk_dollars,
            target_r1=TARGET_R1,
            target_r2=TARGET_R2,
        )
        self.strategy = FirstPullbackBuy(config=config)
        print(f"💰 Risk per trade: ${risk_dollars:.2f} ({RISK_PERCENT}%)")
    
    def scan_once(self) -> List[str]:
        """
        Scan all symbols for FPB entries.
        Returns list of symbols where trades were entered.
        """
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # Check if we're in scanning window
        if current_time < SCAN_START_TIME:
            return []
        if current_time > SCAN_END_TIME:
            return []
        
        # Confirm with Alpaca what we really hold before looking for new trades
        if not self.sync.sync():
            return []

        # Check position limit
        if self.sync.slots_used() >= MAX_POSITIONS:
            return []
        
        # Get symbols we've already traded today (don't re-enter)
        traded_today = self.log.get_symbols_traded_today()
        
        trades_entered = []
        
        print(f"\n[{now.strftime('%H:%M:%S')}] 🔍 Scanning for FPB entries...")
        
        for symbol in self.symbols:
            # Skip if already in position (bot or Alpaca), an order is working, or traded today
            if self.state.has_position(symbol) or self.sync.is_busy(symbol):
                continue
            if symbol in traded_today:
                continue

            # Check position limit again (might have filled during loop)
            if self.sync.slots_used() >= MAX_POSITIONS:
                break
            
            # Download fresh data
            try:
                df = download_stock_data(symbol, days=5)
                if df is None or len(df) < 10:
                    continue
                
                df = self.strategy.prepare_data(df)
                
                # Get today's data
                today = datetime.now().date()
                today_df = df[df.index.date == today]
                
                if len(today_df) < 3:
                    # Not enough bars yet
                    continue
                
                # Get previous close
                prev_close = self.strategy.get_previous_close(df, today_df.index[0].date())
                if prev_close is None:
                    continue
                
                # Check for initial spike
                had_spike, direction = self.strategy.check_initial_spike(today_df, prev_close)
                if not had_spike:
                    continue

                # Shorts only if switched on and Alpaca allows shorting this stock (say so once)
                if direction == "SHORT":
                    reason = None
                    if not ALLOW_SHORTS:
                        reason = "ALLOW_SHORTS = False"
                    elif not self.alpaca.can_short(symbol):
                        reason = "Alpaca says it can't be shorted today"
                    if reason:
                        if symbol not in self.skipped_shorts:
                            print(f"   ⏭️  {symbol}: SHORT setup skipped ({reason})")
                            self.skipped_shorts.add(symbol)
                        continue

                # Get spike levels
                early_df = today_df.iloc[:3]
                spike_high = early_df['high'].max()
                spike_low = early_df['low'].min()
                
                # Look for pullback entry
                signal = self.strategy.find_pullback_entry(today_df, direction, spike_high, spike_low)
                if signal is None:
                    continue
                
                # === SIGNAL FOUND! ===
                gap_pct = ((today_df.iloc[0]['open'] - prev_close) / prev_close) * 100
                
                print(f"\n🟢 SIGNAL: {symbol} ({direction})")
                print(f"   Gap: {gap_pct:+.1f}%")
                print(f"   Entry: ${signal['entry_price']:.2f}")
                print(f"   Stop: ${signal['stop_price']:.2f}")
                print(f"   Targets: ${signal['target_r1']:.2f} / ${signal['target_r2']:.2f}")
                print(f"   Shares: {signal['shares']} (${signal['risk_dollars']:.0f} risk)")
                # Last check with Alpaca right before ordering
                if not self.sync.sync():
                    break
                if self.sync.slots_used() >= MAX_POSITIONS:
                    break
                if self.sync.is_busy(symbol):
                    print(f"   ⏭️  {symbol}: skipped, Alpaca already has a position or order for it")
                    continue
                print(f"   → Entering trade...")

                # Enter trade
                if direction == "LONG":
                    fill_price, actual_shares = self.alpaca.buy(symbol, signal['shares'], direction)
                else:
                    fill_price, actual_shares = self.alpaca.sell_short(symbol, signal['shares'])
                
                if fill_price and actual_shares > 0:
                    # Add to state
                    self.state.add_position(
                        symbol=symbol,
                        entry_price=fill_price,
                        signal_price=signal['entry_price'],
                        stop_price=signal['stop_price'],
                        target_r1=signal['target_r1'],
                        target_r2=signal['target_r2'],
                        shares=actual_shares,
                        direction=direction,
                        risk_dollars=signal['risk_dollars']
                    )
                    
                    trades_entered.append(symbol)
                    
                    # Log entry
                    entry_slippage = abs(fill_price - signal['entry_price'])
                    self.log.log({
                        'type': 'ENTRY',
                        'symbol': symbol,
                        'direction': direction,
                        'shares': actual_shares,
                        'signal_price': signal['entry_price'],
                        'fill_price': fill_price,
                        'slippage': entry_slippage,
                        'slippage_pct': (entry_slippage / signal['entry_price']) * 100,
                        'stop': signal['stop_price'],
                        'target_r1': signal['target_r1'],
                        'target_r2': signal['target_r2']
                    })
                    
            except Exception as e:
                # Skip symbols that error, but say why
                print(f"   ⚠️  {symbol}: skipped after an error ({e})")
                continue

        self.last_scan_time = now

        if trades_entered:
            print(f"\n📊 Scan complete: {len(trades_entered)} new trades entered")
        else:
            positions = self.sync.slots_used()
            print(f"   No new setups found. ({positions}/{MAX_POSITIONS} positions)")
        
        return trades_entered


# ==============================================================================
# POSITION MONITOR (runs frequently)
# ==============================================================================
class PositionMonitor:
    """Monitors existing positions for exits"""
    
    def __init__(self, alpaca: AlpacaClient, state: PositionStateManager, 
                 log: PaperTradeLog):
        self.alpaca = alpaca
        self.state = state
        self.log = log
        self.check_count = 0
    
    def _calculate_exit_slippage(self, fill_price: float, planned_price: float, 
                                  shares: int, direction: str) -> float:
        if direction == "LONG":
            slippage_per_share = planned_price - fill_price
        else:
            slippage_per_share = fill_price - planned_price
        return max(0, slippage_per_share * shares)
    
    def check_position(self, symbol: str, verbose: bool = True) -> Optional[str]:
        """Check single position, return action taken"""
        pos = self.state.get_position(symbol)
        if not pos:
            return None
        
        current_price = self.alpaca.get_current_price(symbol)
        if current_price is None:
            return 'HOLD'
        
        entry_price = pos['entry_price']
        current_stop = pos['current_stop']
        target_r1 = pos['target_r1']
        target_r2 = pos['target_r2']
        shares_remaining = pos['shares_remaining']
        direction = pos['direction']
        hit_r1 = pos['hit_r1']
        
        # Calculate PnL
        if direction == "LONG":
            unrealized_pnl = (current_price - entry_price) * shares_remaining
        else:
            unrealized_pnl = (entry_price - current_price) * shares_remaining
        
        if verbose:
            r1_status = "✅" if hit_r1 else ""
            print(f"   {symbol}: ${current_price:.2f} | Stop: ${current_stop:.2f} | "
                  f"R1: ${target_r1:.2f} {r1_status} | PnL: ${unrealized_pnl:+.2f}")
        
        # === CHECK STOP LOSS ===
        if direction == "LONG" and current_price <= current_stop:
            return self._exit_stop(symbol, pos, current_price)
        elif direction == "SHORT" and current_price >= current_stop:
            return self._exit_stop(symbol, pos, current_price)
        
        # === CHECK R1 TARGET ===
        if not hit_r1:
            if direction == "LONG" and current_price >= target_r1:
                return self._exit_r1(symbol, pos, current_price)
            elif direction == "SHORT" and current_price <= target_r1:
                return self._exit_r1(symbol, pos, current_price)
        
        # === CHECK R2 TARGET ===
        if hit_r1:
            if direction == "LONG" and current_price >= target_r2:
                return self._exit_r2(symbol, pos, current_price)
            elif direction == "SHORT" and current_price <= target_r2:
                return self._exit_r2(symbol, pos, current_price)
        
        # === TRAIL STOP WITH EMA ===
        if hit_r1 and USE_EMA_TRAIL and (self.check_count % EMA_CHECK_INTERVAL == 0):
            ema9 = self.alpaca.get_current_ema9(symbol)
            if ema9:
                if direction == "LONG":
                    new_stop = ema9 * 0.998
                    if new_stop > current_stop:
                        self.state.update_position(symbol, current_stop=new_stop)
                        print(f"   📈 {symbol}: Trail stop raised to ${new_stop:.2f}")
                        if current_price <= new_stop:
                            return self._exit_trail(symbol, pos, current_price, new_stop)
                else:
                    new_stop = ema9 * 1.002
                    if new_stop < current_stop:
                        self.state.update_position(symbol, current_stop=new_stop)
                        print(f"   📉 {symbol}: Trail stop lowered to ${new_stop:.2f}")
                        if current_price >= new_stop:
                            return self._exit_trail(symbol, pos, current_price, new_stop)
        
        return 'HOLD'
    
    def _exit_r1(self, symbol: str, pos: Dict, current_price: float) -> str:
        shares_to_sell = pos['shares_remaining'] // 2
        if shares_to_sell == 0:
            shares_to_sell = pos['shares_remaining']
        
        print(f"\n🎯 {symbol} HIT R1 TARGET!")
        
        fill_price, actual_shares = self.alpaca.close(symbol, shares_to_sell, pos['direction'])
        if not actual_shares:
            return self._exit_failed(symbol)
        
        slippage = self._calculate_exit_slippage(fill_price, pos['target_r1'], actual_shares, pos['direction'])
        
        entry_price = pos['entry_price']
        if pos['direction'] == "LONG":
            pnl = (fill_price - entry_price) * actual_shares
        else:
            pnl = (entry_price - fill_price) * actual_shares
        
        new_shares = pos['shares_remaining'] - actual_shares
        self.state.update_position(
            symbol,
            hit_r1=True,
            shares_remaining=new_shares,
            current_stop=entry_price,
            realized_pnl=pos['realized_pnl'] + pnl,
            exit_slippage_total=pos['exit_slippage_total'] + slippage
        )
        
        print(f"   Closed {actual_shares} @${fill_price:.2f} | PnL: ${pnl:.2f}")
        print(f"   Stop moved to breakeven (${entry_price:.2f}) | {new_shares} shares remaining")
        
        self.log.log({
            'type': 'SELL_R1',
            'symbol': symbol,
            'shares': actual_shares,
            'target_price': pos['target_r1'],
            'fill_price': fill_price,
            'slippage': slippage,
            'pnl': pnl
        })
        
        if new_shares <= 0:
            self.state.remove_position(symbol)
        
        return 'SELL_R1'
    
    def _exit_r2(self, symbol: str, pos: Dict, current_price: float) -> str:
        shares_to_sell = pos['shares_remaining']
        
        print(f"\n🏆 {symbol} HIT R2 TARGET!")
        
        fill_price, actual_shares = self.alpaca.close(symbol, shares_to_sell, pos['direction'])
        if not actual_shares:
            return self._exit_failed(symbol)
        
        slippage = self._calculate_exit_slippage(fill_price, pos['target_r2'], actual_shares, pos['direction'])
        
        entry_price = pos['entry_price']
        if pos['direction'] == "LONG":
            pnl = (fill_price - entry_price) * actual_shares
        else:
            pnl = (entry_price - fill_price) * actual_shares
        
        total_pnl = pos['realized_pnl'] + pnl
        total_slippage = pos['entry_slippage'] + pos['exit_slippage_total'] + slippage
        
        print(f"   Closed {actual_shares} @${fill_price:.2f}")
        print(f"   💰 Total PnL: ${total_pnl:.2f} | Slippage: ${total_slippage:.2f}")
        
        self.log.log({
            'type': 'SELL_R2',
            'symbol': symbol,
            'shares': actual_shares,
            'target_price': pos['target_r2'],
            'fill_price': fill_price,
            'slippage': slippage,
            'pnl': pnl,
            'total_pnl': total_pnl,
            'total_slippage': total_slippage
        })

        self._finish_exit(symbol, pos, actual_shares, pnl)
        return 'SELL_R2'
    
    def _exit_stop(self, symbol: str, pos: Dict, current_price: float) -> str:
        shares_to_sell = pos['shares_remaining']
        stop_type = "BREAKEVEN" if pos['hit_r1'] else "STOP LOSS"
        
        print(f"\n🛑 {symbol} HIT {stop_type}!")
        
        fill_price, actual_shares = self.alpaca.close(symbol, shares_to_sell, pos['direction'])
        if not actual_shares:
            return self._exit_failed(symbol)
        
        slippage = self._calculate_exit_slippage(fill_price, pos['current_stop'], actual_shares, pos['direction'])
        
        entry_price = pos['entry_price']
        if pos['direction'] == "LONG":
            pnl = (fill_price - entry_price) * actual_shares
        else:
            pnl = (entry_price - fill_price) * actual_shares
        
        total_pnl = pos['realized_pnl'] + pnl
        
        print(f"   Closed {actual_shares} @${fill_price:.2f} | PnL: ${pnl:.2f}")
        
        self.log.log({
            'type': 'SELL_STOP',
            'symbol': symbol,
            'shares': actual_shares,
            'stop_price': pos['current_stop'],
            'fill_price': fill_price,
            'slippage': slippage,
            'pnl': pnl,
            'total_pnl': total_pnl,
            'was_breakeven': pos['hit_r1']
        })

        self._finish_exit(symbol, pos, actual_shares, pnl)
        return 'SELL_STOP'
    
    def _exit_trail(self, symbol: str, pos: Dict, current_price: float, trail_stop: float) -> str:
        shares_to_sell = pos['shares_remaining']
        
        print(f"\n📉 {symbol} HIT TRAILING STOP!")
        
        fill_price, actual_shares = self.alpaca.close(symbol, shares_to_sell, pos['direction'])
        if not actual_shares:
            return self._exit_failed(symbol)
        
        slippage = self._calculate_exit_slippage(fill_price, trail_stop, actual_shares, pos['direction'])
        
        entry_price = pos['entry_price']
        if pos['direction'] == "LONG":
            pnl = (fill_price - entry_price) * actual_shares
        else:
            pnl = (entry_price - fill_price) * actual_shares
        
        total_pnl = pos['realized_pnl'] + pnl
        
        print(f"   Closed {actual_shares} @${fill_price:.2f} | Total PnL: ${total_pnl:.2f}")
        
        self.log.log({
            'type': 'SELL_TRAIL',
            'symbol': symbol,
            'shares': actual_shares,
            'trail_stop': trail_stop,
            'fill_price': fill_price,
            'slippage': slippage,
            'pnl': pnl,
            'total_pnl': total_pnl
        })

        self._finish_exit(symbol, pos, actual_shares, pnl)
        return 'SELL_TRAIL'
    
    def exit_eod(self, symbol: str) -> Optional[str]:
        """Exit at end of day"""
        pos = self.state.get_position(symbol)
        if not pos:
            return None

        shares_to_sell = pos['shares_remaining']
        
        print(f"\n⏰ EOD EXIT: {symbol}")
        
        fill_price, actual_shares = self.alpaca.close(symbol, shares_to_sell, pos['direction'])
        if not actual_shares:
            return self._exit_failed(symbol)
        
        entry_price = pos['entry_price']
        if pos['direction'] == "LONG":
            pnl = (fill_price - entry_price) * actual_shares
        else:
            pnl = (entry_price - fill_price) * actual_shares
        
        total_pnl = pos['realized_pnl'] + pnl
        
        print(f"   Closed {actual_shares} @${fill_price:.2f} | Total PnL: ${total_pnl:.2f}")
        
        self.log.log({
            'type': 'SELL_EOD',
            'symbol': symbol,
            'shares': actual_shares,
            'fill_price': fill_price,
            'pnl': pnl,
            'total_pnl': total_pnl
        })

        self._finish_exit(symbol, pos, actual_shares, pnl)
        return 'SELL_EOD'

    def _exit_failed(self, symbol: str) -> str:
        """Nothing filled: keep the position (Alpaca still holds it) and try again next check."""
        print(f"   ⚠️  {symbol}: exit did not go through. Keeping the position; will try again.")
        return 'EXIT_FAILED'

    def _finish_exit(self, symbol: str, pos: Dict, filled: int, pnl: float):
        """Remove a fully closed position, or keep the shares that didn't fill."""
        remaining = pos['shares_remaining'] - filled
        if remaining > 0:
            print(f"   ⚠️  Only {filled} of {pos['shares_remaining']} shares closed. "
                  f"Keeping {remaining}; will try again.")
            self.state.update_position(symbol, shares_remaining=remaining,
                                       realized_pnl=pos['realized_pnl'] + pnl)
        else:
            self.state.remove_position(symbol)

    def check_all_positions(self, verbose: bool = True):
        """Check all positions once"""
        self.check_count += 1
        positions = self.state.get_all_positions()
        
        if not positions:
            return
        
        if verbose:
            print(f"\n📊 Checking {len(positions)} position(s)...")
        
        for symbol in list(positions.keys()):
            self.check_position(symbol, verbose=verbose)


def close_all_tracked(monitor: PositionMonitor, sync: BrokerSync, tries: int = 3) -> bool:
    """Close every position the bot opened, confirm with Alpaca, and retry a few times."""
    for attempt in range(tries):
        for symbol in list(monitor.state.get_all_positions().keys()):
            monitor.exit_eod(symbol)
        sync.sync()
        if not monitor.state.get_all_positions():
            return True
        if attempt < tries - 1:
            time.sleep(MONITOR_INTERVAL)
    still_open = ', '.join(monitor.state.get_all_positions().keys())
    print(f"\n🚨 STILL OPEN after {tries} tries: {still_open}. Close them in Alpaca now!")
    return False


# ==============================================================================
# MAIN TRADING ENGINE (combines scanning + monitoring)
# ==============================================================================
class TradingEngine:
    """
    The main engine that runs everything:
    - Scans for new entries every 5 minutes (until 11 AM)
    - Monitors existing positions every 10 seconds
    - Handles EOD exit and daily loss limit
    """
    
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.state = PositionStateManager()
        self.log = PaperTradeLog()
        self.sync = BrokerSync(self.alpaca, self.state, self.log)
        self.scanner = EntryScanner(self.alpaca, self.state, self.log, self.sync)
        self.monitor = PositionMonitor(self.alpaca, self.state, self.log)
        self.running = False
        self.last_scan_time = None
    
    def should_scan(self) -> bool:
        """Check if we should scan for new entries"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # Only scan during window
        if current_time < SCAN_START_TIME or current_time > SCAN_END_TIME:
            return False
        
        # Don't scan if at max positions
        if self.sync.slots_used() >= MAX_POSITIONS:
            return False
        
        # Scan every SCAN_INTERVAL seconds
        if self.last_scan_time is None:
            return True
        
        elapsed = (now - self.last_scan_time).total_seconds()
        return elapsed >= SCAN_INTERVAL
    
    def run(self):
        """Main loop - runs until market close"""
        print("\n" + "="*70)
        print("🚀 FPB TRADING ENGINE v3 STARTED")
        print("="*70)
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏰ Scanning for entries: {SCAN_START_TIME} - {SCAN_END_TIME} (every {SCAN_INTERVAL//60} min)")
        print(f"👁️  Monitoring positions: every {MONITOR_INTERVAL} seconds")
        print(f"🛑 EOD exit: {EOD_EXIT_TIME}")
        print(f"⏹️  Press Ctrl+C to stop")
        print("="*70)
        
        # Start from what Alpaca actually holds, not from memory
        print("\n🔄 Checking positions with Alpaca...")
        if not self.sync.sync():
            print("❌ Can't confirm positions with Alpaca. Stopping; try again in a minute.")
            return
        print(f"   Bot positions: {self.state.position_count()} | Not opened by bot: {len(self.sync.unknown)}")

        # Initialize
        self.scanner.load_watchlist()
        self.scanner.initialize_strategy()

        self.running = True
        iteration = 0
        
        try:
            while self.running:
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                iteration += 1
                
                # === CHECK MARKET CLOSE ===
                if current_time >= MARKET_CLOSE_TIME:
                    print("\n⏹️  Market closed. Shutting down.")
                    break
                
                # === CHECK EOD EXIT ===
                if current_time >= EOD_EXIT_TIME:
                    print("\n⏰ EOD EXIT TIME")
                    if close_all_tracked(self.monitor, self.sync):
                        print("\n✅ All positions closed (confirmed with Alpaca). Shutting down.")
                    break

                # === CHECK DAILY LOSS LIMIT ===
                daily_pnl = self.log.get_daily_pnl()
                if daily_pnl <= -MAX_DAILY_LOSS:
                    print(f"\n🛑 DAILY LOSS LIMIT HIT (${daily_pnl:.2f})")
                    close_all_tracked(self.monitor, self.sync)
                    print("Shutting down for the day.")
                    break

                # === RE-CHECK WITH ALPACA (every minute) ===
                if iteration % SYNC_CHECK_INTERVAL == 0:
                    self.sync.sync()

                # === SCAN FOR NEW ENTRIES ===
                if self.should_scan():
                    self.scanner.scan_once()
                    self.last_scan_time = now
                
                # === MONITOR EXISTING POSITIONS ===
                verbose = (iteration % 3 == 0)  # Verbose every 30 seconds
                self.monitor.check_all_positions(verbose=verbose)
                
                # === SHOW STATUS (every minute) ===
                if iteration % 6 == 0:  # Every 60 seconds
                    positions = self.sync.slots_used()
                    daily_pnl = self.log.get_daily_pnl()
                    slip = self.log.get_daily_slippage()
                    
                    status_parts = [f"Positions: {positions}/{MAX_POSITIONS}"]
                    if daily_pnl != 0:
                        emoji = "🟢" if daily_pnl > 0 else "🔴"
                        status_parts.append(f"{emoji} PnL: ${daily_pnl:.2f}")
                    if slip['total'] > 0:
                        status_parts.append(f"Slip: ${slip['total']:.2f}")
                    
                    in_scan_window = SCAN_START_TIME <= current_time <= SCAN_END_TIME
                    if in_scan_window and positions < MAX_POSITIONS:
                        next_scan = self.last_scan_time + timedelta(seconds=SCAN_INTERVAL) if self.last_scan_time else now
                        mins_to_scan = max(0, (next_scan - now).total_seconds() // 60)
                        status_parts.append(f"Next scan: {int(mins_to_scan)}m")
                    elif not in_scan_window:
                        status_parts.append("Scan window closed")
                    
                    print(f"\n[{now.strftime('%H:%M:%S')}] {' | '.join(status_parts)}")
                
                # === WAIT ===
                time.sleep(MONITOR_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopped by user")
            
            positions = self.state.get_all_positions()
            if positions:
                print(f"\n⚠️  You have {len(positions)} open position(s)!")
                print("   Run 'python fpb_paper_trader.py close' to close them")
        
        # Final summary
        self._print_summary()
    
    def _print_summary(self):
        """Print end-of-session summary"""
        print("\n" + "="*70)
        print("📊 SESSION SUMMARY")
        print("="*70)
        
        daily_pnl = self.log.get_daily_pnl()
        slip = self.log.get_daily_slippage()
        
        emoji = "🟢" if daily_pnl >= 0 else "🔴"
        print(f"{emoji} Net PnL: ${daily_pnl:.2f}")
        print(f"📈 Entries: {slip['entry_count']}")
        print(f"📉 Exits: {slip['exit_count']}")
        print(f"💸 Total Slippage: ${slip['total']:.2f}")
        
        positions = self.state.get_all_positions()
        if positions:
            print(f"\n⚠️  Open positions: {list(positions.keys())}")
        if self.sync.unknown:
            print(f"⚠️  Alpaca also holds (not opened by the bot): {sorted(self.sync.unknown)}")

        print("="*70)


# ==============================================================================
# COMMAND FUNCTIONS
# ==============================================================================

def cmd_run():
    """Main command - run the full trading engine"""
    engine = TradingEngine()
    engine.run()


def cmd_scan():
    """One-time scan only"""
    alpaca = AlpacaClient()
    state = PositionStateManager()
    log = PaperTradeLog()
    
    scanner = EntryScanner(alpaca, state, log)
    scanner.load_watchlist()
    scanner.initialize_strategy()
    scanner.scan_once()
    
    print("\n💡 To run continuous scanning + monitoring:")
    print("   python fpb_paper_trader.py")


def cmd_monitor():
    """Monitor existing positions only"""
    alpaca = AlpacaClient()
    state = PositionStateManager()
    log = PaperTradeLog()
    sync = BrokerSync(alpaca, state, log)

    if not sync.sync():
        print("\n❌ Can't confirm positions with Alpaca. Try again in a minute.")
        return

    positions = state.get_all_positions()
    if not positions:
        print("\n⚠️  No positions to monitor!")
        return

    print(f"\n📊 Monitoring {len(positions)} position(s)")
    print("Press Ctrl+C to stop\n")

    monitor = PositionMonitor(alpaca, state, log)
    loops = 0

    try:
        while True:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            loops += 1

            if current_time >= EOD_EXIT_TIME:
                print("\n⏰ EOD - Closing all")
                close_all_tracked(monitor, sync)
                break

            if loops % SYNC_CHECK_INTERVAL == 0:
                sync.sync()

            if not state.get_all_positions():
                print("\n✅ All positions closed.")
                break

            print(f"\n[{now.strftime('%H:%M:%S')}] Checking positions...")
            monitor.check_all_positions(verbose=True)

            time.sleep(MONITOR_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n⏹️  Stopped")


def cmd_status():
    """Show current status"""
    alpaca = AlpacaClient()
    state = PositionStateManager()
    log = PaperTradeLog()
    
    print("\n" + "="*70)
    print("📊 STATUS")
    print("="*70)
    
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    # Time status
    if current_time < SCAN_START_TIME:
        print(f"⏰ Pre-market. Scanning starts at {SCAN_START_TIME}")
    elif current_time <= SCAN_END_TIME:
        print(f"⏰ In scanning window ({SCAN_START_TIME} - {SCAN_END_TIME})")
    else:
        print(f"⏰ Scanning window closed. Monitoring only.")
    
    # Positions
    tracked = state.get_all_positions()
    print(f"\n📈 Positions ({len(tracked)}/{MAX_POSITIONS}):")
    if tracked:
        for sym, pos in tracked.items():
            r1 = "✅R1" if pos['hit_r1'] else ""
            print(f"   {sym}: {pos['shares_remaining']} shares @ ${pos['entry_price']:.2f} | "
                  f"Stop: ${pos['current_stop']:.2f} {r1}")
    else:
        print("   (none)")

    # What Alpaca actually holds (the truth)
    if not alpaca.sim_mode:
        held = alpaca.get_positions()
        print(f"\n🏦 Alpaca holds:")
        if held is None:
            print("   (couldn't reach Alpaca)")
        elif not held:
            print("   (nothing)")
        for sym, h in (held or {}).items():
            note = "" if sym in tracked else "   ⚠️ not opened by the bot today"
            print(f"   {sym}: {h['qty']} shares {h['side'].upper()} @ ${h['entry']:.2f}{note}")

    # Daily stats
    daily_pnl = log.get_daily_pnl()
    slip = log.get_daily_slippage()
    emoji = "🟢" if daily_pnl >= 0 else "🔴"
    
    print(f"\n{emoji} Daily PnL: ${daily_pnl:.2f}")
    print(f"💸 Slippage: ${slip['total']:.2f}")
    print(f"📊 Trades today: {slip['entry_count']} entries, {slip['exit_count']} exits")
    print("="*70)


def cmd_close():
    """Close all positions"""
    alpaca = AlpacaClient()
    state = PositionStateManager()
    log = PaperTradeLog()
    
    print("\n🔴 CLOSING ALL POSITIONS\n")
    
    monitor = PositionMonitor(alpaca, state, log)
    
    tracked = state.get_all_positions()
    for symbol in list(tracked.keys()):
        monitor.exit_eod(symbol)

    alpaca.close_all()

    # Confirm with Alpaca
    if alpaca.sim_mode:
        print("\n✅ Done! (simulation)")
        return
    time.sleep(2)
    held = alpaca.get_positions()
    if held is None:
        print("\n⚠️  Couldn't confirm with Alpaca. Check the Alpaca website.")
    elif held:
        print(f"\n🚨 Alpaca still holds: {', '.join(held)}. Check the Alpaca website.")
    else:
        BrokerSync(alpaca, state, log).sync()   # clear anything the bot still remembers
        print("\n✅ Done! Alpaca confirms no open positions.")


def cmd_log():
    """Show today's log"""
    log = PaperTradeLog()
    
    print("\n" + "="*70)
    print(f"📋 TODAY'S LOG ({log.today})")
    print("="*70 + "\n")
    
    if not log.trades:
        print("No activity today\n")
        return
    
    for entry in log.trades:
        t = entry.get('timestamp', '')[11:19]
        typ = entry.get('type', '?')
        sym = entry.get('symbol', '?')
        
        if typ == 'ENTRY':
            slip = entry.get('slippage', 0)
            print(f"[{t}] 📥 {sym} ENTRY: {entry.get('shares')} shares @ ${entry.get('fill_price', 0):.2f} "
                  f"(signal: ${entry.get('signal_price', 0):.2f}, slip: ${slip:.2f})")
            
        elif typ == 'SELL_R1':
            print(f"[{t}] 🎯 {sym} R1: sold {entry.get('shares')} @ ${entry.get('fill_price', 0):.2f} "
                  f"| PnL: ${entry.get('pnl', 0):.2f}")
            
        elif typ == 'SELL_R2':
            print(f"[{t}] 🏆 {sym} R2: sold {entry.get('shares')} @ ${entry.get('fill_price', 0):.2f} "
                  f"| Total: ${entry.get('total_pnl', 0):.2f}")
            
        elif typ == 'SELL_STOP':
            be = "(BE)" if entry.get('was_breakeven') else ""
            print(f"[{t}] 🛑 {sym} STOP{be}: sold {entry.get('shares')} @ ${entry.get('fill_price', 0):.2f} "
                  f"| PnL: ${entry.get('pnl', 0):.2f}")
            
        elif typ == 'SELL_TRAIL':
            print(f"[{t}] 📉 {sym} TRAIL: sold {entry.get('shares')} @ ${entry.get('fill_price', 0):.2f} "
                  f"| Total: ${entry.get('total_pnl', 0):.2f}")
            
        elif typ == 'SELL_EOD':
            print(f"[{t}] ⏰ {sym} EOD: sold {entry.get('shares')} @ ${entry.get('fill_price', 0):.2f} "
                  f"| Total: ${entry.get('total_pnl', 0):.2f}")

        elif typ == 'SYNC_REMOVED':
            print(f"[{t}] 🔄 {sym} removed from bot records: {entry.get('reason', '')}")

        elif typ == 'SYNC_QTY':
            print(f"[{t}] 🔄 {sym} share count fixed: bot had {entry.get('bot_shares')}, "
                  f"Alpaca had {entry.get('alpaca_shares')}")
    
    # Summary
    print("\n" + "-"*70)
    daily_pnl = log.get_daily_pnl()
    slip = log.get_daily_slippage()
    
    emoji = "🟢" if daily_pnl >= 0 else "🔴"
    print(f"{emoji} Net PnL: ${daily_pnl:.2f}")
    print(f"💸 Slippage: ${slip['total']:.2f} (entry: ${slip['entry_total']:.2f}, exit: ${slip['exit_total']:.2f})")
    
    if abs(daily_pnl) > 0.01:
        impact = (slip['total'] / abs(daily_pnl)) * 100
        print(f"   Slippage impact: {impact:.1f}% of gross PnL")
    print()


def cmd_slippage():
    """Slippage analysis across all days"""
    log_dir = Path(LOG_DIR)
    
    print("\n" + "="*70)
    print("📉 SLIPPAGE ANALYSIS (ALL TIME)")
    print("="*70)
    
    all_trades = []
    for log_file in sorted(log_dir.glob("paper_*.json")):
        try:
            with open(log_file, 'r') as f:
                trades = json.load(f)
                for t in trades:
                    t['date'] = log_file.stem.replace('paper_', '')
                all_trades.extend(trades)
        except:
            pass
    
    if not all_trades:
        print("\nNo trades found.\n")
        return
    
    entry_slips = [t.get('slippage', 0) for t in all_trades if t.get('type') == 'ENTRY']
    exit_slips = [t.get('slippage', 0) for t in all_trades if t.get('type') in ['SELL_R1', 'SELL_R2', 'SELL_STOP', 'SELL_EOD', 'SELL_TRAIL']]
    
    total_entry = sum(entry_slips)
    total_exit = sum(exit_slips)
    
    print(f"\n📊 {len(entry_slips)} entries, {len(exit_slips)} exits")
    print(f"   Entry slippage:  ${total_entry:.2f}" + (f" (avg ${total_entry/len(entry_slips):.2f})" if entry_slips else ""))
    print(f"   Exit slippage:   ${total_exit:.2f}" + (f" (avg ${total_exit/len(exit_slips):.2f})" if exit_slips else ""))
    print(f"   TOTAL:           ${total_entry + total_exit:.2f}")
    
    # By symbol
    symbols = {}
    for t in all_trades:
        sym = t.get('symbol', 'UNK')
        if sym not in symbols:
            symbols[sym] = {'entry': 0, 'exit': 0, 'count': 0}
        if t.get('type') == 'ENTRY':
            symbols[sym]['entry'] += t.get('slippage', 0)
            symbols[sym]['count'] += 1
        elif t.get('type') in ['SELL_R1', 'SELL_R2', 'SELL_STOP', 'SELL_EOD', 'SELL_TRAIL']:
            symbols[sym]['exit'] += t.get('slippage', 0)
    
    if symbols:
        print(f"\n{'Symbol':<8} {'Trades':<8} {'Entry':<10} {'Exit':<10} {'Total':<10}")
        print("-"*46)
        for sym, data in sorted(symbols.items(), key=lambda x: x[1]['entry'] + x[1]['exit'], reverse=True):
            total = data['entry'] + data['exit']
            print(f"{sym:<8} {data['count']:<8} ${data['entry']:<8.2f} ${data['exit']:<8.2f} ${total:<8.2f}")
    print()


def cmd_help():
    """Show help"""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  FPB PAPER TRADER v3 - CONTINUOUS SCANNING + MONITORING              ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  COMMANDS:                                                           ║
║    python fpb_paper_trader.py           THE MAIN ONE (does everything)║
║    python fpb_paper_trader.py scan      One-time scan                ║
║    python fpb_paper_trader.py monitor   Monitor existing positions   ║
║    python fpb_paper_trader.py status    Show current state           ║
║    python fpb_paper_trader.py close     Close all positions          ║
║    python fpb_paper_trader.py log       Today's log + slippage       ║
║    python fpb_paper_trader.py slippage  All-time slippage analysis   ║
║                                                                      ║
║  WHAT v3 DOES:                                                       ║
║    ✅ Scans for NEW entries every 5 min (9:35 AM - 11:00 AM)         ║
║    ✅ Monitors EXISTING positions every 10 sec                       ║
║    ✅ Stops scanning when at max positions (3)                       ║
║    ✅ Resumes scanning if a position closes                          ║
║    ✅ Auto EOD exit at 3:55 PM                                       ║
║    ✅ Daily loss limit ($500)                                        ║
║                                                                      ║
║  DAILY ROUTINE:                                                      ║
║    9:25 AM  - Run scanner: python scanners/run_daily.py --now       ║
║    9:35 AM  - Run: python fpb_paper_trader.py                        ║
║              (That's it! Bot does everything until 4 PM)             ║
║                                                                      ║
║  SETTINGS (top of file):                                             ║
║    RISK_PERCENT = 1.0         # 1% risk per trade                    ║
║    MAX_POSITIONS = 3          # Max concurrent                       ║
║    MAX_DAILY_LOSS = 500       # Stop if down $500                    ║
║    SCAN_INTERVAL = 300        # Scan every 5 minutes                 ║
║    MONITOR_INTERVAL = 10      # Check positions every 10 sec         ║
║    SCAN_END_TIME = "11:00"    # Stop looking for new entries         ║
║    ALLOW_SHORTS = True        # Long AND short (False = longs only)  ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    
    print("\n" + "="*70)
    print("🎯 FPB PAPER TRADER v3")
    print("="*70)
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        
        if cmd in ['scan', 's']:
            cmd_scan()
        elif cmd in ['monitor', 'm']:
            cmd_monitor()
        elif cmd in ['status', 'st']:
            cmd_status()
        elif cmd in ['close', 'c']:  
            cmd_close()
        elif cmd in ['log', 'l']:
            cmd_log()
        elif cmd in ['slippage', 'slip']:
            cmd_slippage()
        elif cmd in ['help', 'h', '-h', '--help']:
            cmd_help()
        else:
            cmd_run()
    else:
        cmd_run()