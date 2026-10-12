# ORB-Bot — Project Memory

Claude reads this file at the start of every chat. Keep it up to date: at the end of
each work session, update **Current Status**, **Decisions Log**, and **Next Steps**.

## About the user
- Comes up with trading concepts; does **not** write code.
- Explain everything in plain, simple language. Walk through steps like teaching a beginner.
- Avoid jargon; when a trading or coding term is needed, define it in one line.
- Originally ran the bot on Windows (`C:\Users\Hassan\ORB-Bot`, PowerShell).

## What this project is
A day-trading bot for US stocks, paper-trading through Alpaca.

- **ORB (Opening Range Breakout)** — Nov 2025. Trade breakouts of the first minutes' range.
  Files: `Elite_orb_strategy.py`, `simple_framework.py`, `Quant_engine.py`, `config/paper.yaml`.
  Mostly shelved in favor of FPB.
- **FPB (First Pullback Buy)** — Dec 2025–Jan 2026, the current focus.
  Stock gaps and spikes at the open → wait for a pullback to the EMA → enter with a
  confirmation candle. Picks LONG or SHORT itself from the direction of the opening spike.
  - Strategy + backtest: `fpb_strategy.py`, `run_fpb_backtest.py`, `test_fpb.py`
  - Paper trader (Alpaca): `fpb_paper_trader.py` (commands: run, `monitor`, `close`, `log`)
  - Full how-to: `FPB_MASTER_REFERENCE.md`
- **Scanners** — `scanners/`: pre-market gappers, end-of-day patterns, merged watchlist
  (`scanners/run_daily.py --now`). Watchlists are written to `output/` and `scanners/output/`.

Data source today: `yfinance` (free; only ~7 days of 1-min bars / ~60 days of 5-min bars).

## Big goal
A **smart strategy-selector bot**: it reads market conditions ("regime": trending up,
trending down, choppy, high volatility) and decides on its own whether to go long, short,
which strategy to use (ORB, FPB, ...), or to sit out.

Agreed approach, simplest first:
1. Rule-based selector (user's ideas → written rules).
2. Track-record lookup (which strategy worked on similar past days).
3. Machine learning only later, with lots of data and out-of-sample testing.

Principles: each strategy must be profitable on its own before it goes into the selector;
always test on data the bot has not seen (avoid overfitting); "sit out" is a valid choice;
do not use a chatbot as the live trading brain — the bot runs on testable rules.

## Current Status (as of 2026-10-12)
- Last code work: 2026-01-04 ("Paper Trade option for FPB done").
- Latest FPB backtest: only 15 trades, 53% win rate, +5R. Too small a sample to trust.
- No paper-trading results are saved in the repo.
- The user's PC copy is NEWER than GitHub and has real Alpaca keys typed into the code.
  Do not upload it to GitHub until the keys are moved out (see fix 4 below).
- 2026-10-09: paper bot left stuck positions in MVST, SOFI, GOOGL. User told to close them
  manually in Alpaca and to NOT run the bot again until fixes 1–3 below are done.

## Paper-trading bugs: fix these first (plumbing only, don't change the strategy)
Found 2026-10-09 to 2026-10-12, in `fpb_paper_trader.py`:
1. **Shorting causes messes** → add a `ALLOW_SHORTS = False` switch; trade longs only for now.
2. **"Amnesia"** → `get_positions()` hides errors (`except: return {}`), so if the Alpaca
   call fails the bot thinks it owns nothing and can double up. Make it stop instead.
   Re-check real Alpaca positions and open orders before every scan and every order.
3. **No "can I afford this?" check** → share size comes only from risk ÷ stop distance.
   A tight stop can mean a huge order. Cap shares by buying power and a max $ per trade.
4. **Keys in code** → load `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` from a `.env` file that
   is listed in `.gitignore`. Only after this, push to GitHub.
5. **No stop-loss or target orders are sent to Alpaca** → stops and targets are only printed.
   Use bracket orders (entry + stop + target in one order) so every trade is protected
   even if the bot crashes.
6. **Stale signals** → the scan can find a pullback that happened hours ago and buy at
   today's market price with the old share size. Only act on signals from the last bar or two.
7. Remove hardcoded paths (`BOT_DIR = "C:/Users/Hassan/ORB-Bot"`).
After fixes: run longs only and watch the first hour. After each fill, check that Alpaca and
the bot agree on what's owned. Judge the strategy only after 150+ clean trades.

## Known issues
- Hardcoded Windows paths (e.g. `BOT_DIR = "C:/Users/Hassan/ORB-Bot"` in `fpb_paper_trader.py`).
- API keys are meant to be pasted into code; they should come from environment variables or
  an untracked `.env` file instead. Never commit real keys.
- `requirements.txt` is saved as UTF-16 (tools may fail to read it); it should be UTF-8.
- Clutter in git: `__pycache__/`, `*.backup`, `fpb_strategy backup backtest.py`, many old logs.

## Decisions Log
- 2026-10-09: Resumed project. Plan to switch historical data to Alpaca (years of minute bars)
  so backtests have hundreds of trades. Agreed on the strategy-selector goal above.
- 2026-10-09: Created this CLAUDE.md as cross-chat memory.
- 2026-10-12: Work happens in a Claude Code session on the user's PC, opened on the
  local ORB-Bot folder (the PC copy is the newest). One AI tool only, no Codex.
  Fix the paper-trading bugs before any new strategy work.

## Next Steps
1. Fix the paper-trading bugs above (in that order), then push to GitHub.
   Also: fix `requirements.txt`, add `.gitignore`, delete junk files.
2. Add Alpaca historical data loader; re-run FPB backtest on a large sample.
3. Build a "market weather" (regime) detector that labels each day.
4. Test ORB and FPB separately per regime.
5. Build the rule-based strategy selector from those results.
6. Open question for the user: what tells *them* a day is a "long day" vs a "short day"?
