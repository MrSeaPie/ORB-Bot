# FPB PAPER TRADING BOT - MASTER REFERENCE
> Last Updated: December 31, 2024
> Location: C:\Users\Hassan\ORB-Bot\

---

## QUICK START (Daily Routine)

```powershell
# 1. Open PowerShell, go to bot folder
cd C:\Users\Hassan\ORB-Bot

# 2. Run scanner (9:25 AM)
cd scanners
python run_daily.py --now
cd ..

# 3. Run paper trader (9:35 AM)
python fpb_paper_trader.py

# 4. Check positions (anytime)
python fpb_paper_trader.py monitor

# 5. Close all positions (3:55 PM)
python fpb_paper_trader.py close
```

---

## ONE-TIME SETUP

### Step 1: Fix the Path Bug
```powershell
cd C:\Users\Hassan\ORB-Bot
python fix_watchlist_path.py
```

### Step 2: Get Alpaca Paper Trading Keys
1. Go to: https://app.alpaca.markets/paper/dashboard/overview
2. Click "API Keys" → Generate new keys
3. Edit `fpb_paper_trader.py` lines 25-26:
```python
ALPACA_API_KEY = "PKXXXXXXXXXXXXXXXXXX"
ALPACA_SECRET_KEY = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

### Step 3: Install Dependencies (if needed)
```powershell
pip install yfinance pandas numpy alpaca-py
```

---

## ALL COMMANDS

### Scanner Commands
```powershell
cd C:\Users\Hassan\ORB-Bot\scanners

python run_daily.py --now        # Run all scans immediately
python run_daily.py --premarket  # Pre-market scan only
python run_daily.py --eod        # End-of-day scan only
python run_daily.py --merge      # Merge watchlists only
python run_daily.py              # Start scheduler (runs all day)
```

### Paper Trader Commands
```powershell
cd C:\Users\Hassan\ORB-Bot

python fpb_paper_trader.py           # Scan for setups and trade
python fpb_paper_trader.py monitor   # Show open positions
python fpb_paper_trader.py close     # Close all positions
python fpb_paper_trader.py log       # Show today's log
python fpb_paper_trader.py help      # Show help
```

### Backtest Commands (Testing Only)
```powershell
cd C:\Users\Hassan\ORB-Bot

python fpb_strategy.py              # Run backtest on watchlist
python run_fpb_backtest.py          # Run backtest with custom symbols
```

---

## FILE STRUCTURE

```
C:\Users\Hassan\ORB-Bot\
├── fpb_strategy.py           # YOUR STRATEGY (600 lines, 47.7% win rate)
├── fpb_paper_trader.py       # Paper trading wrapper (imports fpb_strategy.py)
├── fix_watchlist_path.py     # One-time path fix script
├── Quant_engine.py           # Multi-strategy engine (future use)
├── Elite_orb_strategy.py     # A+ ORB setups (future use)
│
├── output/
│   └── watchlist.json        # Scanner output (NEW location - use this!)
│
├── scanners/
│   ├── run_daily.py          # Scanner automation
│   ├── premarket_scanner.py  # Gap scanner
│   ├── eod_scanner.py        # Daily pattern scanner
│   ├── merge_watchlists.py   # Combines scans
│   ├── config.py             # Scanner settings
│   ├── universe.txt          # Stocks to scan
│   └── output/
│       └── watchlist.json    # OLD location (may have stale data)
│
├── logs/
│   ├── fpb_trades/           # Backtest trade logs
│   └── paper_trades/         # Paper trading logs
│
└── config/
    └── paper.yaml            # Config file
```

---

## STRATEGY SETTINGS

### FPB Strategy (fpb_strategy.py)
```python
FPBConfig(
    min_gap_pct=3.0,          # Minimum gap to consider
    max_gap_pct=30.0,         # Maximum gap (avoid extreme)
    min_spike_pct=2.0,        # Min spike before pullback
    max_pullback_candles=6,   # Max bars to wait for entry
    ema_fast=9,               # 9 EMA
    ema_slow=20,              # 20 EMA
    risk_dollars=250.0,       # $ risk per trade
    target_r1=1.5,            # First target (sell half)
    target_r2=3.0,            # Runner target
    use_ema_trail=True,       # Trail stop with 9 EMA after R1
)
```

### Paper Trader Settings (fpb_paper_trader.py)
```python
RISK_PER_TRADE = 250.0       # $ risk per trade
MAX_POSITIONS = 3            # Max simultaneous positions
```

---

## THE FPB STRATEGY LOGIC

1. **Gap Detection**: Stock gaps up 3%+ from previous close
2. **Spike**: Makes higher high in first 15 minutes
3. **Pullback**: Price pulls back (no longer making new highs)
4. **EMA Touch**: Price touches 9 EMA or 20 EMA
5. **Confirmation**: Green candle forms at EMA
6. **Entry**: Buy at close of green candle
7. **Stop**: Below candle low or EMA (whichever lower)
8. **Target R1**: Sell half at 1.5R, move stop to breakeven
9. **Target R2**: Trail rest with 9 EMA, target 3R
10. **Exit**: EOD if still holding

**Backtest Results**: 47.7% win rate, $1,840 profit over 60 days (44 trades)

---

## KNOWN ISSUES & FIXES

### Issue: FPB reading wrong watchlist (stale data)
**Cause**: Two watchlist.json files exist:
- `output/watchlist.json` (NEW - correct)
- `scanners/output/watchlist.json` (OLD - stale)

**Fix**: Run `python fix_watchlist_path.py` once

### Issue: "No scanner watchlist found"
**Fix**: Run the scanner first:
```powershell
cd scanners
python run_daily.py --now
```

### Issue: "Alpaca connection failed"
**Fix**: Check API keys are correct in fpb_paper_trader.py lines 25-26

---

## LOGS LOCATION

| Log Type | Location |
|----------|----------|
| Paper trades | `logs/paper_trades/paper_2025-01-02.json` |
| Backtest trades | `logs/fpb_trades/fpb_trades_YYYYMMDD_HHMMSS.csv` |
| Scanner output | `output/watchlist.json` |

---

## FOR FUTURE AI CHATS

Copy this context when starting a new chat:

```
I'm working on my FPB (First Pullback Buy) day trading bot.

LOCATION: C:\Users\Hassan\ORB-Bot\

KEY FILES:
- fpb_strategy.py = My strategy (600 lines, 47.7% backtest win rate)
- fpb_paper_trader.py = Paper trading wrapper (imports fpb_strategy.py)
- scanners/run_daily.py = Runs gap scanner

WHAT IT DOES:
1. Scanner finds gap-up stocks (3%+)
2. FPB strategy looks for pullback to 9/20 EMA
3. Entry on green candle at EMA
4. Stop below EMA, targets at 1.5R and 3R

CURRENT STATUS:
- Backtest complete: 47.7% win rate, +$1,840 over 60 days
- Now paper trading for 2-3 months to validate
- Using Alpaca paper trading API

I have no coding experience - explain like I'm a beginner.
```

---

## DAILY SCHEDULE

| Time (ET) | Action | Command |
|-----------|--------|---------|
| 9:25 AM | Run scanner | `cd scanners && python run_daily.py --now` |
| 9:35 AM | Run paper trader | `python fpb_paper_trader.py` |
| 10:30 AM | Check positions | `python fpb_paper_trader.py monitor` |
| 12:00 PM | Check positions | `python fpb_paper_trader.py monitor` |
| 3:55 PM | Close all | `python fpb_paper_trader.py close` |
| 4:15 PM | EOD scan (optional) | `cd scanners && python run_daily.py --eod` |

---

## AFTER 2-3 MONTHS

Review paper trading results:
```powershell
# All paper trade logs are in:
C:\Users\Hassan\ORB-Bot\logs\paper_trades\

# Each day has a JSON file like:
paper_2025-01-02.json
paper_2025-01-03.json
...
```

If results are good (40%+ win rate, positive PnL):
1. Consider live trading with small size
2. Start with 1 position max
3. Scale up gradually

---

## CONTACT / RESOURCES

- Alpaca Dashboard: https://app.alpaca.markets/paper/dashboard/overview
- Strategy Source: Bulls Bootcamp Sessions 64-77 (Kunal)
- Python: 3.12 installed at default location
