# ORB-Bot — Project Memory

Claude reads this file at the start of every chat. Keep it up to date: at the end of
each work session, update **Current Status**, **Decisions Log**, and **Next Steps**.

Full background (strategy rules, every past result and error, vision): `PROJECT_HISTORY.md`.
It's kept on the PC only and is git-ignored, because the GitHub repo is **public** and the doc
has personal details. If it disagrees with the code, trust the code and tell the user.

## About the user (Hassan)
- Comes up with trading concepts; does **not** write code.
- Explain everything in plain, simple language. Walk through steps like teaching a beginner.
- Avoid jargon; when a trading or coding term is needed, define it in one line.
- Be blunt and honest; don't flatter results. Test before saying something works.
- Has a full-time job: can't babysit the bot or type commands at exact times.
- Runs Windows (`C:\Users\Hassan\ORB-Bot`, PowerShell 5.1: no `&&`, use `;`).
- Python: use the project's `.venv` (Python 3.13, has alpaca-py, pandas, yfinance).
  PROJECT_HISTORY.md says Python 3.12, but the working `.venv` is 3.13.

## What this project is
A day-trading bot for US stocks, paper-trading through Alpaca. Strategies come from
Bulls Bootcamp (instructor Kunal).

The pipeline (these are the ONLY code files, after the 2026-10-12 cleanup):
- `scanners/run_daily.py --now` → `premarket_scanner.py` (gaps) + `eod_scanner.py` (daily
  patterns) → `merge_watchlists.py` → `output/watchlist.json`. Settings: `scanners/config.py`.
  Stock list: `scanners/universe.txt`. Works from any folder; `output/` is the only watchlist folder.
- `fpb_strategy.py`: **FPB (First Pullback Buy)** rules, the current focus. Gap + spike at
  the open → pullback to 9/20 EMA → confirmation candle. Picks LONG or SHORT from the spike.
- `fpb_paper_trader.py` (v3): paper trades FPB on Alpaca. Commands: (none)=run, `scan`,
  `monitor`, `status`, `close`, `log`, `slippage`, `help`. Logs to `logs/paper_trades/`.
- `run_fpb_backtest.py`: backtest. Logs to `logs/fpb_trades/`.
- How-to for the user: `FPB_MASTER_REFERENCE.md`. Overview: `README.md`.

ORB (Opening Range Breakout, Nov 2025) was shelved; its code was removed on 2026-10-12
(still in git history, e.g. commit `ac3d2db`). Rebuild it properly when the selector needs it.

Data source today: `yfinance` (free; only ~7 days of 1-min bars / ~60 days of 5-min bars).

## Big goal
A **smart strategy-selector bot**: it reads market conditions ("regime": trending up,
trending down, choppy, high volatility) and decides on its own whether to go long, short,
which strategy to use (ORB, FPB, ...), or to sit out.

Agreed approach, simplest first:
1. Rule-based selector (user's ideas → written rules). Kunal's tree is a first version:
   stock pops → consolidates sideways = ORB; pulls back to 9/20 EMA = FPB; tanks = skip.
2. Track-record lookup (which strategy worked on similar past days).
3. Machine learning only later, with lots of data and out-of-sample testing.

Architecture plan (agreed 2026-10-12, "mini quant fund"): after the plumbing bugs and before a
second strategy, split `fpb_paper_trader.py` into shared layers every strategy reuses: data →
strategy plug-ins (each only says symbol, direction, entry, stop, targets) → selector → risk &
sizing → execution + `BrokerSync` → logging & per-strategy performance. Adding a strategy should
then mean writing only its signal rules, tested with the same backtester.

Principles: each strategy must be profitable on its own before it goes into the selector;
always test on data the bot has not seen (avoid overfitting); "sit out" is a valid choice;
do not use a chatbot as the live trading brain — the bot runs on testable rules.

## Current Status (as of 2026-10-12)
- Paper trading ran Jan 4 – Feb 5, 2026 (logs in `logs/paper_trades/`): ~3 real round trips.
  Plumbing bugs left stuck positions (MVST, SOFI, GOOGL), ~-$3.4k, blocking later trades.
- Alpaca paper account (read-only check 2026-10-12): equity $6,565.84, no positions or orders,
  shorting enabled, 4x margin ($26,263 buying power). Alpaca reports no pattern-day-trader
  fields for this account any more. Re-check day-trading rules before going live.
- **All known paper-trading bugs are fixed (2026-10-12)**, see below. The bot is ready for
  PAPER testing. Strategy is still unvalidated (every backtest sample < 75 trades).
- End-to-end run of `run_bot.bat` on 2026-10-12 (after the close) worked: scanner → 20-stock
  watchlist → bot connected, synced, saw the market closed, stopped. No orders.
- The live `fpb_strategy.py` has NO low-volume-pullback check (Kunal's rule / "V4").
- Test suite (fake broker + fake Yahoo data, 69 checks) lives outside the repo; rebuild it if
  needed: the key tricks are a fake TradingClient that enforces Alpaca's held-shares rule
  (can't close shares a stop order holds) and patched `download_stock_data`/`now_et`.

## Paper-trading bugs: ALL FIXED 2026-10-12 (each its own commit, tested)
1. Short exits made shorts bigger → exits use Alpaca close-position (`AlpacaClient.close()`).
2. "Amnesia" → `BrokerSync`: Alpaca is the truth (startup, every scan/order, every 60 s, end of
   day). Real fills only; failed exits retry; leftovers flagged, never traded.
3. Order size → capped at `MAX_POSITION_PCT` (50%) of equity and buying power ÷ open slots.
4. Keys → `.env` only (git-ignored), never in history.
5. No stops at Alpaca → GTC stop order (`client_order_id` "fpbstop-…") placed after every fill and
   kept in line with the position (`PositionMonitor._ensure_stop`): breakeven after R1, trailing,
   resized after partial fills. Exits cancel it first (`_release_stop`); fills of it are recorded
   (`record_stop_fill`). `BrokerSync` cancels our stop orders whose position is gone or duplicated.
6. Stale signals → act only on a signal candle ≤ `MAX_SIGNAL_AGE_MINUTES` (10) old, and not if the
   price is already past the stop.
7. Hardcoded paths → removed.
8. Retrying rejected orders → `ENTRY_FAILED` logged; one attempt per stock per day.
9. Position flips → never enters a stock Alpaca holds or has an order for.
10. Typos started trading → unknown commands print help and exit.
11. Needed Hassan at the keyboard → Alpaca market calendar (holidays, early closes), `now_et()`
    (New York time on any machine), UTF-8 output, `run_bot.bat`, `setup_schedule.ps1`
    (Task Scheduler, weekdays 9:20 AM; NOT registered yet, waiting for Hassan's OK).
Also fixed: live prices from one-sided Alpaca quotes (ask $0 gave AAPL $0.01) → quote only if
two-sided with spread ≤ 2%, else latest trade (< 5 min), else Yahoo 1-min bar.

## Scanner fixes 2026-10-12
- Pre-market gap was YESTERDAY's (no daily bar for today before the open) → now today's latest
  price (pre-market included) vs the last completed close. Alpaca path fixed the same way.
- Gap-downs were dropped → ±3% now (shorts need gap-downs).
- Scans save even when empty; merge ignores a pre-market file not from today and an EOD file
  older than 4 days; gap + pattern bonus only for gap-UPS (the daily patterns are bullish).
- Paper trader trades only from a watchlist dated today (no NVDA/AMD/TSLA fallback).
- `output/` is git-ignored now (rebuilt daily).

## Known issues / data quality (not bugs in the code, but they matter)
- `universe.txt` starts with mega-caps; the EOD scanner gives AAPL/MSFT/GOOGL/AMZN/TSLA score 100.
  Biggest lesson so far: Kunal trades news/earnings gappers and small/mid-caps. Needs Hassan.
- `RIDE` in `universe.txt` has no Yahoo data (possibly delisted).
- Free data: signals use Yahoo (unofficial, can time out); Alpaca free feed is IEX-only
  (thin after hours: IEX last trade can differ a lot from the consolidated price).
- Broker code is all in `AlpacaClient` → switching brokers = rewrite that one class.

## Open questions for the user
1. Risk: $250 fixed (strategy docs) or 1% of account (paper trader, current code)?
2. Exit: FPB rules say out by 11:00 (hard exit 11:30); paper trader holds until 3:55.
3. Gap minimum 3% or 4%? Stop under candle low or under 20 EMA? Candle body min 15% or 30%?
4. ~~Shorts?~~ Answered 2026-10-12: both long and short. `ALLOW_SHORTS = True`.
5. Make the GitHub repo private? (Then PROJECT_HISTORY.md can be uploaded too.)
6. What tells *him* a day is a "long day" vs a "short day"?
7. Which stocks belong in `universe.txt` (drop mega-caps? add small/mid-cap gappers)?
8. OK to register the Task Scheduler job (`setup_schedule.ps1`)?
9. `MAX_POSITION_PCT = 50` is a default Claude picked; confirm or change.

## Decisions Log
- 2026-10-09: Resumed project. Plan to switch historical data to Alpaca (years of minute bars)
  so backtests have hundreds of trades. Agreed on the strategy-selector goal above.
- 2026-10-09: Created this CLAUDE.md as cross-chat memory.
- 2026-10-12: Work happens in a Claude Code session on the user's PC, opened on the
  local ORB-Bot folder. One AI tool only, no Codex.
  Fix the paper-trading bugs before any new strategy work.
- 2026-10-12: User approved deleting everything not used by the pipeline. Removed: old copies
  and backups, ORB code, Quant_engine.py, fix_watchlist_path.py, scanners/output/, old ORB and
  FPB v2/v3 logs. Snapshot commit `ac3d2db` holds the pre-cleanup state.
- 2026-10-12: User wants shorts on and asked to fix all bugs. Stay on Alpaca for paper testing;
  decide the broker (and paid real-time data) before real money.

## Next Steps
1. Hassan: answer open questions 7 and 8 (universe, schedule), then paper trade daily.
2. Watch the first live sessions: after each fill, Alpaca and the bot must agree; stop orders
   must show in Alpaca's open orders.
3. Add Alpaca historical data loader; re-run FPB backtest on a large sample (200+ trades),
   with slippage, on the right stocks; compare with/without the low-volume pullback rule.
4. Split `fpb_paper_trader.py` into shared layers (see Architecture plan) before strategy #2.
5. Build a "market weather" (regime) detector; test ORB and FPB per regime; build selector.
6. Paper trade for months (150+ clean trades) before any real money.
