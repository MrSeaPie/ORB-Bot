"""
Swing backtest: Kunal's daily-chart setups (swing_strategy.py, rules in SWING_RULES.md) on every
liquid US stock, day by day, with slippage. Separate strategy: no FPB or ORB file is used or changed.

    .venv\\Scripts\\python.exe -X utf8 run_swing_backtest.py --start 2024-07-01 --end 2025-06-30 --label dev
    (--fetch first downloads any missing daily candles: refused 9:15 AM-4:05 PM New York time on weekdays)

Writes to logs/swing_trades/:
  <label>_setups.csv   every setup the shapes found, with each of Kunal's checks and the trade's result
  <label>_summary.txt  the report (also printed)
Results are in R (1R = what one trade risks). "Main rule" = a named shape that passes all five of
Kunal's questions AND trades with the market (QQQ vs its 50-day), one trade per stock at a time.
Two periods: development (before 2025-07) may be used to choose; holdout (2025-07 on) only confirms.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import alpaca_history as hist
from orb_strategy import Slippage
from run_orb_backtest import keep_pc_awake, months_between
from swing_strategy import Candles, SwingSettings, find_setups, simulate, slippage_r

HOLDOUT_FROM = "2025-07-01"
OUT = Path(__file__).resolve().parent / "logs" / "swing_trades"
CHECKS = ["liquid", "no_distribution", "ema_tight", "ema_sloped", "bone_zone", "juice", "not_tired", "market"]


def load_daily(begin: date, end: date, fetch: bool) -> pd.DataFrame:
    """Daily candles of every stock from the cache (data_cache/1Day_many), optionally downloading gaps first."""
    if fetch:
        symbols = hist.get_assets().symbol.tolist() + ["QQQ"]
        for first, last in months_between(begin, end):
            hist.get_daily_many(symbols, first, last)
            print(f"  daily candles for {first:%Y-%m} ready", flush=True)
    folder = hist.CACHE_DIR / "1Day_many"
    paths = [p for p in (folder / f"{first:%Y-%m}.csv.gz" for first, _ in months_between(begin, end)) if p.exists()]
    if not paths:
        sys.exit("No daily candles on disk for these months: run with --fetch after 4:05 PM New York time.")
    keep, seen = {"QQQ"}, set()
    for path in paths:                                      # pass 1: stocks that are ever busy enough in a month
        m = pd.read_csv(path, usecols=["symbol", "close", "volume"], keep_default_na=False, na_values=[""])
        busy = m.groupby("symbol").agg(volume=("volume", "mean"), close=("close", "max"))
        keep |= set(busy[(busy.volume >= 700_000) & (busy.close >= 4)].index)
        seen |= set(busy.index)
    frames = []
    for path in paths:                                      # pass 2: read only those (keeps memory small)
        m = pd.read_csv(path, keep_default_na=False, na_values=[""])
        frames.append(m[m.symbol.isin(keep)])
    daily = pd.concat(frames).drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"])
    print(f"Daily candles {daily.date.min()} to {daily.date.max()}: {len(seen):,} stocks, "
          f"{len(keep):,} of them busy enough at some point", flush=True)
    return daily.reset_index(drop=True)


def market_by_date(daily: pd.DataFrame) -> pd.Series:
    """True on day t if QQQ closed above its 50-day average on day t-1 [Kunal 76, 78]."""
    q = daily[daily.symbol == "QQQ"].set_index("date").close
    return (q > q.rolling(50).mean()).shift(1).where(q.rolling(50).mean().shift(1).notna())


def run(daily, start: str, end: str, s: SwingSettings, slip: Slippage) -> pd.DataFrame:
    market = market_by_date(daily)
    rows = []
    groups = daily[daily.symbol != "QQQ"].groupby("symbol", sort=True)
    for n, (symbol, df) in enumerate(groups, 1):
        if n % 500 == 0:
            print(f"  {n:,}/{groups.ngroups:,} stocks checked, {len(rows):,} setups so far", flush=True)
        if len(df) < 40:
            continue
        a = Candles(df)
        up = market.reindex(a.dates).to_numpy()
        first = int(np.searchsorted(a.dates, start))
        for setup in find_setups(a, s, up, first_day=first):
            if setup["date"] > end:
                break
            worst = simulate(a, setup, s)
            best = simulate(a, setup, s, worst_case_entry_day=False) if worst["unclear_entry"] else worst
            row = {k: v for k, v in setup.items() if k != "t"}
            row.update(symbol=symbol, exit_date=worst["exit_date"], days_held=worst["days_held"],
                       first_exit=worst["first_exit"], last_exit=worst["last_exit"],
                       unclear_entry=worst["unclear_entry"], unclear_day=worst["unclear_day"],
                       exits="; ".join(f"{a.dates[i]} {p:.2f} x{f:g} {why}" for i, p, f, why in worst["exits"]),
                       gross_r=worst["gross_r"], slippage_r=slippage_r(setup, worst, slip),
                       best_case_gross_r=best["gross_r"])
            row["net_r"] = row["gross_r"] - row["slippage_r"]
            row["best_case_net_r"] = row["best_case_gross_r"] - slippage_r(setup, best, slip)
            row["net_r_2x_slippage"] = row["gross_r"] - 2 * row["slippage_r"]
            rows.append(row)
    return pd.DataFrame(rows)


def one_at_a_time(t: pd.DataFrame) -> pd.DataFrame:
    """Keep a stock's setup only if that stock has no trade open (research mode otherwise allows overlaps)."""
    keep, busy_until = [], {}
    for i, r in t.sort_values(["date", "symbol"]).iterrows():
        if r.date > busy_until.get(r.symbol, ""):
            keep.append(i)
            busy_until[r.symbol] = r.exit_date
    return t.loc[keep]


def account(main: pd.DataFrame, daily: pd.DataFrame, start: str, end: str, slots=5, risk_pct=1.0, cap_pct=20.0):
    """
    A realistic account: at most `slots` positions, risk `risk_pct`% of the account per trade, no more
    than `cap_pct`% of the account in one stock; each day the most-traded stocks get the free slots.
    Profits and losses count when a trade closes. Compared with simply holding QQQ.
    """
    equity, open_trades, curve, taken = 100.0, [], [(start, 100.0)], 0
    for d, today in main.sort_values(["date", "dollar_volume_m"], ascending=[True, False]).groupby("date", sort=True):
        for tr in [x for x in open_trades if x[0] < d]:
            equity += tr[1]
            curve.append((tr[0], equity))
        open_trades = [x for x in open_trades if x[0] >= d]
        for _, r in today.iterrows():
            if len(open_trades) >= slots:
                break
            risk_money = equity * risk_pct / 100
            scale = min(1.0, equity * cap_pct / 100 / (risk_money / r.risk * r.entry))
            open_trades.append((r.exit_date, r.net_r * risk_money * scale))
            taken += 1
    for tr in sorted(open_trades):
        equity += tr[1]
        curve.append((tr[0], equity))
    values = pd.Series([v for _, v in curve])
    drawdown = ((values.cummax() - values) / values.cummax()).max() * 100
    q = daily[daily.symbol == "QQQ"].set_index("date").close
    q = q[(q.index >= start) & (q.index <= end)]
    qqq_return = (q.iloc[-1] / q.iloc[0] - 1) * 100
    qqq_drawdown = ((q.cummax() - q) / q.cummax()).max() * 100
    return equity - 100, drawdown, taken, qqq_return, qqq_drawdown


def _line(name, t, col="net_r"):
    if not len(t):
        return f"  {name:42} no trades"
    r = t[col]
    losses = -r[r < 0].sum()
    pf = r[r > 0].sum() / losses if losses else float("inf")
    months = t.groupby(t.date.str[:7])[col].sum()
    return (f"  {name:42} {len(t):6} trades  win {(r > 0).mean():5.1%}  avg {t.gross_r.mean():+.2f}R gross"
            f" / {r.mean():+.2f}R net  total {r.sum():+8.1f}R  PF {pf:4.2f}  months up {(months > 0).sum()}/{len(months)}")


def _buckets(t, column, edges, labels, title):
    groups = t.groupby(pd.cut(t[column], edges, labels=labels), observed=True).net_r
    lines = [f"  {title}:"]
    for name, r in groups:
        lines.append(f"    {name:20} {len(r):6}   win {(r > 0).mean():6.1%}   avg {r.mean():+.2f}R   total {r.sum():+8.1f}R")
    return lines


def summarize(t: pd.DataFrame, daily, start, end, label) -> str:
    out = [f"SWING BACKTEST ({label}) {start} to {end}", "=" * 72]
    if not len(t):
        return "\n".join(out + ["No setups found."]) + "\n"
    out.append(f"Named shapes found: {len(t):,} (" + ", ".join(f"{k} {v:,}" for k, v in t.setup.value_counts().items()) + ")")
    main = one_at_a_time(t[t.kunal_market])
    no_market = one_at_a_time(t[t.kunal])
    out += ["", "MAIN RULE: shape + all five questions + with the market, one trade per stock at a time",
            "(R per trade; 'net' = after estimated slippage; PF = profit factor = won R / lost R)",
            _line("Main rule", main),
            _line("  same, best case on unclear breakout days", main, "best_case_net_r"),
            _line("  same, double slippage", main, "net_r_2x_slippage")]
    out += [_line(f"  {name}", g) for name, g in main.groupby("setup")]
    out += [_line("  longs", main[main.direction == "long"]), _line("  shorts", main[main.direction == "short"])]
    out += [_line(f"  {m}", g) for m, g in main.groupby(main.date.str[:7])]
    if len(main):
        out += ["", f"  Average days held {main.days_held.mean():.1f}; stop distance {main.risk_pct.mean():.1f}% of the "
                f"price; slippage {main.slippage_r.mean():.2f}R a trade",
                f"  Unclear breakout days (low also hit the stop): {main.unclear_entry.sum()} of {len(main)};"
                f" stop and 3R on the same later day: {main.unclear_day.sum()}",
                "  How trades ended (first exit / last exit):"]
        out += [f"    {k:30} {v:5}" for k, v in main.first_exit.value_counts().items()]
        out += ["    ---"] + [f"    {k:30} {v:5}" for k, v in main.last_exit.value_counts().items()]
        gain, dd, taken, qqq, qqq_dd = account(main, daily, start, end)
        out += ["", "REALISTIC ACCOUNT (max 5 positions, 1% risk each, max 20% of the account per stock):",
                f"  {taken} of {len(main)} main-rule trades fit. Account {gain:+.1f}% (worst drop {dd:.1f}%)."
                f"  Holding QQQ instead: {qqq:+.1f}% (worst drop {qqq_dd:.1f}%)."]
    out += ["", "WITHOUT THE MARKET SWITCH (all five questions only):", _line("All", no_market),
            _line("  with the market", no_market[no_market.market]), _line("  against the market", no_market[~no_market.market])]
    out += ["", "EACH QUESTION ON ITS OWN (every named shape; overlapping trades allowed):",
            _line("Every named shape, no checks", t)]
    for c in CHECKS:
        out.append(_line(f"  {c}: yes", t[t[c]]) + "\n" + _line(f"  {c}: no", t[~t[c]]))
    if len(main) >= 30:
        out += ["", "MAIN-RULE TRADES BY GROUP (development only; learning, not choosing)"]
        dev = main[main.date < HOLDOUT_FROM]
        out += _buckets(dev, "risk_pct", [0, 2, 4, 6, 10, 1e9], ["under 2%", "2-4%", "4-6%", "6-10%", "10%+"], "Stop distance")
        out += _buckets(dev, "juice_x", [0, 3, 6, 10, 1e9], ["2-3x", "3-6x", "6-10x", "10x+"], "Last move vs risk (juice)")
        out += _buckets(dev, "price", [0, 10, 20, 50, 100, 1e9], ["$5-10", "$10-20", "$20-50", "$50-100", "$100+"], "Share price")
        out += _buckets(dev, "dollar_volume_m", [0, 20, 100, 500, 1e9], ["under $20M", "$20-100M", "$100-500M", "$500M+"], "Daily $ traded")
        out += _buckets(dev, "atr_pct", [0, 2, 3, 5, 1e9], ["under 2%", "2-3%", "3-5%", "5%+"], "Daily range (ATR %)")
        out += _buckets(dev, "breakout_volume_x", [0, 1, 2, 4, 1e9], ["under 1x", "1-2x", "2-4x", "4x+"],
                        "Breakout-day volume vs normal (known only after the close: NOT usable for entry)")
        out += [_line(f"  stacked 9>20>50>200: {k}", g) for k, g in dev.groupby("stacked")]
    out += ["", "Notes: daily candles only, worst case when the order of events in a day is unclear. Stocks that",
            "no longer trade are missing (survivorship bias: longs look a bit better than reality). No earnings",
            "dates, so some trades hold through earnings (Kunal sells before). Slippage is an estimate."]
    return "\n".join(out) + "\n"


def main():
    keep_pc_awake(True)
    parser = argparse.ArgumentParser(description="Swing backtest (see the notes at the top of this file)")
    parser.add_argument("--start", default="2024-07-01")
    parser.add_argument("--end", default="2025-06-30")
    parser.add_argument("--label", default="")
    parser.add_argument("--history-from", default="", help="first month of candles to load (default: 15 months before start)")
    parser.add_argument("--fetch", action="store_true", help="download missing daily candles first (after 4:05 PM)")
    parser.add_argument("--entry", choices=["line", "close"], default="line", help="line = buy-stop at the line; close = "
                        "buy at the close on a confirmed breakout (closed past the line on 2x+ volume)")
    parser.add_argument("--trail", choices=["intraday", "close"], default="intraday", help="intraday = stop order under "
                        "the 9 EMA; close = sell at the close of a day that closes past the 9 EMA")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    begin = date.fromisoformat(args.history_from) if args.history_from else start - timedelta(days=455)
    label = args.label or f"{start}_{end}"
    daily = load_daily(begin, end + timedelta(days=120), args.fetch)   # +120 days so late trades can finish
    settings = SwingSettings(entry_mode=args.entry, trail_mode=args.trail)
    print(f"Entry: {settings.entry_mode}; trailing exit: {settings.trail_mode}", flush=True)
    trades = run(daily, str(start), str(end), settings, Slippage())
    OUT.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUT / f"{label}_setups.csv", index=False)
    report = summarize(trades, daily, str(start), str(end), label)
    (OUT / f"{label}_summary.txt").write_text(report, encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    sys.exit(main())
