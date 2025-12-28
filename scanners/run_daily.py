"""
run_daily.py - Master Daily Automation Script
==============================================
Runs scanners and trading bot on schedule.

SCHEDULE (Eastern Time):
- 6:00 AM: Pre-market scan (first pass)
- 9:00 AM: Pre-market scan (update)  
- 9:25 AM: Merge watchlists
- 9:30 AM: Day trade bot starts
- 4:15 PM: EOD scan (for tomorrow)

Run this script in the morning and leave it running all day.
Or use Windows Task Scheduler / cron to run individual scripts.

Usage:
    python run_daily.py           # Run scheduler
    python run_daily.py --now     # Run all scans now (testing)
    python run_daily.py --premarket  # Run just pre-market scan
    python run_daily.py --eod     # Run just EOD scan
    python run_daily.py --merge   # Run just merge
"""

import sys
import os
import subprocess
from datetime import datetime
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import schedule (optional)
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False
    print("⚠️  'schedule' not installed. Install with: pip install schedule")
    print("   Running without scheduler (manual mode).\n")


# ==============================================================================
# SCANNER FUNCTIONS
# ==============================================================================

def run_premarket_scan():
    """Run pre-market scanner"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 Running pre-market scan...")
    try:
        from premarket_scanner import run_premarket_scan
        results = run_premarket_scan(require_news=False, save=True)
        print(f"   Found {len(results)} gappers")
        return results
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return []


def run_eod_scan():
    """Run end-of-day scanner"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📊 Running EOD scan...")
    try:
        from eod_scanner import run_eod_scan
        results = run_eod_scan(save=True)
        print(f"   Found {len(results)} setups")
        return results
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return []


def run_merge():
    """Merge watchlists"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📋 Merging watchlists...")
    try:
        from merge_watchlists import merge_watchlists
        results = merge_watchlists()
        print(f"   Final watchlist: {len(results)} stocks")
        return results
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return []


def run_day_trade_bot():
    """Run day trading bot (FPB strategy)"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🎯 Starting day trade bot...")
    try:
        # Option 1: Run as subprocess
        # subprocess.run(["python", "fpb_strategy.py"])
        
        # Option 2: Import and run
        # from fpb_strategy import FirstPullbackBuy
        # strategy = FirstPullbackBuy()
        # ...
        
        print("   (Day trading bot would start here)")
        print("   NOTE: Integrate with your existing FPB/ORB code")
    except Exception as e:
        print(f"   ❌ Error: {e}")


# ==============================================================================
# ALL-IN-ONE SCAN
# ==============================================================================

def run_all_scans():
    """Run all scans (for testing or manual run)"""
    print("\n" + "="*60)
    print("🚀 RUNNING ALL SCANS")
    print("="*60)
    
    # Pre-market
    run_premarket_scan()
    
    # EOD
    run_eod_scan()
    
    # Merge
    run_merge()
    
    # Print final watchlist
    try:
        from watchlist_reader import print_watchlist_summary
        print_watchlist_summary()
    except:
        pass
    
    print("\n✅ All scans complete!")


# ==============================================================================
# SCHEDULER
# ==============================================================================

def start_scheduler():
    """Start the daily scheduler"""
    
    if not SCHEDULE_AVAILABLE:
        print("❌ Cannot run scheduler without 'schedule' package")
        print("   Install: pip install schedule")
        print("   Or run scans manually with: python run_daily.py --now")
        return
    
    print("\n" + "="*60)
    print("📅 SCANNER SCHEDULER STARTED")
    print("="*60)
    print(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nSchedule (Eastern Time):")
    print("  06:00 - Pre-market scan")
    print("  09:00 - Pre-market scan (update)")
    print("  09:25 - Merge watchlists")
    print("  09:30 - Day trade bot")
    print("  16:15 - EOD scan")
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")
    
    # Schedule tasks
    schedule.every().day.at("06:00").do(run_premarket_scan)
    schedule.every().day.at("09:00").do(run_premarket_scan)
    schedule.every().day.at("09:25").do(run_merge)
    schedule.every().day.at("09:30").do(run_day_trade_bot)
    schedule.every().day.at("16:15").do(run_eod_scan)
    
    # Also run every hour for testing (comment out in production)
    # schedule.every().hour.do(run_premarket_scan)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        print("\n\n⏹️  Scheduler stopped")


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "🚀"*30)
    print("\n  SCANNER BOT - DAILY AUTOMATION")
    print("\n" + "🚀"*30)
    
    # Parse arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        
        if arg in ['--now', '-n', 'now', 'all']:
            # Run all scans now
            run_all_scans()
            
        elif arg in ['--premarket', '-p', 'premarket', 'pm']:
            # Run just pre-market
            run_premarket_scan()
            
        elif arg in ['--eod', '-e', 'eod']:
            # Run just EOD
            run_eod_scan()
            
        elif arg in ['--merge', '-m', 'merge']:
            # Run just merge
            run_merge()
            
        elif arg in ['--help', '-h', 'help']:
            print("\nUsage:")
            print("  python run_daily.py          # Start scheduler")
            print("  python run_daily.py --now    # Run all scans now")
            print("  python run_daily.py --premarket  # Pre-market scan")
            print("  python run_daily.py --eod    # EOD scan")
            print("  python run_daily.py --merge  # Merge watchlists")
            
        else:
            print(f"Unknown argument: {arg}")
            print("Use --help for usage")
    else:
        # No arguments - start scheduler or run all
        if SCHEDULE_AVAILABLE:
            start_scheduler()
        else:
            print("Running all scans now (no scheduler available)...\n")
            run_all_scans()
