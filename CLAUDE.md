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

## Current Status (as of 2026-10-09)
- Last code work: 2026-01-04 ("Paper Trade option for FPB done").
- Latest FPB backtest: only 15 trades, 53% win rate, +5R. Too small a sample to trust.
- No paper-trading results are saved in the repo.

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

## Next Steps
1. Clean up: remove hardcoded paths, load keys from environment, fix `requirements.txt`,
   add `.gitignore`, delete junk files.
2. Add Alpaca historical data loader; re-run FPB backtest on a large sample.
3. Build a "market weather" (regime) detector that labels each day.
4. Test ORB and FPB separately per regime.
5. Build the rule-based strategy selector from those results.
6. Open question for the user: what tells *them* a day is a "long day" vs a "short day"?
