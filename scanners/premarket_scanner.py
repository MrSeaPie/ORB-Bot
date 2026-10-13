"""
premarket_scanner.py - Pre-Market Gap Scanner
==============================================
Finds stocks gapping up OR down (for longs and shorts) with news/catalyst before market open.

Run: 6:00 AM - 9:25 AM Eastern
Output: watchlist_premarket.json

WHAT IT DOES:
1. Scans stocks for 3%+ gaps (up or down) from the previous close
2. Checks for news/catalyst
3. Filters by volume, price, float
4. Ranks by quality score
5. Outputs watchlist for day trading bot
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import warnings
warnings.filterwarnings('ignore')

# Gaps are measured against New York trading days
ET = ZoneInfo("America/New_York")

# Try to import Alpaca (optional - falls back to Yahoo)
try:
    from alpaca.data import StockHistoricalDataClient
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("⚠️  Alpaca not installed. Using Yahoo Finance instead.")
    print("   Install with: pip install alpaca-py")

import yfinance as yf
import pandas as pd

# Import config
try:
    from config import *
except ImportError:
    # Defaults if config not found
    MIN_GAP_PCT = 3.0
    MIN_PRICE = 5.0
    MAX_PRICE = 500.0
    MIN_PREMARKET_VOLUME = 100000
    MIN_RELATIVE_VOLUME = 2.0
    MIN_AVG_DAILY_VOLUME = 500000
    ALPACA_API_KEY = os.getenv('ALPACA_API_KEY', '')
    ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY', '')
    DEFAULT_UNIVERSE = ["NVDA", "AMD", "TSLA", "COIN", "MSTR"]

# File locations, found from this file so scans work from any folder
SCANNER_DIR = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(SCANNER_DIR, 'universe.txt')
OUTPUT_DIR = os.path.join(os.path.dirname(SCANNER_DIR), 'output')


def _et_dates(index):
    """New York calendar date of each timestamp in a price table's index."""
    idx = pd.DatetimeIndex(index)
    return (idx.tz_convert(ET) if idx.tz is not None else idx).date


# ==============================================================================
# PRE-MARKET SCANNER CLASS
# ==============================================================================
class PreMarketScanner:
    """
    Scans for gap-up stocks with news catalyst.
    
    Per Bulls Bootcamp:
    - Gap ≥ 3% from previous close
    - Price $5-500
    - Volume > average
    - Has news/catalyst
    """
    
    def __init__(self, api_key: str = None, secret_key: str = None):
        self.api_key = api_key or ALPACA_API_KEY
        self.secret_key = secret_key or ALPACA_SECRET_KEY
        
        # Initialize Alpaca client if available
        if ALPACA_AVAILABLE and self.api_key and self.api_key != 'YOUR_API_KEY_HERE':
            try:
                self.alpaca_client = StockHistoricalDataClient(self.api_key, self.secret_key)
                self.use_alpaca = True
                print("✅ Using Alpaca for data")
            except Exception as e:
                print(f"⚠️  Alpaca init failed: {e}")
                self.use_alpaca = False
        else:
            self.use_alpaca = False
            print("📊 Using Yahoo Finance for data")
        
        # Scanner settings (from config)
        self.min_gap_pct = MIN_GAP_PCT
        self.min_price = MIN_PRICE
        self.max_price = MAX_PRICE
        self.min_premarket_volume = MIN_PREMARKET_VOLUME
        self.min_relative_volume = MIN_RELATIVE_VOLUME
        self.min_avg_daily_volume = MIN_AVG_DAILY_VOLUME
        
    def get_universe(self) -> List[str]:
        """Get list of stocks to scan"""
        # Check for custom universe file
        if os.path.exists(UNIVERSE_FILE):
            with open(UNIVERSE_FILE, 'r') as f:
                symbols = []
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        symbols.append(line.upper())
            print(f"📋 Loaded {len(symbols)} symbols from universe.txt")
            return symbols
        
        # Use default
        return DEFAULT_UNIVERSE
    
    def get_stock_data_yahoo(self, symbol: str) -> Optional[Dict]:
        """
        Get stock data using Yahoo Finance.
        Gap = latest price TODAY (pre-market included) vs the last COMPLETED day's close.
        (Before the open Yahoo has no daily bar for today yet, so "last daily bar" would be
        yesterday and the gap would be yesterday's.)
        """
        try:
            ticker = yf.Ticker(symbol)
            today = datetime.now(ET).date()

            # Completed trading days only
            daily = ticker.history(period="1mo", interval="1d")
            if daily is None or len(daily) == 0:
                return None
            past = daily[_et_dates(daily.index) < today]
            if len(past) < 2:
                return None
            prev_close = float(past['Close'].iloc[-1])
            avg_volume = float(past['Volume'].tail(20).mean())

            # Today's trading so far, pre-market included
            intraday = ticker.history(period="2d", interval="1m", prepost=True)
            if intraday is None or len(intraday) == 0:
                return None
            today_bars = intraday[_et_dates(intraday.index) == today]
            if len(today_bars) == 0:
                return None     # no trades yet today
            current_price = float(today_bars['Close'].iloc[-1])
            today_volume = float(today_bars['Volume'].sum())

            gap_pct = ((current_price - prev_close) / prev_close) * 100
            rel_vol = today_volume / avg_volume if avg_volume > 0 else 0    # today so far vs a full day

            return {
                'symbol': symbol,
                'prev_close': round(prev_close, 2),
                'current_price': round(current_price, 2),
                'gap_pct': round(gap_pct, 2),
                'volume': int(today_volume),
                'avg_volume': int(avg_volume),
                'relative_volume': round(rel_vol, 2)
            }

        except Exception as e:
            return None
    
    def get_stock_data_alpaca(self, symbol: str) -> Optional[Dict]:
        """Get stock data using Alpaca API"""
        try:
            # Get daily bars for previous close (IEX feed: allowed on the free plan)
            end = datetime.now(ET)
            start = end - timedelta(days=10)

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                feed=DataFeed.IEX
            )
            bars = self.alpaca_client.get_stock_bars(request)

            # Completed trading days only (today's bar may be missing or still forming)
            today = end.date()
            completed = [b for b in bars.data.get(symbol, []) if b.timestamp.astimezone(ET).date() < today]
            if len(completed) < 2:
                return None

            prev_close = float(completed[-1].close)
            avg_volume = sum(b.volume for b in completed) / len(completed)

            # Latest TRADE for the current price (quotes on the free feed can be one-sided,
            # e.g. ask = $0, which made the old bid/ask average useless)
            trade_request = StockLatestTradeRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
            trade = self.alpaca_client.get_stock_latest_trade(trade_request).get(symbol)
            if trade is None or not trade.price or trade.timestamp.astimezone(ET).date() != today:
                return None     # no trades yet today
            current_price = float(trade.price)
            
            # Calculate gap
            gap_pct = ((current_price - prev_close) / prev_close) * 100
            
            return {
                'symbol': symbol,
                'prev_close': round(prev_close, 2),
                'current_price': round(current_price, 2),
                'gap_pct': round(gap_pct, 2),
                'volume': 0,  # Pre-market volume requires subscription
                'avg_volume': int(avg_volume),
                'relative_volume': 0
            }
            
        except Exception as e:
            return None
    
    def check_news(self, symbol: str) -> Dict:
        """
        Check for recent news catalyst.
        
        Returns:
            {
                'has_news': True/False,
                'headline': 'Latest headline...',
                'catalyst_type': 'earnings' | 'pr' | 'analyst' | 'sector' | 'unknown'
            }
        
        NOTE: For full news integration, you'd use:
        - Alpaca News API (free with account)
        - Finnhub API (free tier)
        - Benzinga (paid, best quality)
        
        For now, we'll do a simple Yahoo check.
        """
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news
            
            if not news or len(news) == 0:
                return {'has_news': False, 'headline': '', 'catalyst_type': 'none'}
            
            # Get most recent news
            latest = news[0]
            headline = latest.get('title', '')
            
            # Check news age (within 24 hours)
            publish_time = latest.get('providerPublishTime', 0)
            news_age = datetime.now().timestamp() - publish_time
            
            if news_age > 86400:  # 24 hours
                return {'has_news': False, 'headline': '', 'catalyst_type': 'none'}
            
            # Classify catalyst type
            headline_lower = headline.lower()
            if any(w in headline_lower for w in ['earnings', 'revenue', 'profit', 'eps', 'quarter']):
                catalyst_type = 'earnings'
            elif any(w in headline_lower for w in ['fda', 'approval', 'trial', 'drug']):
                catalyst_type = 'fda'
            elif any(w in headline_lower for w in ['upgrade', 'downgrade', 'price target', 'analyst']):
                catalyst_type = 'analyst'
            elif any(w in headline_lower for w in ['contract', 'deal', 'partnership', 'acquisition']):
                catalyst_type = 'pr'
            else:
                catalyst_type = 'unknown'
            
            return {
                'has_news': True,
                'headline': headline[:100],  # Truncate
                'catalyst_type': catalyst_type
            }
            
        except Exception as e:
            # If news check fails, still allow trade (manual check)
            return {'has_news': True, 'headline': 'CHECK MANUALLY', 'catalyst_type': 'unknown'}
    
    def calculate_score(self, stock: Dict) -> int:
        """
        Calculate quality score for ranking (0-100).
        Higher = better setup.
        """
        score = 0
        
        # Gap size (max 30 points)
        gap = abs(stock['gap_pct'])
        if gap >= 10:
            score += 30
        elif gap >= 7:
            score += 25
        elif gap >= 5:
            score += 20
        elif gap >= 3:
            score += 15
        
        # Relative volume (max 25 points)
        rvol = stock.get('relative_volume', 0)
        if rvol >= 5:
            score += 25
        elif rvol >= 3:
            score += 20
        elif rvol >= 2:
            score += 15
        elif rvol >= 1.5:
            score += 10
        
        # Catalyst type (max 25 points)
        catalyst = stock.get('catalyst_type', 'unknown')
        if catalyst == 'earnings':
            score += 25
        elif catalyst == 'fda':
            score += 25
        elif catalyst == 'pr':
            score += 20
        elif catalyst == 'analyst':
            score += 15
        else:
            score += 5
        
        # Price sweet spot $20-100 (max 10 points)
        price = stock.get('current_price', 0)
        if 20 <= price <= 100:
            score += 10
        elif 10 <= price <= 150:
            score += 5
        
        # Volume (max 10 points)
        avg_vol = stock.get('avg_volume', 0)
        if avg_vol >= 5000000:
            score += 10
        elif avg_vol >= 2000000:
            score += 7
        elif avg_vol >= 1000000:
            score += 5
        
        return min(score, 100)
    
    def scan(self, require_news: bool = False) -> List[Dict]:
        """
        Run the pre-market scan.
        
        Args:
            require_news: If True, skip stocks without recent news
            
        Returns:
            List of qualifying stocks, sorted by score
        """
        results = []
        universe = self.get_universe()
        
        print(f"\n{'='*60}")
        print(f"🔍 PRE-MARKET SCANNER")
        print(f"{'='*60}")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 Scanning {len(universe)} stocks...")
        print(f"🎯 Filters: Gap ≥{self.min_gap_pct}%, Price ${self.min_price}-${self.max_price}")
        print(f"{'='*60}\n")
        
        for i, symbol in enumerate(universe):
            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"   Progress: {i+1}/{len(universe)}...")
            
            try:
                # Get stock data
                if self.use_alpaca:
                    data = self.get_stock_data_alpaca(symbol)
                else:
                    data = self.get_stock_data_yahoo(symbol)
                
                if data is None:
                    continue
                
                # === APPLY FILTERS ===
                
                # Filter 1: Gap percentage, up (long setups) or down (short setups)
                if abs(data['gap_pct']) < self.min_gap_pct:
                    continue
                
                # Filter 2: Price range
                if data['current_price'] < self.min_price or data['current_price'] > self.max_price:
                    continue
                
                # Filter 3: Average volume (liquidity)
                if data['avg_volume'] < self.min_avg_daily_volume:
                    continue
                
                # Filter 4: Check news
                news = self.check_news(symbol)
                data['has_news'] = news['has_news']
                data['headline'] = news['headline']
                data['catalyst_type'] = news['catalyst_type']
                
                if require_news and not news['has_news']:
                    continue
                
                # Calculate score
                data['score'] = self.calculate_score(data)
                data['scan_type'] = 'premarket'
                data['scan_time'] = datetime.now().isoformat()
                
                # Add to results
                results.append(data)
                print(f"   ✅ {symbol}: {data['gap_pct']:+.1f}% @ ${data['current_price']:.2f} (Score: {data['score']})")
                
            except Exception as e:
                continue
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"\n{'='*60}")
        print(f"✅ FOUND {len(results)} GAPPERS")
        print(f"{'='*60}")
        
        return results


# ==============================================================================
# MAIN FUNCTION
# ==============================================================================
def run_premarket_scan(require_news: bool = False, save: bool = True) -> List[Dict]:
    """
    Main function to run pre-market scan.
    
    Args:
        require_news: Skip stocks without recent news
        save: Save results to JSON file
        
    Returns:
        List of qualifying stocks
    """
    # Create scanner
    scanner = PreMarketScanner()
    
    # Run scan
    results = scanner.scan(require_news=require_news)
    
    # Print top results
    if results:
        print(f"\n📈 TOP GAPPERS:")
        for i, stock in enumerate(results[:10], 1):
            catalyst = stock.get('catalyst_type', '?')
            print(f"   {i}. {stock['symbol']:6} | {stock['gap_pct']:+6.1f}% | "
                  f"${stock['current_price']:7.2f} | Score: {stock['score']} | {catalyst}")

    # Save to file, even when nothing was found: an old file must never stand in for today
    if save:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output = {
            'scan_time': datetime.now().isoformat(),
            'scan_type': 'premarket',
            'filters': {
                'min_gap_pct': MIN_GAP_PCT,
                'min_price': MIN_PRICE,
                'max_price': MAX_PRICE,
                'min_avg_volume': MIN_AVG_DAILY_VOLUME
            },
            'count': len(results),
            'stocks': results
        }
        
        output_file = os.path.join(OUTPUT_DIR, 'watchlist_premarket.json')
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n💾 Saved to {output_file}")
    
    return results


# ==============================================================================
# RUN
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "🚀"*30)
    print("\n  PRE-MARKET GAP SCANNER")
    print("\n" + "🚀"*30)
    
    # Run scan
    gappers = run_premarket_scan(require_news=False)
    
    if gappers:
        print(f"\n✅ Found {len(gappers)} gapping stocks!")
        print("\n📋 Top 5 for today:")
        for stock in gappers[:5]:
            print(f"   • {stock['symbol']}: {stock['gap_pct']:+.1f}% (Score: {stock['score']})")
    else:
        print("\n⚠️  No gappers found matching criteria")
    
    print("\n✅ Scan complete!")
