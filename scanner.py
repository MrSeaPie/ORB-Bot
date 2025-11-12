# ============================================================================
# GAP SCANNER - FIXED FOR YFINANCE COMPATIBILITY
# ============================================================================

import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import List, Dict
import time
import warnings
warnings.filterwarnings('ignore')  # Hide warnings

# ============================================================================
# SIMPLE GAP CHECKER
# ============================================================================

def check_single_stock(symbol: str) -> Dict:
    """Check if ONE stock gapped up"""
    try:
        # Download - FIXED PARAMETERS
        df = yf.download(
            symbol, 
            period="5d", 
            interval="1d",
            progress=False,
            auto_adjust=True
            # Removed show_errors - doesn't exist in all versions
        )
        
        # Check if we got data
        if df is None or len(df) < 2:
            return None
        
        # Handle MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Lowercase column names
        df.columns = [c.lower() for c in df.columns]
        
        # Check we have what we need
        if 'close' not in df.columns or 'open' not in df.columns:
            return None
        
        # Get the data
        prev_close = float(df['close'].iloc[-2])
        today_open = float(df['open'].iloc[-1])
        gap_pct = ((today_open - prev_close) / prev_close) * 100
        
        # Volume
        if 'volume' in df.columns:
            today_volume = float(df['volume'].iloc[-1])
            lookback = min(20, len(df))
            avg_volume = float(df['volume'].tail(lookback).mean())
        else:
            today_volume = 0
            avg_volume = 0
        
        return {
            'symbol': symbol,
            'prev_close': prev_close,
            'today_open': today_open,
            'gap_pct': gap_pct,
            'price': today_open,
            'today_volume': today_volume,
            'avg_volume': avg_volume,
        }
        
    except Exception as e:
        # Silently skip errors
        return None


# ============================================================================
# MAIN SCANNER
# ============================================================================

def scan_for_gappers(
    min_gap_pct=3.0,
    min_price=20.0,
    max_price=200.0,
    min_avg_volume=3000000,
    max_results=20
) -> List[Dict]:
    """Scan stocks for gaps"""
    
    print("\n" + "="*70)
    print("🔍 GAP SCANNER")
    print("="*70)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Gap ≥{min_gap_pct}%, Price ${min_price}-${max_price}, Vol ≥{min_avg_volume/1e6:.0f}M")
    print("="*70 + "\n")
    
    # Stock universe
    universe = [
        "BBAI", "SOUN", "UPST", "PATH",
        "WKHS", "RIDE", "PLUG", "GEVO",
        "RIOT", "MARA", "COIN", "MSTR",
        "RKLB", "SPCE",
        "ATOS", "OCGN", "SNDL",
        "SOFI", "AFRM",
        "TFM", "TSSI", "RDW", "RKBF",
    ]
    
    print(f"📊 Scanning {len(universe)} stocks...")
    print(f"⏱️  Takes ~1 minute...\n")
    
    gappers = []
    checked = 0
    
    for i, symbol in enumerate(universe):
        if (i + 1) % 5 == 0:
            print(f"   Progress: {i+1}/{len(universe)}...")
        
        info = check_single_stock(symbol)
        
        if info is None:
            time.sleep(0.3)
            continue
        
        checked += 1
        
        # Apply filters
        passes = (
            abs(info['gap_pct']) >= min_gap_pct and
            min_price <= info['price'] <= max_price and
            (info['avg_volume'] == 0 or info['avg_volume'] >= min_avg_volume)
        )
        
        if passes:
            gappers.append(info)
            print(f"   ✅ {symbol}: {info['gap_pct']:+.1f}% @ ${info['price']:.2f}")
        
        time.sleep(0.3)
    
    print(f"\n   Checked: {checked}/{len(universe)} stocks")
    
    gappers = sorted(gappers, key=lambda x: abs(x['gap_pct']), reverse=True)
    gappers = gappers[:max_results]
    
    print(f"\n{'='*70}")
    print(f"✅ FOUND {len(gappers)} GAPPERS!")
    print("="*70)
    
    if len(gappers) > 0:
        print("\n📈 TOP GAPPERS:")
        for i, g in enumerate(gappers, 1):
            vol = f"{g['avg_volume']/1e6:.1f}M" if g['avg_volume'] > 0 else "N/A"
            print(f"   {i}. {g['symbol']:>6} | {g['gap_pct']:+5.1f}% | ${g['price']:>6.2f} | {vol}")
    
    print("\n" + "="*70 + "\n")
    
    return gappers


def find_daily_gappers() -> List[str]:
    """Main function - returns ticker symbols"""
    try:
        gappers = scan_for_gappers()
        
        if len(gappers) > 0:
            symbols = [g['symbol'] for g in gappers]
            print(f"✅ Scanner found {len(symbols)} gappers\n")
            return symbols
        else:
            print("⚠️  No gappers found, using backup list\n")
            return get_historical_gappers()
    except:
        print("⚠️  Scanner error, using backup list\n")
        return get_historical_gappers()


def get_historical_gappers() -> List[str]:
    """Backup list"""
    return [
        "BBAI", "SOUN", "TFM", "TSSI", 
        "RDW", "RKBF", "SCUN", "RKLB",
        "WKHS", "RIDE", "SPCE", "PLUG",
        "RIOT", "MARA", "COIN",
        "ATOS", "OCGN", "GEVO",
    ]


if __name__ == "__main__":
    print("\n🧪 TESTING SCANNER\n")
    symbols = find_daily_gappers()
    print(f"\n✅ Returned {len(symbols)} stocks: {symbols}\n")