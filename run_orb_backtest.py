"""
ORB backtest: the ORB rules (orb_strategy.py) over many past days, on the stocks ORB's own finder
(orb_stock_finder.py) would have listed each morning, with slippage. Separate from FPB: no FPB file
is used or changed.

    .venv\\Scripts\\python.exe -X utf8 run_orb_backtest.py                       # 2024-01-02 to 2026-09-30
    .venv\\Scripts\\python.exe -X utf8 run_orb_backtest.py --start 2025-05-01 --end 2025-05-30 --label pilot
    (--per-day 10 keeps only the first 10 of each morning's list; default 0 = every candidate)

Writes to logs/orb_trades/:
  <label>_decisions.csv  every stock on every morning list: traded, skipped (and why), or no setup
  <label>_trades.csv     every trade: entry, stop, exits, result in R before and after slippage
  <label>_summary.txt    the report (also printed)
Results are in R: 1R = what one trade risks (at 1% risk, about $65 on a $6,500 account).
Two periods: "development" (before 2025-07) may be used to choose between options; "holdout"
(2025-07 on) only confirms them, so settings fitted to the same data can't fool us.

Downloads refuse to run on weekdays 9:15 AM-4:05 PM New York time (the live FPB bot shares the
Alpaca keys). If that happens mid-run, the results so far are saved; a later run continues quickly
because everything downloaded is kept on disk.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

import alpaca_history as hist
from orb_stock_finder import FinderSettings, candidates_for_day, daily_features
from orb_strategy import DayContext, OrbSettings, Slippage, find_orb, simulate_trade

HOLDOUT_FROM = "2025-07-01"
OUT = Path(__file__).resolve().parent / "logs" / "orb_trades"


def months_between(start: date, end: date):
    first = date(start.year, start.month, 1)
    while first <= end:
        after = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
        yield first, min(after - timedelta(days=1), end)
        first = after


def load_daily(start: date, end: date, finder: FinderSettings):
    """Daily candles for every stock that was ever liquid enough, from ~5 months before `start`."""
    assets = hist.get_assets()
    symbols = assets.symbol.tolist() + ["QQQ"]
    begin = start - timedelta(days=150)                  # enough history for the 50-day average
    print(f"Daily candles for {len(symbols):,} stocks, {begin} to {end} (downloaded once, then read from disk)...",
          flush=True)
    liquid, floor = {"QQQ"}, 0.7 * min(finder.min_avg_volume, finder.gapper_min_avg_volume)
    for first, last in months_between(begin, end):        # pass 1: which stocks are ever busy enough
        month = hist.get_daily_many(symbols, first, last)
        mean_volume = month.groupby("symbol").volume.mean()
        liquid |= set(mean_volume[mean_volume >= floor].index)
    frames = [m[m.symbol.isin(liquid)] for m in            # pass 2: keep only those (from disk)
              (hist.get_daily_many(symbols, first, last) for first, last in months_between(begin, end))]
    daily = pd.concat(frames).sort_values(["symbol", "date"]).reset_index(drop=True)
    print(f"  {len(liquid):,} stocks were liquid at some point", flush=True)
    return assets, daily


def signal_for(c, day: date, qqq: pd.DataFrame, shortable: set, rules: OrbSettings):
    """One stock on one morning's list -> (decision row, signal, day context, 5-minute candles)."""
    row = {"date": str(day), "symbol": c.symbol, "rank": int(c["rank"]), "source": c.source, "list_side": c.side,
           "gap_pct": round(c.gap_pct, 2), "atr_pct": round(c.atr_pct, 2),
           "rel_volume": round(c.rel_volume, 2), "avg_volume": int(c.avg_volume), "trend": int(c.trend),
           "up_days": int(c.up_days)}
    extended = hist.get_bars(c.symbol, day, day, "5Min")          # includes pre-market candles
    five = hist.regular_hours(extended)
    if len(five) < 3:
        return {**row, "status": "none", "reasons": "no intraday candles"}, None, None, None
    scale = five.open.iloc[0] / c.open        # split-adjusted daily prices -> prices as traded that day
    normal_volume = c.avg_volume / scale      # shares a day, in that day's share count
    premarket = extended[extended.index < five.index[0]].volume.sum()
    row.update(price=round(five.open.iloc[0], 2), dollar_volume_m=round(normal_volume * five.open.iloc[0] / 1e6, 1),
               premarket_volume=int(premarket), premarket_ratio=round(premarket / normal_volume, 4),
               # first 10 minutes (candles 1-2): known by 9:40, the earliest entry, so no peeking ahead
               early_volume_ratio=round(five.volume.iloc[:2].sum() / normal_volume, 4))
    ctx = DayContext(prev_close=c.prev_close * scale, prev_high=c.prev_high * scale,
                     prev_low=c.prev_low * scale, atr_pct=c.atr_pct, qqq=qqq)
    sig = find_orb(five, ctx, rules)
    reasons, status = list(sig.reasons), sig.status
    if status == "trade":
        if c.side and sig.direction != c.side:
            reasons.append(f"{c.source} list is for {c.side}s")
        if sig.direction == "short" and c.symbol not in shortable:
            reasons.append("can't be shorted (Alpaca's list today)")
        status = "skip" if reasons else "trade"
    row.update(status=status, direction=sig.direction, candle=sig.candle,
               time=f"{sig.time:%H:%M}" if sig.time is not None else "", entry=round(sig.entry, 4),
               stop=round(sig.stop, 4), risk_pct=round(sig.risk / sig.entry * 100, 2) if sig.entry else 0,
               reasons="; ".join(reasons))
    return row, sig, ctx, five


def play(row, sig, ctx, five, day: date, rules: OrbSettings, slip: Slippage):
    """Play a trade minute by minute -> trade row with the result before and after slippage."""
    minutes = hist.get_morning_minutes(row["symbol"], day)
    # 9 EMA warm-up: start it at yesterday's close, as a chart that runs on from the day before would
    closes5 = pd.concat([pd.Series([ctx.prev_close], index=[five.index[0] - pd.Timedelta(minutes=5)]), five.close])
    result = simulate_trade(sig, minutes, closes5, rules)
    cost = slip.r(sig, result)
    return {**row, "exits": " | ".join(f"{t:%H:%M} {p:.2f} x{f:g} {why}" for t, p, f, why in result.exits),
            "first_exit": result.exits[0][3] if result.exits else "", "last_exit": result.exits[-1][3] if result.exits else "",
            "gross_r": result.r, "slippage_r": round(cost, 3), "net_r": round(result.r - cost, 3),
            "net_r_2x_slippage": round(result.r - 2 * cost, 3)}


def _progress(what):
    return lambda done, total: print(f"  {what}: {done:,}/{total:,} downloaded", flush=True)


def run(start: date, end: date, label: str, finder: FinderSettings, rules: OrbSettings, slip: Slippage):
    decisions, trades, stopped = [], [], ""
    try:
        assets, daily = load_daily(start, end, finder)
        shortable = set(assets[assets.shortable].symbol)
        features = daily_features(daily)
        days = sorted(d for d in features[features.symbol == "QQQ"].date if str(start) <= d <= str(end))
        features = features[features.date.isin(days) & (features.symbol != "QQQ")]
        by_day = {d: rows for d, rows in features.groupby("date")}
        lists = {d: candidates_for_day(by_day.get(d, features.head(0)), finder) for d in days}
        print(f"{len(days)} trading days, {sum(len(x) for x in lists.values()):,} stock-days on the morning lists. "
              "Working month by month (each finished month is kept even if the run is stopped)...", flush=True)
        for month in sorted({d[:7] for d in days}):
            month_days = [d for d in days if d.startswith(month)]
            pairs = [(s, date.fromisoformat(d)) for d in month_days for s in list(lists[d].symbol) + ["QQQ"]]
            hist.prefetch(pairs, "5Min", progress=_progress(f"{month} 5-minute"))
            pending = []                                 # step 1: the ORB decision for every listed stock
            for day_text in month_days:
                day = date.fromisoformat(day_text)
                qqq = hist.regular_hours(hist.get_bars("QQQ", day, day, "5Min"))
                for _, c in lists[day_text].iterrows():
                    try:
                        row, sig, ctx, five = signal_for(c, day, qqq, shortable, rules)
                    except hist.MarketHoursError:
                        raise
                    except Exception as error:          # one bad stock must not stop the run
                        row, sig = {"date": day_text, "symbol": c.symbol, "status": "error", "reasons": str(error)[:200]}, None
                    decisions.append(row)
                    if row["status"] == "trade":
                        pending.append((row, sig, ctx, five, day))
            hist.prefetch_mornings([(p[0]["symbol"], p[4]) for p in pending], progress=_progress(f"{month} 1-minute mornings"))
            month_r = 0.0
            for row, sig, ctx, five, day in pending:    # step 2: play each trade minute by minute
                try:
                    trades.append(play(row, sig, ctx, five, day, rules, slip))
                    month_r += trades[-1]["net_r"]
                except hist.MarketHoursError:
                    raise
                except Exception as error:
                    row.update(status="error", reasons=f"playing the trade: {str(error)[:150]}")
            total = sum(t["net_r"] for t in trades)
            print(f"{month}: {sum(len(lists[d]) for d in month_days):,} stock-days, {len(pending)} trades, "
                  f"{month_r:+.1f}R net this month, {total:+.1f}R so far", flush=True)
    except hist.MarketHoursError as error:
        stopped = f"STOPPED EARLY: {error} Run it again after the close to finish."
        print(stopped, flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    decisions, trades = pd.DataFrame(decisions), pd.DataFrame(trades)
    decisions.to_csv(OUT / f"{label}_decisions.csv", index=False)
    trades.to_csv(OUT / f"{label}_trades.csv", index=False)
    report = summarize(decisions, trades, start, end, finder, stopped)
    (OUT / f"{label}_summary.txt").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Saved: {OUT / (label + '_summary.txt')} (+ _trades.csv, _decisions.csv)")


def _line(name, t):
    if not len(t):
        return f"  {name:30} no trades"
    losses = -t.net_r[t.net_r < 0].sum()
    pf = t.net_r[t.net_r > 0].sum() / losses if losses else float("inf")
    return (f"  {name:30} {len(t):5} trades   win {(t.net_r > 0).mean():6.1%}   avg {t.gross_r.mean():+.2f}R gross"
            f" / {t.net_r.mean():+.2f}R net   total {t.net_r.sum():+8.1f}R   profit factor {pf:.2f}")


def _buckets(t, column, edges, labels, title):
    if column not in t:
        return []
    groups = t.groupby(pd.cut(t[column], edges, labels=labels), observed=True).net_r
    lines = [f"  {title}:"]
    for name, r in groups:
        lines.append(f"    {name:18} {len(r):5}   win {(r > 0).mean():6.1%}   avg {r.mean():+.2f}R   total {r.sum():+8.1f}R")
    return lines


def summarize(decisions, trades, start, end, finder, stopped=""):
    out = [f"ORB BACKTEST {start} to {end}", "=" * 60]
    if stopped:
        out.append(stopped)
    cap = f"up to {finder.per_day} stocks a day" if finder.per_day else "every candidate (research mode)"
    out.append(f"Morning lists: {cap}; {len(decisions):,} stock-days looked at.")
    if len(decisions):
        counts = decisions.status.value_counts()
        out.append("Decisions: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()))
    if not len(trades):
        out.append("No trades.")
        return "\n".join(out) + "\n"
    t = trades.sort_values(["date", "time"]).reset_index(drop=True)
    curve = t.net_r.cumsum()
    out += ["", "RESULTS (R per trade; 'net' = after estimated slippage; win = net result above 0)",
            _line("All trades", t),
            _line("  development (to 2025-06)", t[t.date < HOLDOUT_FROM]),
            _line("  holdout (2025-07 on)", t[t.date >= HOLDOUT_FROM]),
            _line("Longs", t[t.direction == "long"]), _line("Shorts", t[t.direction == "short"]),
            _line("Gappers", t[t.source == "gapper"]), _line("Yesterday's movers", t[t.source == "mover"]),
            _line("Go-to stocks", t[t.source == "go-to"]),
            _line("Ranked 1-6 on the list", t[t["rank"] <= 6]), _line("Ranked 7 or lower", t[t["rank"] > 6])]
    out += [_line(f"Year {y}", t[t.date.str[:4] == y]) for y in sorted(t.date.str[:4].unique())]
    out += ["", f"With double slippage: total {t.net_r_2x_slippage.sum():+.1f}R, avg {t.net_r_2x_slippage.mean():+.2f}R",
            f"Worst losing streak (biggest drop from a high, net): {(curve.cummax() - curve).max():.1f}R",
            f"Trades per day: average {t.groupby('date').size().mean():.1f}, most on one day {t.groupby('date').size().max()}",
            f"Average stop distance: {t.risk_pct.mean():.2f}% of the price",
            "", "How trades ended (first exit / last exit):"]
    out += [f"  {k:32} {v:5}" for k, v in t.first_exit.value_counts().items()]
    out += ["  ---"] + [f"  {k:32} {v:5}" for k, v in t.last_exit.value_counts().items()]
    dev = t[t.date < HOLDOUT_FROM]
    if len(dev):
        out += ["", "WHICH STOCKS DOES ORB WORK ON? (development period only; this picks the ranking later)",
                "  trades / win rate / average net R / total net R per group"]
        out += _buckets(dev, "gap_pct", [-1e9, -10, -3, 3, 10, 1e9],
                        ["gap down 10%+", "gap down 3-10%", "no big gap", "gap up 3-10%", "gap up 10%+"], "Gap at the open")
        out += _buckets(dev, "price", [0, 5, 10, 20, 50, 100, 1e9],
                        ["under $5", "$5-10", "$10-20", "$20-50", "$50-100", "$100+"], "Share price")
        out += _buckets(dev, "dollar_volume_m", [0, 10, 50, 200, 1e9],
                        ["under $10M", "$10-50M", "$50-200M", "$200M+"], "Normal daily trading ($ a day)")
        out += _buckets(dev, "premarket_volume", [-1, 50_000, 200_000, 1_000_000, 1e12],
                        ["under 50k", "50k-200k", "200k-1M", "1M+"], "Pre-market volume (shares; Kunal: 50k+)")
        out += _buckets(dev, "early_volume_ratio", [-1, 0.05, 0.10, 0.20, 1e9],
                        ["under 5%", "5-10%", "10-20%", "20%+"], "First 10 minutes' volume vs a normal day")
        out += _buckets(dev, "atr_pct", [0, 3, 5, 8, 1e9], ["2-3%", "3-5%", "5-8%", "8%+"], "Daily range (ATR)")
    skipped = decisions[decisions.status == "skip"].reasons.str.split("; ").explode()
    if len(skipped):
        out += ["", "Why breakouts were skipped (a stock can have several reasons):"]
        grouped = skipped.str.replace(r"\(.*\)", "(...)", regex=True).str.replace(r"[+-]?\d+(\.\d+)?%", "x%", regex=True)
        out += [f"  {k[:60]:62} {v:6,}" for k, v in grouped.value_counts().head(12).items()]
    out += ["", "Notes: stocks that no longer exist are missing (survivorship bias: results look a bit better",
            "than reality). Slippage is an estimate. In research mode every candidate is traded, far more",
            "than one account could; the point is to learn which kinds of stocks ORB works on. At 1% risk",
            "per trade, the total in R is roughly the % gained or lost, before the 50% size cap shrinks some trades."]
    return "\n".join(out) + "\n"


def keep_pc_awake(on: bool) -> bool:
    """
    Ask Windows not to idle-sleep while the backtest runs (same request as the FPB bot; the screen
    can still turn off). Ends by itself when the script exits. Returns True if Windows agreed.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
        return ctypes.windll.kernel32.SetThreadExecutionState(flags) != 0
    except Exception:
        return False


def main():
    keep_pc_awake(True)
    parser = argparse.ArgumentParser(description="ORB backtest (see the notes at the top of this file)")
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default="2026-09-30")
    parser.add_argument("--label", default="")
    parser.add_argument("--per-day", type=int, default=FinderSettings.per_day, help="0 = every candidate")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    finder = FinderSettings(per_day=args.per_day)
    run(start, end, args.label or f"{start}_{end}", finder, OrbSettings(), Slippage())


if __name__ == "__main__":
    sys.exit(main())
