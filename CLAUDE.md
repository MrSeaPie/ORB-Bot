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

Principles: each strategy must be profitable on its own before it goes into the selector;
always test on data the bot has not seen (avoid overfitting); "sit out" is a valid choice;
do not use a chatbot as the live trading brain — the bot runs on testable rules.

## Current Status (as of 2026-10-12)
- Paper trading ran Jan 4 – Feb 5, 2026 (logs in `logs/paper_trades/`): ~3 real round trips.
  Plumbing bugs left stuck positions (MVST long 805, SOFI short, GOOGL short 42), about
  -$3.4k unrealized, which blocked every later trade. User to close them by hand in Alpaca.
  **Do NOT run the bot until bugs 1–3 below are fixed.**
- Strategy is unvalidated: every backtest sample is under 75 trades.
- 2026-10-12 done: keys moved to `.env`; repo cleaned (99 unused files removed);
  paths made relative; requirements.txt fixed; docs rewritten; all pushed to GitHub.
- The live `fpb_strategy.py` has NO low-volume-pullback check (Kunal's rule / "V4").

## Paper-trading bugs: fix these first (plumbing only, don't change the strategy)
In `fpb_paper_trader.py`:
1. ✅ DONE 2026-10-12. **Short exits made the short bigger** (every exit called `sell()`;
   GOOGL 21 → 42, SOFI 214 → 428). Now all exits go through `AlpacaClient.close()`, which uses
   Alpaca's close-position order: right side automatically, can only shrink a position.
   Entries: `buy()` for longs, `sell_short()` for shorts. `ALLOW_SHORTS = False` (longs only).
   Tested on a fake broker: old code replays GOOGL to -42, new code to 0.
2. **"Amnesia"** → `get_positions()` hides errors (`except: return {}`), and the bot only trusts
   its own state file. Read real Alpaca positions and open orders on startup and before every
   scan/order; stop if that call fails; flag positions the bot didn't open.
   Also: when an exit order FAILS, every `_exit_*` falls back to `fill_price = current_price`
   and removes the position from state, logging a fake fill. It must keep the position instead.
3. **No "can I afford this?" check** → shares = risk ÷ stop distance only. QS asked for
   1,618 shares (~$11.5k) on a ~$7.6k account. Cap by buying power ÷ open slots.
4. ✅ DONE 2026-10-12. Keys live only in `.env` (git-ignored). Never in git history.
5. **No stop/target orders at Alpaca** → stops only exist while the script runs. Use bracket orders.
6. **Stale signals** → a pullback from hours ago can trigger a buy at today's price.
   Only act on signals from the last bar or two.
7. ✅ DONE 2026-10-12. Hardcoded paths removed (bot, strategy and scanners).
8. **Rejected signals retried every 5 min** (QS, MSTR, MARA) → one attempt per ticker per day.
9. **Order that would flip a position is rejected** by Alpaca (SOFI buy 376 while short 52).
10. **Mistyped command starts trading** → unknown command falls through to `cmd_run()`.
11. **End-of-day close needs the script running** → needs a scheduler (Task Scheduler) later.
    Note: the bot prints emoji; with output redirected to a file, Windows' default encoding
    (cp1252) crashes `print()`. Run with `python -X utf8` (or set PYTHONUTF8=1) when scheduling.
After fixes: run longs only and watch the first hour. After each fill, check that Alpaca and
the bot agree on what's owned. Judge the strategy only after 150+ clean trades.

## Scanner / stock-selection issues (fix after the plumbing)
- `premarket_scanner.py` only saves when it finds ≥1 stock, so a 0-result day leaves the
  OLD file and the merge uses stale gaps (Oct 9 watchlist merged a May 6 pre-market scan).
  The merge should ignore scan files not from today.
- `universe.txt` starts with mega-caps (AAPL, MSFT, GOOGL, AMZN, META...). Biggest lesson so
  far: Kunal trades news/earnings gappers and small/mid-caps, not mega-caps.
- `load_watchlist_symbols()` silently falls back to NVDA/AMD/TSLA/COIN/MSTR if no watchlist.

## Open questions for the user
1. Risk: $250 fixed (strategy docs) or 1% of account (paper trader, current code)?
2. Exit: FPB rules say out by 11:00 (hard exit 11:30); paper trader holds until 3:55.
3. Gap minimum 3% or 4%? Stop under candle low or under 20 EMA? Candle body min 15% or 30%?
4. Shorts are OFF (`ALLOW_SHORTS = False`) since 2026-10-12. When should they come back on?
5. Make the GitHub repo private? (Then PROJECT_HISTORY.md can be uploaded too.)
6. What tells *him* a day is a "long day" vs a "short day"?

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

## Next Steps
1. Fix paper-trading bugs 2, 3 (in that order), then 5, 6, 8–10. One at a time, tested.
2. Fix the stale pre-market merge; review `universe.txt` with the user.
3. Add Alpaca historical data loader; re-run FPB backtest on a large sample (200+ trades),
   with slippage, on the right stocks; compare with/without the low-volume pullback rule.
4. Build a "market weather" (regime) detector that labels each day.
5. Test ORB and FPB separately per regime.
6. Build the rule-based strategy selector from those results.
7. Automate (scheduler) and paper trade for months before any real money.
