# ORB-Bot

A day-trading bot for US stocks. It paper-trades (fake money) through Alpaca.
The current strategy is **FPB (First Pullback Buy)**.

> **Status:** not validated yet, and the paper trader has known bugs (see `CLAUDE.md`).
> Don't run it until those are fixed, and never with real money.

## How the pieces fit

```
scanners/run_daily.py      finds gapping stocks, writes output/watchlist.json
        ↓
fpb_paper_trader.py        watches those stocks, uses the rules in fpb_strategy.py,
        ↓                  places orders on your Alpaca PAPER account
logs/paper_trades/         one log file per trading day
```

## Files

| File / folder | What it does |
|---|---|
| `fpb_strategy.py` | The FPB rules (gap → spike → pullback to EMA → entry). Used by both the backtest and the paper trader. |
| `fpb_paper_trader.py` | Runs FPB on the Alpaca paper account. |
| `run_fpb_backtest.py` | Tests FPB on past price data. Results go to `logs/fpb_trades/`. |
| `scanners/` | Pre-market gap scanner, end-of-day pattern scanner and the merge step. Stock list: `scanners/universe.txt`. Settings: `scanners/config.py`. |
| `output/` | The latest watchlists the scanners wrote. |
| `logs/` | Paper-trade logs and backtest results. |
| `FPB_MASTER_REFERENCE.md` | The full how-to: commands, settings, strategy rules. |
| `CLAUDE.md` | Project memory that Claude reads at the start of every chat: status, bugs, plan. |

## One-time setup

1. Copy `.env.example` to `.env` and paste your Alpaca **paper** keys into it.
   `.env` never gets uploaded to GitHub.
2. Install the packages into the project's Python:
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

## Daily commands

Run these in PowerShell from the `ORB-Bot` folder:

```powershell
.\.venv\Scripts\Activate.ps1          # use the project's Python
python scanners\run_daily.py --now    # 9:25 AM: build today's watchlist
python fpb_paper_trader.py            # 9:35 AM: scan, trade, monitor, exit at 3:55 PM
```
