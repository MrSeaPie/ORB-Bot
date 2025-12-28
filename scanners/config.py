"""
config.py - Central Configuration for Scanner Bot
==================================================
All settings in one place for easy tuning.
"""

import os

# ==============================================================================
# API CREDENTIALS
# ==============================================================================
# Set these as environment variables or hardcode for testing

ALPACA_API_KEY = os.getenv('ALPACA_API_KEY', 'YOUR_API_KEY_HERE')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY', 'YOUR_SECRET_KEY_HERE')

# Paper trading (safe for testing)
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"

# Live trading (use when ready)
# ALPACA_BASE_URL = "https://api.alpaca.markets"


# ==============================================================================
# SCANNER SCHEDULE (Eastern Time)
# ==============================================================================
PREMARKET_SCAN_START = "06:00"      # Start scanning pre-market
PREMARKET_SCAN_END = "09:25"        # Stop 5 min before open
EOD_SCAN_TIME = "16:15"             # After market close


# ==============================================================================
# PRE-MARKET SCANNER FILTERS
# ==============================================================================
# These match your bootcamp criteria exactly

MIN_GAP_PCT = 3.0           # Minimum gap % (bootcamp: 3%+)
MIN_PRICE = 5.0             # Minimum stock price
MAX_PRICE = 500.0           # Maximum stock price
MIN_PREMARKET_VOLUME = 100000   # Min pre-market shares traded
MIN_RELATIVE_VOLUME = 2.0   # Today's vol / avg vol
MIN_AVG_DAILY_VOLUME = 500000   # Liquidity filter
MAX_FLOAT_SHARES = 500000000    # 500M max float (optional)


# ==============================================================================
# END-OF-DAY SCANNER FILTERS
# ==============================================================================
# Daily chart pattern detection

FLAT_TOP_TOUCHES = 3        # Min touches for flat top pattern
FLAT_TOP_ZONE_PCT = 2.0     # % zone for resistance touches
BULL_FLAG_MIN_POLE = 10.0   # Min % move for pole
BULL_FLAG_MAX_RETRACE = 50.0    # Max % flag can retrace
PULLBACK_EMA_BUFFER = 2.0   # % buffer for EMA touch


# ==============================================================================
# WATCHLIST SETTINGS
# ==============================================================================
MAX_WATCHLIST_SIZE = 20     # Max stocks on final watchlist
OUTPUT_DIR = "output"       # Where to save watchlist files


# ==============================================================================
# TRADING STRATEGY SETTINGS (for reference by FPB/ORB bots)
# ==============================================================================
RISK_PER_TRADE = 250.0      # $ risk per trade
MAX_POSITIONS = 5           # Max concurrent positions
TARGET_R1 = 1.5             # First target (sell half)
TARGET_R2 = 3.0             # Runner target


# ==============================================================================
# NEWS SETTINGS
# ==============================================================================
# Options: "alpaca", "finnhub", "yahoo", "skip"
NEWS_SOURCE = "alpaca"      # Which news API to use
NEWS_LOOKBACK_HOURS = 24    # How far back to check for news


# ==============================================================================
# STOCK UNIVERSE
# ==============================================================================
# These are stocks the scanner will check each day
# Update weekly with top momentum names

DEFAULT_UNIVERSE = [
    # Mega caps (always liquid, sometimes gap)
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    
    # High-beta tech
    "AMD", "COIN", "MSTR", "PLTR", "SOUN", "IONQ", "RKLB",
    "SMCI", "ARM", "MARA", "RIOT", "HOOD", "SOFI", "AFRM",
    
    # Popular momentum / small caps
    "BBAI", "UPST", "PATH", "WKHS", "RIDE", "PLUG", "GEVO",
    "SPCE", "ATOS", "OCGN", "SNDL", "LCID", "RIVN", "NIO",
    
    # Recent gappers (update this list!)
    "RDDT", "SMMT", "DRUG", "HOLO", "MVST", "QS", "JOBY",
]


print("✅ Config loaded!")
print(f"   Gap filter: ≥{MIN_GAP_PCT}%")
print(f"   Price range: ${MIN_PRICE}-${MAX_PRICE}")
print(f"   Min volume: {MIN_AVG_DAILY_VOLUME/1e6:.1f}M avg daily")
