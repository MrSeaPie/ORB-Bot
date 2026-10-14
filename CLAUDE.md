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
- **TESTING PHASE STARTED 2026-10-12.** Task Scheduler job "ORB-Bot daily" registered with
  Hassan's OK (weekdays 9:20 AM → `run_bot.bat`); test-fired OK (result 0). First live paper
  session: Tue 2026-10-13. Running with defaults: 1% risk, hold to 3:55, MAX_POSITION_PCT 50,
  current universe. The PC sleeps after 1 h idle, so `run` keeps Windows awake while trading.
- After each session, review: `logs/runs/<date>.log`, `logs/paper_trades/paper_<date>.json`,
  and (read-only) Alpaca positions/orders. Check every fill had a matching stop order, exits
  cancelled stops, and the bot and Alpaca ended flat.
- The live `fpb_strategy.py` has NO low-volume-pullback check (Kunal's rule / "V4").
- Tests: `tests/test_paper_trader.py` (fake broker + fake Yahoo data, 69 checks, no internet).
  Run after every change to the trader or scanners. Before every commit run
  `tests/check_no_secrets.py` (the repo is public).
- `private/` (git-ignored) holds course transcripts, e.g. `private/transcripts/orb/`. Never
  upload or quote them in tracked files; write rules in our own words.

## How to work in parallel (agreed 2026-10-13)
- The live bot runs from THIS folder every weekday 9:20 AM–4 PM and loads the code at start.
  Never leave half-finished edits to `fpb_paper_trader.py`, `fpb_strategy.py` or `scanners/`
  here: build new things (ORB, backtester) in a separate git worktree/branch and merge to main
  only after the tests pass, outside market hours.
- One chat per workstream: (a) short chats to review the live FPB days, (b) a separate chat for
  ORB (transcripts → written rules Hassan confirms → data loader → backtest → plug-in).
- Two strategies trading live at once → one Alpaca paper account per strategy (own keys, own
  scheduled task) so results and BrokerSync never mix. Requires the plug-in split first.

## ORB workstream (separate strategy; folder `C:\Users\Hassan\ORB-Bot-orb`, branch `orb-rules`)
Never touches FPB files, the FPB scanner or `universe.txt`. Built in a git worktree beside the live folder.
- `ORB_RULES.md`: the rules in plain words, each tagged [Kunal class] / [Armando] / [Proposed] /
  [Project]. Defaults confirmed by Hassan 2026-10-13 ("if nothing in the course says otherwise").
  Section 12 = what changed and why; section 13 = Kunal's 20 marked charts.
- `alpaca_history.py`: Alpaca price history (SIP, raw prices, NY time), cached per stock per month in
  git-ignored `data_cache/`. Refuses to download 9:15 AM–4:05 PM ET on weekdays (the live bot shares
  the keys and Alpaca's request limit). The ORB folder has its own git-ignored copy of `.env`.
- `orb_strategy.py`: rules as pure functions (`find_orb`, `simulate_trade`, `day_context`).
- `check_kunal_examples.py`: runs the rules on Kunal's 19 ORB charts with real data →
  `logs/orb_checks/kunal_examples.csv`. 2026-10-13: 19/19 found at his candle, 19/19 pass filters
  (recognition only: they are hand-picked winners).
- `tests/test_orb_strategy.py`: 45 offline checks. Run after every ORB change.
- Course material for ORB lives in the ORB folder's `private/` (git-ignored): 20 chart screenshots in
  `private/charts/orb_kunal_examples/`. The transcripts are on Hassan's Desktop (`TRANSCRIPTS\ORB\`,
  `whisper\Release\` for the scanning classes); `private/transcripts/orb/` in the live folder is empty.
- Run with the live folder's Python: `C:\Users\Hassan\ORB-Bot\.venv\Scripts\python.exe -X utf8 <file>`.
- `orb_stock_finder.py`: ORB's own morning list from daily candles of ~13,200 stocks (gappers,
  yesterday's movers, go-to). Research mode by default: every candidate, no top-N cut.
- `run_orb_backtest.py`: month by month; 5-min candles per stock-month + 1-min "mornings" (9:30–11:35)
  per trade, fetched in parallel (6 threads, one shared limiter ~170 requests/min). Writes
  `logs/orb_trades/<label>_summary.txt / _trades.csv / _decisions.csv` (git-ignored outputs, not committed).
  Development period up to 2025-06 (choose options here); holdout 2025-07 on (confirm only).
- Results so far (2026-10-13):
  - May 2025 pilot, top 10 by gap: about break-even, and none of Kunal's May stocks made the list.
  - May 2025 research mode, all 1,546 candidates traded: −0.29R a trade after slippage (most
    breakouts fail; slippage ≈ 0.24R a trade with ~1.75% stops).
  - But clear gradients: more pre-market volume, more first-15-minute volume and a bigger daily ATR
    are better. 1M+ pre-market shares: +0.17R.
  - One month only, so nothing was chosen from it.
  - The development year (2024-07 → 2025-06) was started the evening of 2026-10-13 →
    `logs/orb_trades/dev_2024-07_2025-06_*`.
- Next: (1) read the development-year breakdown and choose the stock ranking/filters there only. (2) Run
  the holdout (2025-07 → 2026-09) with that ranking and a realistic top-N per day. (3) Only if it holds
  up: a second Alpaca paper account + its own schedule. Open questions: #7 go-to stocks, #9 where chart
  CRK came from.

## Paper-trading journal (one line per session; judge the strategy only after 150+ trades)
- 2026-10-13 (day 1): 4 trades, all SHORT (watchlist was mostly gap-downs): DELL -$15.30 and
  ARM -$22.38 (stopped out < 1 min after entry), RIOT -$70.38 (stop), SMCI +$36.03 (R1, then
  trailed stop). Net -$72.03. PLUMBING PASSED: bot P&L = Alpaca equity change to the cent;
  every fill got its stop order within 3 s; R1 → breakeven → 5 trailing moves all done as
  cancel + new stop at Alpaca, no strays; ended flat with no open orders; zero warnings.
  Notes: all trades hit the 50% size cap (real risk $14–$58, not $65); stops were tight
  (0.45–0.55% on DELL/ARM) and stop fills slipped $0.35–$0.48; the status line says "Scan
  window closed" before 9:35 (cosmetic, should say "starts 9:35").

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
8. ~~Register the schedule?~~ Yes, registered 2026-10-12.
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

- 2026-10-13: ORB rules written from Kunal's 6 ORB classes, his 2 scanning classes, 2 guest webinars
  (Armando) and 20 of his marked charts. Hassan: defaults OK unless the course says otherwise. Real-data
  check changed 4 rules to fit Kunal's own trades (direction from the gap; yesterday's range only an
  option; daily ATR 2%; QQQ check only without a news gap). ORB stays fully separate from FPB.

## Next Steps
1. Review the first live sessions (from 2026-10-13): after each fill, Alpaca and the bot must
   agree; stop orders must show in Alpaca's open orders. Fix anything the real broker does
   differently from the fake one.
2. Hassan: decide the stock list (open question 7) and the open strategy rules.
3. Add Alpaca historical data loader; re-run FPB backtest on a large sample (200+ trades),
   with slippage, on the right stocks; compare with/without the low-volume pullback rule.
4. Split `fpb_paper_trader.py` into shared layers (see Architecture plan) before strategy #2.
5. Build a "market weather" (regime) detector; test ORB and FPB per regime; build selector.
6. Paper trade for months (150+ clean trades) before any real money.
