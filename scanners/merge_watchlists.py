"""
merge_watchlists.py - Combine Pre-Market and EOD Watchlists
============================================================
Merges scanner outputs into final watchlist for day trading bot.

Run: 9:25 AM (right before market open)
Output: watchlist.json (read by FPB/ORB bot)

PRIORITY ORDER:
1. Pre-market gappers WITH daily patterns (best!)
2. Pre-market gappers (gap + catalyst)
3. Daily setups (technical patterns)

Per bootcamp: "Stocks with BOTH gap and hot daily are A+ setups"
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional

# The project's output/ folder (one level up from scanners/), so merges work from any folder
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')


def load_json(filepath: str) -> Optional[Dict]:
    """Load JSON file if exists"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  Not found: {filepath}")
        return None
    except Exception as e:
        print(f"❌ Error loading {filepath}: {e}")
        return None


def scan_age_days(data: Dict) -> Optional[int]:
    """How many calendar days old a scan file is (None if it has no scan time)."""
    try:
        return (datetime.now().date() - datetime.fromisoformat(data['scan_time']).date()).days
    except (KeyError, TypeError, ValueError):
        return None


MAX_EOD_AGE_DAYS = 4    # Friday's after-close scan is still good on Monday (and after a long weekend)


def merge_watchlists(
    premarket_file: str = os.path.join(OUTPUT_DIR, "watchlist_premarket.json"),
    eod_file: str = os.path.join(OUTPUT_DIR, "watchlist_eod.json"),
    output_file: str = os.path.join(OUTPUT_DIR, "watchlist.json"),
    max_stocks: int = 20
) -> List[Dict]:
    """
    Merge pre-market and EOD watchlists into final watchlist.
    
    Priority:
    1. Stocks on BOTH lists get score boost (gap + pattern = best)
    2. Pre-market gappers (have catalyst)
    3. EOD setups (technical only)
    
    Returns:
        Final merged watchlist
    """
    
    print(f"\n{'='*60}")
    print(f"📋 MERGING WATCHLISTS")
    print(f"{'='*60}")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    final_stocks = {}  # Use dict for deduplication
    
    # Load pre-market results: only today's scan counts (an old gap is not today's gap)
    premarket_data = load_json(premarket_file)
    if premarket_data and scan_age_days(premarket_data) != 0:
        print(f"⚠️  Pre-market scan is from {premarket_data.get('scan_time', '?')[:10]}, not today. Ignoring it.")
        premarket_data = None
    if premarket_data:
        premarket_stocks = premarket_data.get('stocks', [])
        print(f"📈 Pre-market gappers: {len(premarket_stocks)}")
        
        for stock in premarket_stocks:
            symbol = stock['symbol']
            stock['source'] = 'premarket'
            stock['has_gap'] = True
            stock['has_pattern'] = False
            final_stocks[symbol] = stock
    else:
        premarket_stocks = []
        print("📈 Pre-market gappers: 0 (no file)")
    
    # Load EOD results: daily-chart patterns from the last few days
    eod_data = load_json(eod_file)
    age = scan_age_days(eod_data) if eod_data else None
    if eod_data and (age is None or age > MAX_EOD_AGE_DAYS):
        print(f"⚠️  End-of-day scan is from {eod_data.get('scan_time', '?')[:10]}, too old. Ignoring it.")
        eod_data = None
    if eod_data:
        eod_stocks = eod_data.get('stocks', [])
        print(f"📊 EOD setups: {len(eod_stocks)}")
        
        for stock in eod_stocks:
            symbol = stock['symbol']
            
            if symbol in final_stocks:
                # Stock has BOTH gap AND pattern - BEST!
                existing = final_stocks[symbol]
                existing['has_pattern'] = True
                existing['patterns'] = stock.get('patterns', [])
                existing['pattern_names'] = stock.get('pattern_names', [])
                existing['score'] = existing.get('score', 50) + 30  # Big bonus!
                existing['source'] = 'both'  # Both sources
                print(f"   ⭐ {symbol}: Gap + Pattern (boosted!)")
            else:
                # EOD only
                stock['source'] = 'eod'
                stock['has_gap'] = False
                stock['has_pattern'] = True
                final_stocks[symbol] = stock
    else:
        print("📊 EOD setups: 0 (no file)")
    
    # Convert to list
    stocks_list = list(final_stocks.values())
    
    # Sort by: source priority (both > premarket > eod), then score
    def sort_key(stock):
        source_priority = {'both': 3, 'premarket': 2, 'eod': 1}
        return (source_priority.get(stock['source'], 0), stock.get('score', 0))
    
    stocks_list.sort(key=sort_key, reverse=True)
    
    # Limit to max stocks
    stocks_list = stocks_list[:max_stocks]
    
    # Print final list
    print(f"\n{'='*60}")
    print(f"✅ FINAL WATCHLIST: {len(stocks_list)} stocks")
    print(f"{'='*60}\n")
    
    for i, stock in enumerate(stocks_list, 1):
        symbol = stock['symbol']
        source = stock['source'].upper()
        score = stock.get('score', 0)
        
        # Format based on source
        if source == 'BOTH':
            gap = stock.get('gap_pct', 0)
            patterns = stock.get('pattern_names', [])
            print(f"   {i}. ⭐ {symbol:6} | {source:10} | {gap:+.1f}% | {patterns} | Score: {score}")
        elif source == 'PREMARKET':
            gap = stock.get('gap_pct', 0)
            catalyst = stock.get('catalyst_type', 'unknown')
            print(f"   {i}. 📈 {symbol:6} | {source:10} | {gap:+.1f}% | {catalyst} | Score: {score}")
        else:
            patterns = stock.get('pattern_names', [])
            print(f"   {i}. 📊 {symbol:6} | {source:10} | {patterns} | Score: {score}")
    
    # Summary counts
    both_count = len([s for s in stocks_list if s['source'] == 'both'])
    pm_count = len([s for s in stocks_list if s['source'] == 'premarket'])
    eod_count = len([s for s in stocks_list if s['source'] == 'eod'])
    
    print(f"\n📋 Breakdown:")
    print(f"   ⭐ Gap + Pattern (best): {both_count}")
    print(f"   📈 Gap only: {pm_count}")
    print(f"   📊 Pattern only: {eod_count}")
    
    # Save final watchlist
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    output = {
        'last_updated': datetime.now().isoformat(),
        'premarket_file': os.path.basename(premarket_file) if premarket_data else None,
        'eod_file': os.path.basename(eod_file) if eod_data else None,
        'count': len(stocks_list),
        'breakdown': {
            'gap_and_pattern': both_count,
            'gap_only': pm_count,
            'pattern_only': eod_count
        },
        'stocks': stocks_list
    }
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Saved to {output_file}")
    
    # Also save simple text list
    symbols = [s['symbol'] for s in stocks_list]
    txt_file = os.path.join(os.path.dirname(os.path.abspath(output_file)), 'watchlist.txt')
    with open(txt_file, 'w') as f:
        f.write('\n'.join(symbols))

    print(f"💾 Symbols saved to {txt_file}")
    
    print(f"\n{'='*60}\n")
    
    return stocks_list


def get_symbols_only(watchlist_file: str = os.path.join(OUTPUT_DIR, "watchlist.json")) -> List[str]:
    """
    Get just the symbols from watchlist (for FPB/ORB bot).
    
    Usage:
        from merge_watchlists import get_symbols_only
        symbols = get_symbols_only()
        # Now run FPB strategy on these symbols
    """
    data = load_json(watchlist_file)
    if not data:
        # Fallback to hardcoded
        return ["NVDA", "AMD", "TSLA", "COIN", "MSTR"]
    
    return [stock['symbol'] for stock in data.get('stocks', [])]


def print_watchlist(watchlist_file: str = os.path.join(OUTPUT_DIR, "watchlist.json")):
    """Pretty print the current watchlist"""
    data = load_json(watchlist_file)
    if not data:
        print("❌ No watchlist found")
        return
    
    print(f"\n📋 TODAY'S WATCHLIST ({data.get('count', 0)} stocks)")
    print(f"   Updated: {data.get('last_updated', 'unknown')}")
    print("-" * 50)
    
    for i, stock in enumerate(data.get('stocks', []), 1):
        symbol = stock['symbol']
        source = stock.get('source', '?')
        score = stock.get('score', 0)
        
        if source == 'both':
            emoji = "⭐"
        elif source == 'premarket':
            emoji = "📈"
        else:
            emoji = "📊"
        
        print(f"   {i}. {emoji} {symbol:6} | Score: {score}")


# ==============================================================================
# RUN
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "📋"*30)
    print("\n  WATCHLIST MERGER")
    print("\n" + "📋"*30)
    
    # Merge watchlists
    final = merge_watchlists()
    
    if final:
        print(f"✅ Final watchlist ready with {len(final)} stocks!")
        print("\n🎯 Top 5 for trading:")
        for stock in final[:5]:
            print(f"   • {stock['symbol']} ({stock['source']})")
    else:
        print("⚠️  No stocks in watchlist")
    
    print("\n✅ Merge complete!")
