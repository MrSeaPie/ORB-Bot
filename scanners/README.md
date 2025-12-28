# 📈 Scanner Bot for Bulls Bootcamp Day Trading

Automated stock scanner that finds gap-up stocks and daily chart patterns for your FPB/ORB strategies.

## 🎯 What It Does

1. **Pre-Market Scanner** (6:00-9:25 AM): Finds stocks gapping up 3%+ with news
2. **EOD Scanner** (After 4 PM): Finds daily chart patterns for next day
3. **Watchlist Merger**: Combines both scans into final trading list
4. **Connects to your FPB/ORB bot** to trade only the best setups

## ⚡ Quick Start

### Step 1: Install Dependencies
```bash
cd C:\Users\Hassan\ORB-Bot\scanners
pip install -r requirements.txt
```

### Step 2: Set Up API Keys (Optional but Recommended)
```bash
# Windows PowerShell
$env:ALPACA_API_KEY = "your_api_key"
$env:ALPACA_SECRET_KEY = "your_secret_key"

# Or edit config.py directly
```

### Step 3: Run Scanners

**Test all scans now:**
```bash
python run_daily.py --now
```

**Run just pre-market scan:**
```bash
python premarket_scanner.py
```

**Run just EOD scan:**
```bash
python eod_scanner.py
```

**Start scheduler (runs all day):**
```bash
python run_daily.py
```

### Step 4: Use in Your Trading Bot

```python
# In your FPB or ORB strategy:
from watchlist_reader import load_watchlist

# Get today's symbols
symbols = load_watchlist()

# Trade only these stocks
for symbol in symbols:
    run_fpb_strategy(symbol)
```

## 📁 File Structure

```
scanners/
├── config.py              # All settings in one place
├── premarket_scanner.py   # Gap-up scanner
├── eod_scanner.py         # Daily pattern scanner
├── merge_watchlists.py    # Combines scans
├── watchlist_reader.py    # Load watchlist into bots
├── run_daily.py           # Automation script
├── universe.txt           # Stocks to scan (edit weekly)
├── requirements.txt       # Dependencies
│
└── output/
    ├── watchlist.json         # Final merged watchlist
    ├── watchlist_premarket.json   # Pre-market results
    ├── watchlist_eod.json     # EOD results
    └── watchlist.txt          # Simple symbol list
```

## 🔧 Configuration

Edit `config.py` to adjust:

```python
# Gap requirements
MIN_GAP_PCT = 3.0          # Minimum gap % (bootcamp: 3%+)
MIN_PRICE = 5.0            # Minimum stock price
MAX_PRICE = 500.0          # Maximum stock price

# Volume filters
MIN_PREMARKET_VOLUME = 100000   # Pre-market shares
MIN_RELATIVE_VOLUME = 2.0       # Today vs average
MIN_AVG_DAILY_VOLUME = 500000   # Liquidity filter

# Strategy settings
RISK_PER_TRADE = 250.0     # $ risk per trade
MAX_POSITIONS = 5          # Max concurrent positions
```

## 📊 Scanner Criteria

### Pre-Market Scanner (Gap Stocks)
| Filter | Value | Why |
|--------|-------|-----|
| Gap % | ≥ 3% | Bootcamp minimum |
| Price | $5-500 | Tradeable range |
| Volume | 2x+ relative | Confirms interest |
| News | Preferred | Catalyst needed |

### EOD Scanner (Daily Patterns)
| Pattern | Description |
|---------|-------------|
| Flat Top Breakout | 3+ resistance touches |
| Bull Flag | 10%+ pole + tight flag |
| Pullback to MA | Bounce off 20/50 EMA |
| Base Breakout | Tight consolidation |

## 🎯 Priority Ranking

1. **⭐ Gap + Pattern** - Stocks that gapped AND have daily pattern (BEST!)
2. **📈 Gap Only** - Pre-market gappers with catalyst
3. **📊 Pattern Only** - Technical setups without gap

## 📅 Daily Schedule

| Time (ET) | Action |
|-----------|--------|
| 6:00 AM | Pre-market scan (first pass) |
| 9:00 AM | Pre-market scan (update) |
| 9:25 AM | Merge watchlists |
| 9:30 AM | Day trading starts |
| 4:15 PM | EOD scan for tomorrow |

## 🔗 Integration with FPB/ORB

### Simple Integration
```python
# At the top of your fpb_strategy.py
from watchlist_reader import load_watchlist

# Replace hardcoded symbols
# OLD: symbols = ["NVDA", "AMD", "TSLA"]
# NEW:
symbols = load_watchlist()

# Rest of your strategy...
```

### Smart Integration (Use Context)
```python
from watchlist_reader import load_watchlist_with_context

stocks = load_watchlist_with_context()

for stock in stocks:
    # Best setups get more size
    if stock['source'] == 'both':  # Gap + Pattern
        risk = 500  # Double risk
    else:
        risk = 250  # Normal risk
    
    run_fpb_strategy(stock['symbol'], risk_dollars=risk)
```

## 🐛 Troubleshooting

**"No gappers found"**
- Normal on quiet days
- Check universe.txt has enough stocks
- Lower MIN_GAP_PCT temporarily for testing

**"Alpaca not available"**
- Scanner falls back to Yahoo Finance
- Install: `pip install alpaca-py`
- Set API keys in environment or config.py

**"Schedule not running"**
- Install: `pip install schedule`
- Or run manually: `python run_daily.py --now`

## 📝 Weekly Maintenance

1. **Update universe.txt** with hot stocks
2. **Review scan results** - are good stocks being found?
3. **Adjust filters** if needed (too many/few results)
4. **Check news detection** - manually verify catalysts

## 🚀 Next Steps

1. Run `python run_daily.py --now` to test
2. Check `output/watchlist.json` for results
3. Integrate with your FPB strategy
4. Let it run and refine!

---

Built for Bulls Bootcamp methodology 🐂
