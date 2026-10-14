"""
Experiment (rules fixed in DAILY_SCANNER_EXPERIMENT.md): the ORB and FPB development-year day trades,
kept only when Kunal's daily chart agreed that morning, with ONE change to the exit:
stop = one daily ATR from the entry, no target, out at 3:55 PM.
Reads saved trades and cached candles only, so it runs at any time (no downloads), except --fetch-news.

    .venv\\Scripts\\python.exe -X utf8 run_daily_scanner_experiment.py               # version A
    .venv\\Scripts\\python.exe -X utf8 run_daily_scanner_experiment.py --fetch-news  # after 4:05 PM: headlines
    .venv\\Scripts\\python.exe -X utf8 run_daily_scanner_experiment.py --news        # version B (news only)
Writes logs/daily_scanner/<label>_trades.csv and _summary.txt.
"""
import argparse
import glob
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import alpaca_history as hist
from swing_strategy import Candles, SwingSettings, daily_setup_ready

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "logs" / "daily_scanner"
NEWS = hist.CACHE_DIR / "news" / "headlines.csv"
NA = dict(keep_default_na=False, na_values=[""])
SOURCES = {"ORB": (ROOT / "logs/orb_trades/dev_2024-07_2025-06_trades.csv", "time", "entry"),
           "FPB": (ROOT / "logs/fpb_backtest_alpaca/dev_2024-07_2025-06_trades.csv", "entry_time", "entry_fill")}
ENTRY_PCT, STOP_PCT, MARKET_PCT, CENTS = 0.05, 0.20, 0.05, 0.01          # same cost model as before


def load_trades() -> pd.DataFrame:
    frames = []
    for name, (path, time_col, entry_col) in SOURCES.items():
        t = pd.read_csv(path, **NA)
        t = t[t.net_r.notna()].copy()
        frames.append(pd.DataFrame(dict(strategy=name, date=t.date, symbol=t.symbol, direction=t.direction.str.lower(),
                                        entry_time=t[time_col], entry=t[entry_col], atr_pct=t.atr_pct,
                                        old_gross_r=t.gross_r, old_net_r=t.net_r)))
    return pd.concat(frames, ignore_index=True)


def add_daily_chart(trades: pd.DataFrame) -> pd.DataFrame:
    """Did Kunal's daily chart agree with each trade that morning? (swing_strategy.daily_setup_ready)"""
    wanted = set(trades.symbol) | {"QQQ"}
    parts = []
    for f in sorted(glob.glob(str(hist.CACHE_DIR / "1Day_many" / "*.csv.gz"))):
        d = pd.read_csv(f, **NA)
        parts.append(d[d.symbol.isin(wanted)])
    daily = pd.concat(parts).drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"])
    q = daily[daily.symbol == "QQQ"].set_index("date").close
    market_up = (q > q.rolling(50).mean()).shift(1)
    candles, s = {sym: Candles(g) for sym, g in daily.groupby("symbol")}, SwingSettings()
    shapes, agrees = [], []
    for r in trades.itertuples():
        a = candles.get(r.symbol)
        t = int(np.searchsorted(a.dates, r.date)) if a is not None else -1
        if a is None or t >= len(a) or a.dates[t] != r.date:
            shapes.append(None)
            agrees.append(False)
            continue
        up = market_up.get(r.date)
        result = daily_setup_ready(a, t, s, r.direction == "long", None if pd.isna(up) else bool(up))
        shapes.append(result["shape"])
        agrees.append(result["agrees"])
    return trades.assign(daily_shape=shapes, daily_agrees=agrees)


_bars = {}


def day_bars(symbol: str, day: str) -> pd.DataFrame | None:
    """Cached 5-minute candles of one regular session (None if not on disk; nothing is downloaded here)."""
    key = (symbol, day[:7])
    if key not in _bars:
        y, m = int(day[:4]), int(day[5:7])
        path = hist._month_path("5Min", symbol, y, m)
        _bars[key] = hist.regular_hours(hist._read(path)) if path.exists() else None
    month = _bars[key]
    if month is None:
        return None
    bars = month[month.index.strftime("%Y-%m-%d") == day]
    return bars if len(bars) else None


def daily_atr_trade(r, bars: pd.DataFrame) -> dict:
    """The new exit: stop one daily ATR away, out at 3:55 PM. Worst case if the entry candle touched the stop."""
    side = 1 if r.direction == "long" else -1
    risk = r.entry * r.atr_pct / 100
    stop = r.entry - side * risk
    times = bars.index.strftime("%H:%M")
    start = int(np.searchsorted(times, r.entry_time, side="right")) - 1     # the candle the entry happened in
    exit_price, why, when = None, "", ""
    for i in range(max(start, 0), len(bars)):
        if times[i] >= "15:55":
            exit_price, why, when = bars.open.iloc[i], "3:55 PM", times[i]
            break
        if i > start and side * (bars.open.iloc[i] - stop) <= 0:
            exit_price, why, when = bars.open.iloc[i], "stop (gap)", times[i]
            break
        extreme = bars.low.iloc[i] if side > 0 else bars.high.iloc[i]
        if side * (extreme - stop) <= 0:
            exit_price, why, when = stop, "stop", times[i]
            break
    if exit_price is None:                                   # no 3:55 candle (early close): last close
        exit_price, why, when = bars.close.iloc[-1], "close", times[-1]
    cost = r.entry * ENTRY_PCT / 100 + CENTS + exit_price * (STOP_PCT if why == "stop" else MARKET_PCT) / 100 + CENTS
    gross = side * (exit_price - r.entry) / risk
    return dict(new_exit=why, exit_time=when, exit_price=exit_price, new_gross_r=gross,
                new_net_r=gross - cost / risk, move_pct=side * (exit_price - r.entry) / r.entry * 100,
                cost_pct=cost / r.entry * 100)


def fetch_news(trades: pd.DataFrame):
    """Alpaca news headlines between 4 PM the day before and 9:30 AM, for each kept trade (after 4:05 PM only)."""
    hist.check_download_allowed()
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    import os
    client = NewsClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
    done = pd.read_csv(NEWS, **NA) if NEWS.exists() else pd.DataFrame(columns=["symbol", "date", "headlines", "first"])
    have = set(zip(done.symbol, done.date))
    rows = []
    todo = sorted({(r.symbol, r.date) for r in trades.itertuples()} - have)
    for n, (symbol, day) in enumerate(todo, 1):
        d = date.fromisoformat(day)
        start = datetime.combine(d - timedelta(days=4 if d.weekday() == 0 else 1), datetime.min.time()).replace(
            hour=16, tzinfo=hist.ET)
        end = datetime.combine(d, datetime.min.time()).replace(hour=9, minute=30, tzinfo=hist.ET)
        hist._wait_turn()
        try:
            news = client.get_news(NewsRequest(symbols=symbol, start=start, end=end, limit=50)).data.get("news", [])
        except Exception as e:                               # keep going; a later run retries what's missing
            print(f"  news for {symbol} {day} failed: {e}")
            continue
        news = [x for x in news if symbol in (x.symbols or [])]
        rows.append(dict(symbol=symbol, date=day, headlines=len(news), first=news[0].headline if news else ""))
        if n % 100 == 0:
            print(f"  headlines {n}/{len(todo)}", flush=True)
    NEWS.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([done, pd.DataFrame(rows)]).to_csv(NEWS, index=False)
    print(f"Headlines saved for {len(rows)} stock-days ({NEWS})")


def _line(name, x, col):
    if not len(x):
        return f"  {name:44} no trades"
    months = x.groupby(x.date.str[:7])[col].sum()
    gross = col.replace("net", "gross")
    return (f"  {name:44} {len(x):5} trades  win {(x[col] > 0).mean():5.1%}  {x[gross].mean():+.2f}R before costs"
            f" / {x[col].mean():+.2f}R after  months up {(months > 0).sum()}/{len(months)}")


def summarize(t: pd.DataFrame, label: str) -> str:
    out = [f"DAILY-CHART DAY TRADE EXPERIMENT ({label}), development year Jul 2024 - Jun 2025", "=" * 72,
           "Pass mark (fixed beforehand): at least +0.10R a trade after costs AND at least 7 of 12 months up."]
    for name, g in t.groupby("strategy"):
        months = g.groupby(g.date.str[:7]).new_net_r.sum()
        passed = g.new_net_r.mean() >= 0.10 and (months > 0).sum() >= 7
        out += ["", f"{name} entries, daily chart agreed: {len(g)} trades",
                _line("Old exits (tight intraday stop)", g, "old_net_r"),
                _line("NEW: 1 daily ATR stop, out at 3:55 PM", g, "new_net_r"),
                _line("  longs", g[g.direction == "long"], "new_net_r"),
                _line("  shorts", g[g.direction == "short"], "new_net_r"),
                f"  In % of the price: average move {g.move_pct.mean():+.2f}% vs costs {g.cost_pct.mean():.2f}% a trade;"
                f" stop {g.atr_pct.mean():.1f}% away",
                "  Exits: " + ", ".join(f"{k} {v}" for k, v in g.new_exit.value_counts().items()),
                f"  VERDICT: {'PASSES the development-year mark' if passed else 'FAILS the pass mark'}"]
        out += [f"    {m}: {v:+6.1f}R" for m, v in months.items()]
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Daily-chart day trade experiment (see DAILY_SCANNER_EXPERIMENT.md)")
    parser.add_argument("--news", action="store_true", help="version B: only stock-days with a headline before the open")
    parser.add_argument("--fetch-news", action="store_true", help="download the headlines first (after 4:05 PM)")
    args = parser.parse_args()
    trades = add_daily_chart(load_trades())
    kept = trades[trades.daily_agrees].copy()
    print(f"{len(trades):,} day trades; the daily chart agreed with {len(kept):,}", flush=True)
    if args.fetch_news:
        fetch_news(kept)
    label = "B_news" if args.news else "A"
    if args.news:
        news = pd.read_csv(NEWS, **NA)
        kept = kept.merge(news[["symbol", "date", "headlines", "first"]], on=["symbol", "date"], how="left")
        missing = kept.headlines.isna().sum()
        if missing:
            print(f"  ({missing} trades have no headline data yet: run --fetch-news after 4:05 PM)")
        kept = kept[kept.headlines.fillna(0) > 0]
    rows, missing = [], 0
    for r in kept.itertuples():
        bars = day_bars(r.symbol, r.date)
        if bars is None:
            missing += 1
            continue
        rows.append(dict(r._asdict(), **daily_atr_trade(r, bars)))
    result = pd.DataFrame(rows).drop(columns=["Index"])
    print(f"  replayed {len(result):,} trades on 5-minute candles ({missing} without cached candles)")
    OUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT / f"{label}_trades.csv", index=False)
    report = summarize(result, label)
    (OUT / f"{label}_summary.txt").write_text(report, encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    sys.exit(main())
