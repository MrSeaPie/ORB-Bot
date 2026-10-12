# FPB PAPER TRADING BOT - MASTER REFERENCE
> Last Updated: October 12, 2026 (first written Dec 31, 2025; the old "2024" date was a typo)
> Location: the `ORB-Bot` folder (on Hassan's PC: `C:\Users\Hassan\ORB-Bot\`)
>
> ⚠️ The paper trader has known bugs (shorts, broker sync, order size). See `CLAUDE.md`.
> Don't run it until they're fixed.

---

## QUICK START (Daily Routine)

```powershell
# 1. Open PowerShell, go to the bot folder, switch on the project's Python
cd C:\Users\Hassan\ORB-Bot
.\.venv\Scripts\Activate.ps1

# 2. Run scanner (9:25 AM)
python scanners\run_daily.py --now

# 3. Run paper trader (9:35 AM). It scans, trades, monitors and exits at 3:55 PM
python fpb_paper_trader.py

# 4. Check positions (anytime, in a second PowerShell window)
python fpb_paper_trader.py status

# 5. Emergency: close all positions
python fpb_paper_trader.py close
```

Every command works from the `ORB-Bot` folder. You don't need to `cd` into `scanners`.

---

## ONE-TIME SETUP

### Step 1: Get Alpaca Paper Trading Keys
1. Go to: https://app.alpaca.markets/paper/dashboard/overview
2. Click "API Keys" → Generate new keys
3. Copy `.env.example` to a new file named `.env` and paste the keys after the `=` signs:
```
ALPACA_API_KEY=PKXXXXXXXXXXXXXXXXXX
ALPACA_SECRET_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```
`.env` is listed in `.gitignore`, so it never gets uploaded to GitHub. Never paste keys into a `.py` file.

### Step 2: Install Dependencies (if needed)
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## ALL COMMANDS

### Scanner Commands
```powershell
python scanners\run_daily.py --now        # Run all scans immediately
python scanners\run_daily.py --premarket  # Pre-market scan only
python scanners\run_daily.py --eod        # End-of-day scan only
python scanners\run_daily.py --merge      # Merge watchlists only
python scanners\run_daily.py              # Start scheduler (needs: pip install schedule)
```

### Paper Trader Commands
```powershell
python fpb_paper_trader.py            # THE MAIN ONE: scan, enter, monitor, exit
python fpb_paper_trader.py scan       # One-time scan (no monitoring)
python fpb_paper_trader.py monitor    # Just monitor existing positions
python fpb_paper_trader.py status     # Show current state
python fpb_paper_trader.py close      # Close all positions
python fpb_paper_trader.py log        # Today's activity + slippage
python fpb_paper_trader.py slippage   # All-time slippage analysis
python fpb_paper_trader.py help       # Show help
```
⚠️ A mistyped command (e.g. `stauts`) currently starts the full trading run. Type carefully.

### Backtest Commands (Testing Only)
```powershell
python fpb_strategy.py              # Run backtest on watchlist
python run_fpb_backtest.py          # Run backtest with custom symbols
```

---

## FILE STRUCTURE

```
ORB-Bot\
├── fpb_strategy.py           # The FPB rules (used by backtest AND paper trader)
├── fpb_paper_trader.py       # Paper trading on Alpaca (imports fpb_strategy.py)
├── run_fpb_backtest.py       # Backtest runner
├── .env                      # Your Alpaca keys (never uploaded)
├── .env.example              # Blank template for .env
├── requirements.txt          # Python packages to install
├── CLAUDE.md                 # Project memory for Claude: status, bugs, plan
│
├── output\                   # Scanner results (the ONLY watchlist folder)
│   ├── watchlist.json        # Final merged watchlist (the bot reads this)
│   ├── watchlist_premarket.json
│   └── watchlist_eod.json
│
├── scanners\
│   ├── run_daily.py          # Scanner automation
│   ├── premarket_scanner.py  # Gap scanner
│   ├── eod_scanner.py        # Daily pattern scanner
│   ├── merge_watchlists.py   # Combines scans
│   ├── watchlist_reader.py   # Prints the watchlist summary
│   ├── config.py             # Scanner settings
│   └── universe.txt          # Stocks to scan
│
└── logs\
    ├── fpb_trades\           # Backtest trade logs
    └── paper_trades\         # Paper trading logs
```

Old files (ORB code, Quant_engine.py, backups, one-off scripts) were removed on Oct 12, 2026.
They're still in the GitHub history if ever needed.

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
    risk_dollars=250.0,       # $ risk per trade (backtest only)
    target_r1=1.5,            # First target (sell half)
    target_r2=3.0,            # Runner target
    use_ema_trail=True,       # Trail stop with 9 EMA after R1
)
```

### Paper Trader Settings (top of fpb_paper_trader.py)
```python
RISK_PERCENT = 1.0           # Risk 1% of account per trade
MAX_POSITIONS = 3            # Max simultaneous positions
MAX_DAILY_LOSS = 500.0       # Stop trading if down $500 today
SCAN_START_TIME = "09:35"    # Start scanning for entries
SCAN_END_TIME = "11:00"      # Stop scanning for new entries
EOD_EXIT_TIME = "15:55"      # Close all positions
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

Note: the bootcamp rule "pullback on LOW volume" is **not** checked by `fpb_strategy.py` yet.

**Backtest Results (unverified)**: 47.7% win rate, $1,840 profit over 60 days (44 trades).
44 trades is far too few to trust, and the numbers don't add up. Re-run before relying on it.

---

## KNOWN ISSUES & FIXES

The full, current bug list lives in `CLAUDE.md`. Common error messages:

### Issue: "No scanner watchlist found"
**Fix**: Run the scanner first: `python scanners\run_daily.py --now`

### Issue: "API keys not set" / "Alpaca connection failed"
**Fix**: Check that `.env` exists in the `ORB-Bot` folder and has both keys (see Setup Step 1)

### Issue: "No module named yfinance" (or alpaca)
**Fix**: You're using the wrong Python. Run `.\.venv\Scripts\Activate.ps1` first.

---

## LOGS LOCATION

| Log Type | Location |
|----------|----------|
| Paper trades | `logs/paper_trades/paper_YYYY-MM-DD.json` |
| Backtest trades | `logs/fpb_trades/fpb_trades_YYYYMMDD_HHMMSS.csv` |
| Scanner output | `output/watchlist.json` |

---

## FOR FUTURE AI CHATS

Claude Code reads `CLAUDE.md` automatically, so there's nothing to paste.
Keep `CLAUDE.md` up to date at the end of each work session.

---

## DAILY SCHEDULE

| Time (ET) | Action | Command |
|-----------|--------|---------|
| 9:25 AM | Run scanner | `python scanners\run_daily.py --now` |
| 9:35 AM | Run paper trader | `python fpb_paper_trader.py` |
| Anytime | Check positions | `python fpb_paper_trader.py status` |
| 3:55 PM | Auto exit | (the paper trader closes positions itself if still running) |
| 4:15 PM | EOD scan (optional) | `python scanners\run_daily.py --eod` |

---

## WHEN TO JUDGE THE RESULTS

All paper trade logs are in `logs\paper_trades\`, one file per day (`paper_2026-01-09.json`, ...).

Only judge the strategy after **150+ clean paper trades** (no bug-caused trades).
If results are good (40%+ win rate, positive PnL after slippage):
1. Consider live trading with small size
2. Start with 1 position max
3. Scale up gradually

---

## CONTACT / RESOURCES

- Alpaca Dashboard: https://app.alpaca.markets/paper/dashboard/overview
- Strategy Source: Bulls Bootcamp Sessions 64-77 (Kunal)
- Python: the project's `.venv` folder (Python 3.13, has alpaca-py, pandas, yfinance)
