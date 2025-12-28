"""
watchlist_reader.py - Load Watchlist for Day Trading Bot
========================================================
Provides simple functions to load scanner output into 
your FPB or ORB trading strategies.

Usage:
    from watchlist_reader import load_watchlist, load_watchlist_with_context
    
    # Simple: just get symbols
    symbols = load_watchlist()
    
    # Full: get all context (gap %, patterns, scores)
    stocks = load_watchlist_with_context()
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


def load_watchlist(filepath: str = "output/watchlist.json") -> List[str]:
    """
    Load today's watchlist symbols.
    
    Args:
        filepath: Path to watchlist JSON
        
    Returns:
        List of ticker symbols
        
    Example:
        symbols = load_watchlist()
        for symbol in symbols:
            run_fpb_strategy(symbol)
    """
    path = Path(filepath)
    
    if not path.exists():
        print(f"⚠️  Watchlist not found: {filepath}")
        print("   Using fallback symbols...")
        return get_fallback_symbols()
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        
        symbols = [stock['symbol'] for stock in data.get('stocks', [])]
        
        print(f"📋 Loaded {len(symbols)} stocks from watchlist")
        if symbols:
            print(f"   Symbols: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")
        
        return symbols
        
    except Exception as e:
        print(f"❌ Error loading watchlist: {e}")
        return get_fallback_symbols()


def load_watchlist_with_context(filepath: str = "output/watchlist.json") -> List[Dict]:
    """
    Load watchlist with full context for smarter trading.
    
    Returns list of dicts with:
    - symbol
    - source: 'both' | 'premarket' | 'eod'
    - has_gap: bool
    - gap_pct: float (if gap)
    - has_pattern: bool
    - patterns: list (if patterns)
    - score: int
    - catalyst_type: str (if news)
    
    Example:
        stocks = load_watchlist_with_context()
        
        for stock in stocks:
            # Prioritize gap + pattern stocks
            if stock['source'] == 'both':
                run_aggressive_strategy(stock['symbol'])
            else:
                run_normal_strategy(stock['symbol'])
    """
    path = Path(filepath)
    
    if not path.exists():
        print(f"⚠️  Watchlist not found: {filepath}")
        return []
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        
        stocks = data.get('stocks', [])
        print(f"📋 Loaded {len(stocks)} stocks with full context")
        
        return stocks
        
    except Exception as e:
        print(f"❌ Error loading watchlist: {e}")
        return []


def get_gap_stocks(min_gap: float = 3.0) -> List[Dict]:
    """
    Get only gap-up stocks from watchlist.
    
    Args:
        min_gap: Minimum gap percentage
        
    Returns:
        List of stocks that gapped up
    """
    stocks = load_watchlist_with_context()
    
    gappers = [
        s for s in stocks 
        if s.get('has_gap', False) and s.get('gap_pct', 0) >= min_gap
    ]
    
    print(f"📈 Found {len(gappers)} gap-up stocks (≥{min_gap}%)")
    return gappers


def get_pattern_stocks() -> List[Dict]:
    """
    Get stocks with daily chart patterns.
    
    Returns:
        List of stocks with technical patterns
    """
    stocks = load_watchlist_with_context()
    
    pattern_stocks = [
        s for s in stocks 
        if s.get('has_pattern', False)
    ]
    
    print(f"📊 Found {len(pattern_stocks)} stocks with patterns")
    return pattern_stocks


def get_top_stocks(n: int = 5) -> List[str]:
    """
    Get top N stocks by score.
    
    Args:
        n: Number of stocks to return
        
    Returns:
        List of top ticker symbols
    """
    stocks = load_watchlist_with_context()
    
    # Sort by score
    sorted_stocks = sorted(stocks, key=lambda x: x.get('score', 0), reverse=True)
    
    top = [s['symbol'] for s in sorted_stocks[:n]]
    print(f"🏆 Top {n} stocks: {', '.join(top)}")
    
    return top


def get_fallback_symbols() -> List[str]:
    """
    Fallback symbols when no watchlist available.
    These are historically volatile momentum stocks.
    """
    fallback = [
        "NVDA", "AMD", "TSLA", "COIN", "MSTR",
        "PLTR", "SOUN", "IONQ", "RKLB", "BBAI"
    ]
    print(f"   Fallback: {', '.join(fallback)}")
    return fallback


def print_watchlist_summary(filepath: str = "output/watchlist.json"):
    """Pretty print watchlist summary"""
    stocks = load_watchlist_with_context(filepath)
    
    if not stocks:
        print("❌ No stocks in watchlist")
        return
    
    print(f"\n{'='*60}")
    print(f"📋 TODAY'S TRADING WATCHLIST")
    print(f"{'='*60}")
    
    # Group by source
    both = [s for s in stocks if s.get('source') == 'both']
    gap_only = [s for s in stocks if s.get('source') == 'premarket']
    pattern_only = [s for s in stocks if s.get('source') == 'eod']
    
    if both:
        print(f"\n⭐ A+ SETUPS (Gap + Pattern): {len(both)}")
        for s in both[:5]:
            gap = s.get('gap_pct', 0)
            patterns = s.get('pattern_names', [])
            print(f"   {s['symbol']:6} | +{gap:.1f}% | {patterns}")
    
    if gap_only:
        print(f"\n📈 GAP STOCKS: {len(gap_only)}")
        for s in gap_only[:5]:
            gap = s.get('gap_pct', 0)
            catalyst = s.get('catalyst_type', 'news')
            print(f"   {s['symbol']:6} | +{gap:.1f}% | {catalyst}")
    
    if pattern_only:
        print(f"\n📊 PATTERN STOCKS: {len(pattern_only)}")
        for s in pattern_only[:5]:
            patterns = s.get('pattern_names', [])
            print(f"   {s['symbol']:6} | {patterns}")
    
    print(f"\n{'='*60}\n")


# ==============================================================================
# INTEGRATION EXAMPLE
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "📋"*30)
    print("\n  WATCHLIST READER")
    print("\n" + "📋"*30)
    
    # Show what's available
    print_watchlist_summary()
    
    # Example: Load for FPB trading
    print("\n🎯 Example: Loading for FPB Strategy")
    symbols = load_watchlist()
    print(f"   Ready to trade: {len(symbols)} stocks")
    
    # Example: Get only best setups
    print("\n🏆 Example: Top 5 stocks")
    top = get_top_stocks(5)
    
    # Example: Get gap stocks for ORB
    print("\n📈 Example: Gap stocks for ORB")
    gappers = get_gap_stocks(min_gap=3.0)
    for g in gappers[:3]:
        print(f"   {g['symbol']}: +{g.get('gap_pct', 0):.1f}%")
    
    print("\n✅ Reader ready!")
