"""
FPB backtest on Alpaca history: the LIVE FPB rules, unchanged, on many past days and stocks.

What is tested is what the live bot does (nothing in the FPB files is changed; they are only read):
  entry   fpb_strategy.FirstPullbackBuy: prepare_data, check_initial_spike (3%+ gap, 2%+ spike),
          find_pullback_entry (pullback to the 9/20 EMA within 6 candles, confirmation candle),
          then a market order right after the signal candle closes (the live bot scans every
          5 minutes and acts on signals up to 10 minutes old). Skipped if the price is already past
          the stop, or for a short Alpaca won't allow.
  exits   as fpb_paper_trader.py: stop order at the signal's stop; half sold at 1.5R and the stop
          moved to the entry price; then the stop trails the 9 EMA (x0.998 for longs, x1.002 for
          shorts, updated every minute with the forming candle, like the live bot); the rest sold
          at 3R or at 3:55 PM. Settings are read from fpb_paper_trader.py itself.
Played minute by minute on 1-minute candles from 9:30 to 4:00. Within a minute the stop is checked
before the targets (the cautious choice).

Stocks: ORB's stock finder in gapper mode with the FPB scanner's own limits (gap 3%+, price
$5-$500, 500k+ shares a day; scanners/config.py), but every gapper, not just universe.txt. The report
also shows the live-like slices: only stocks in today's universe.txt, and only the first 3 entries
a day (MAX_POSITIONS).

    .venv\\Scripts\\python.exe -X utf8 run_fpb_backtest_alpaca.py                      # 2024-07 .. 2025-06
    .venv\\Scripts\\python.exe -X utf8 run_fpb_backtest_alpaca.py --start 2025-05-01 --end 2025-05-30 --label pilot

Writes logs/fpb_backtest_alpaca/<label>_summary.txt, _trades.csv and _decisions.csv.
Downloads refuse to run on weekdays 9:15 AM-4:05 PM (the live bot shares the keys); a stopped run
keeps its finished months, and running it again continues from the saved data.
"""
import argparse
import contextlib
import importlib.util
import io
import sys
from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd

import alpaca_history as hist
from fpb_strategy import FirstPullbackBuy, FPBConfig
from orb_stock_finder import FinderSettings, candidates_for_day, daily_features
from orb_strategy import Slippage
from run_orb_backtest import HOLDOUT_FROM, _buckets, _line, keep_pc_awake, load_daily

HERE = Path(__file__).resolve().parent
OUT = HERE / "logs" / "fpb_backtest_alpaca"


def _live_settings():
    """Read the live bot's settings from fpb_paper_trader.py (imported quietly, nothing is run)."""
    spec = importlib.util.spec_from_file_location("fpb_paper_trader_settings", HERE / "fpb_paper_trader.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    return module


LIVE = _live_settings()
EOD_EXIT = time.fromisoformat(LIVE.EOD_EXIT_TIME)          # 15:55
TRAIL = 0.002                                               # live: stop = 9 EMA x 0.998 / x 1.002
ALPHA = 2 / (9 + 1)                                         # 9 EMA weight of the newest price


def simulate_live_exits(direction, entry_fill, entry_time, stop, r1, r2, risk, minutes, ema9_done):
    """
    Play an FPB position the way fpb_paper_trader.py manages it, minute by minute.
    `ema9_done`: 9 EMA after each finished 5-minute candle (indexed by candle start).
    Returns (exits [(time, price, fraction, why)], gross R).
    """
    long = direction == "LONG"
    side, left, hit_r1, trailed, exits = (1 if long else -1), 1.0, False, False, []
    for when, m in minutes.loc[entry_time:].iterrows():
        if when.time() >= EOD_EXIT:
            exits.append((when, m.open, left, "3:55 PM exit"))
            left = 0
            break
        if (long and m.low <= stop) or (not long and m.high >= stop):          # the stop order at Alpaca
            gapped = (long and m.open < stop) or (not long and m.open > stop)
            why = "trailing stop" if trailed else ("breakeven stop" if hit_r1 else "stop")
            exits.append((when, m.open if gapped else stop, left, why))
            left = 0
            break
        if not hit_r1 and ((long and m.high >= r1) or (not long and m.low <= r1)):
            exits.append((when, r1, 0.5, f"R1 ({LIVE.TARGET_R1:g}R): half sold"))
            left, hit_r1, stop = left - 0.5, True, entry_fill
        if hit_r1 and ((long and m.high >= r2) or (not long and m.low <= r2)):
            exits.append((when, r2, left, f"R2 ({LIVE.TARGET_R2:g}R)"))
            left = 0
            break
        if hit_r1 and LIVE.USE_EMA_TRAIL:
            done = ema9_done.loc[:when.floor("5min") - pd.Timedelta(minutes=5)]
            if len(done):
                live_ema = done.iloc[-1] * (1 - ALPHA) + m.close * ALPHA        # EMA with the forming candle
                new_stop = live_ema * (1 - TRAIL) if long else live_ema * (1 + TRAIL)
                if (long and new_stop > stop) or (not long and new_stop < stop):
                    stop, trailed = new_stop, True
                    if (long and m.close <= stop) or (not long and m.close >= stop):
                        exits.append((when, m.close, left, "trailing stop"))
                        left = 0
                        break
    if left > 1e-9 and len(minutes):
        exits.append((minutes.index[-1], minutes.close.iloc[-1], left, "end of data"))
    gross = sum(f * side * (p - entry_fill) for _, p, f, _ in exits) / risk if exits else 0.0
    return exits, round(gross, 3)


def slippage_r(entry_fill, exits, risk, slip: Slippage, times=1.0):
    """Slippage in R: entry and target/time exits are market orders; stops are stop orders."""
    cost = entry_fill * slip.market_pct / 100 + slip.cents
    for _, price, fraction, why in exits:
        pct = slip.stop_pct if "stop" in why else slip.market_pct
        cost += fraction * (price * pct / 100 + slip.cents)
    return cost * times / risk


def fpb_decision(c, day: date, strategy: FirstPullbackBuy, shortable: set, universe: set):
    """One gapper on one day -> (decision row, entry details or None)."""
    row = {"date": str(day), "symbol": c.symbol, "gap_pct_daily": round(c.gap_pct, 2), "atr_pct": round(c.atr_pct, 2),
           "avg_volume": int(c.avg_volume), "rel_volume": round(c.rel_volume, 2), "trend": int(c.trend),
           "in_universe": c.symbol in universe}
    bars = hist.get_bars(c.symbol, day - timedelta(days=6), day, "5Min")
    rth = hist.regular_hours(bars)
    today_ext = bars[bars.index.date == day]
    today_rth = rth[rth.index.date == day]
    if len(today_rth) < 3 or len(rth[rth.index.date < day]) == 0:
        return {**row, "status": "none", "reasons": "not enough candles"}, None
    scale = today_rth.open.iloc[0] / c.open                # split-adjusted daily -> prices as traded that day
    prev_close = c.prev_close * scale
    normal_volume = c.avg_volume / scale
    premarket = today_ext[today_ext.index < today_rth.index[0]].volume.sum()
    row.update(price=round(today_rth.open.iloc[0], 2), dollar_volume_m=round(normal_volume * today_rth.open.iloc[0] / 1e6, 1),
               premarket_volume=int(premarket), early_volume_ratio=round(today_rth.volume.iloc[:2].sum() / normal_volume, 4))
    df = strategy.prepare_data(rth)                        # EMAs run on from the days before, as live
    today = df[df.index.date == day]
    had_spike, direction = strategy.check_initial_spike(today, prev_close)
    row["gap_pct"] = round((today.open.iloc[0] / prev_close - 1) * 100, 2)
    if not had_spike:
        return {**row, "status": "none", "reasons": "no 3% gap with a 2% spike"}, None
    signal = strategy.find_pullback_entry(today, direction, today.high.iloc[:3].max(), today.low.iloc[:3].min())
    row["direction"] = direction.lower()
    if signal is None:
        return {**row, "status": "none", "reasons": "no pullback entry in the first 6 candles"}, None
    entry_time = pd.Timestamp(signal["entry_time"]) + pd.Timedelta(minutes=5)       # right after the candle closes
    row.update(signal_time=f"{pd.Timestamp(signal['entry_time']):%H:%M}", entry_time=f"{entry_time:%H:%M}",
               ema_level=signal["ema_level"], signal_price=round(signal["entry_price"], 4),
               stop=round(signal["stop_price"], 4), risk_pct=round(signal["risk_per_share"] / signal["entry_price"] * 100, 2))
    reasons = []
    if direction == "SHORT" and (not LIVE.ALLOW_SHORTS or c.symbol not in shortable):
        reasons.append("can't be shorted (Alpaca's list today)")
    if entry_time.time() > time.fromisoformat(LIVE.SCAN_END_TIME):
        reasons.append("signal after the 11:00 scan window")
    if reasons:
        return {**row, "status": "skip", "reasons": "; ".join(reasons)}, None
    return {**row, "status": "signal", "reasons": ""}, (signal, entry_time, direction, df)


def play_fpb(row, details, day: date, slip: Slippage):
    """Enter at the market right after the signal candle and play the live exits. Updates `row`."""
    signal, entry_time, direction, df = details
    minutes = hist.get_minutes(row["symbol"], day, hist.SESSION)
    after = minutes.loc[entry_time:]
    if not len(after):
        row.update(status="skip", reasons="no trades after the signal")
        return None
    entry_fill = after.open.iloc[0]
    long = direction == "LONG"
    if (long and entry_fill <= signal["stop_price"]) or (not long and entry_fill >= signal["stop_price"]):
        row.update(status="skip", reasons="price already past the stop")
        return None
    exits, gross = simulate_live_exits(direction, entry_fill, after.index[0], signal["stop_price"],
                                       signal["target_r1"], signal["target_r2"], signal["risk_per_share"],
                                       minutes, df.ema9[df.index.date == day])
    cost = slippage_r(entry_fill, exits, signal["risk_per_share"], slip)
    row.update(status="trade", entry_fill=round(entry_fill, 4))
    return {**row, "exits": " | ".join(f"{t:%H:%M} {p:.2f} x{f:g} {w}" for t, p, f, w in exits),
            "first_exit": exits[0][3] if exits else "", "last_exit": exits[-1][3] if exits else "",
            "gross_r": gross, "slippage_r": round(cost, 3), "net_r": round(gross - cost, 3),
            "net_r_2x_slippage": round(gross - 2 * cost, 3)}


def run(start: date, end: date, label: str, slip: Slippage):
    finder = FinderSettings(gapper_min_avg_volume=500_000, gapper_min_price=5.0, min_atr_pct=0.0, max_goto=0)
    strategy = FirstPullbackBuy(FPBConfig(min_gap_pct=3.0, target_r1=LIVE.TARGET_R1, target_r2=LIVE.TARGET_R2))
    universe_file = HERE / "scanners" / "universe.txt"
    universe = {s.split("#")[0].strip().upper() for s in universe_file.read_text().splitlines() if s.split("#")[0].strip()}
    decisions, trades, stopped = [], [], ""
    try:
        assets, daily = load_daily(start, end, finder)
        shortable = set(assets[assets.shortable & assets.easy_to_borrow].symbol)
        features = daily_features(daily)
        days = sorted(d for d in features[features.symbol == "QQQ"].date if str(start) <= d <= str(end))
        features = features[features.date.isin(days) & (features.symbol != "QQQ")]
        by_day = {d: rows for d, rows in features.groupby("date")}
        lists = {}
        for d in days:
            listed = candidates_for_day(by_day.get(d, features.head(0)), finder)
            lists[d] = listed[(listed.source == "gapper") & (listed.open <= 500)]       # FPB scanner: $5-$500
        print(f"{len(days)} trading days, {sum(len(x) for x in lists.values()):,} gapper stock-days. "
              "Working month by month...", flush=True)
        for month in sorted({d[:7] for d in days}):
            month_days = [d for d in days if d.startswith(month)]
            pairs = [(s, date.fromisoformat(d) - timedelta(days=k)) for d in month_days
                     for s in lists[d].symbol for k in (0, 6)]                 # today + the days before (EMA warm-up)
            hist.prefetch(pairs, "5Min", progress=lambda n, t: print(f"  {month} 5-minute: {n:,}/{t:,}", flush=True))
            pending = []
            for d in month_days:
                day = date.fromisoformat(d)
                for _, c in lists[d].iterrows():
                    try:
                        row, details = fpb_decision(c, day, strategy, shortable, universe)
                    except hist.MarketHoursError:
                        raise
                    except Exception as error:
                        row, details = {"date": d, "symbol": c.symbol, "status": "error", "reasons": str(error)[:200]}, None
                    decisions.append(row)
                    if details:
                        pending.append((row, details, day))
            hist.prefetch_minutes([(p[0]["symbol"], p[2]) for p in pending], hist.SESSION,
                                  progress=lambda n, t: print(f"  {month} 1-minute days: {n:,}/{t:,}", flush=True))
            month_r = 0.0
            for row, details, day in pending:
                try:
                    trade = play_fpb(row, details, day, slip)
                except hist.MarketHoursError:
                    raise
                except Exception as error:
                    row.update(status="error", reasons=f"playing the trade: {str(error)[:150]}")
                    continue
                if trade:
                    trades.append(trade)
                    month_r += trade["net_r"]
            print(f"{month}: {sum(len(lists[d]) for d in month_days):,} gapper-days, "
                  f"{sum(1 for p in pending if p[0]['status'] == 'trade')} trades, {month_r:+.1f}R net, "
                  f"{sum(t['net_r'] for t in trades):+.1f}R so far", flush=True)
    except hist.MarketHoursError as error:
        stopped = f"STOPPED EARLY: {error} Run it again after the close to finish."
        print(stopped, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    decisions, trades = pd.DataFrame(decisions), pd.DataFrame(trades)
    decisions.to_csv(OUT / f"{label}_decisions.csv", index=False)
    trades.to_csv(OUT / f"{label}_trades.csv", index=False)
    report = summarize(decisions, trades, start, end, stopped)
    (OUT / f"{label}_summary.txt").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Saved: {OUT / (label + '_summary.txt')} (+ _trades.csv, _decisions.csv)")


def summarize(decisions, trades, start, end, stopped=""):
    out = [f"FPB BACKTEST (live rules, Alpaca history) {start} to {end}", "=" * 60]
    if stopped:
        out.append(stopped)
    out.append(f"{len(decisions):,} gapper stock-days looked at.")
    if len(decisions):
        out.append("Decisions: " + ", ".join(f"{k} {v:,}" for k, v in decisions.status.value_counts().items()))
    if not len(trades):
        return "\n".join(out + ["No trades."]) + "\n"
    t = trades.sort_values(["date", "entry_time"]).reset_index(drop=True)
    first3 = t.groupby("date").head(LIVE.MAX_POSITIONS)
    curve = t.net_r.cumsum()
    out += ["", "RESULTS (R per trade; 'net' = after estimated slippage; win = net result above 0)",
            _line("All trades", t),
            _line("  development (to 2025-06)", t[t.date < HOLDOUT_FROM]),
            _line("  holdout (2025-07 on)", t[t.date >= HOLDOUT_FROM]),
            _line("Longs", t[t.direction == "long"]), _line("Shorts", t[t.direction == "short"]),
            _line("Like live: stocks in universe.txt", t[t.in_universe]),
            _line(f"Like live: first {LIVE.MAX_POSITIONS} entries a day", first3),
            _line("Pulled back to the 9 EMA", t[t.ema_level == "EMA9"]),
            _line("Pulled back to the 20 EMA", t[t.ema_level == "EMA20"])]
    out += [_line(f"Year {y}", t[t.date.str[:4] == y]) for y in sorted(t.date.str[:4].unique())]
    out += ["", f"With double slippage: total {t.net_r_2x_slippage.sum():+.1f}R, avg {t.net_r_2x_slippage.mean():+.2f}R",
            f"Worst losing streak (biggest drop from a high, net): {(curve.cummax() - curve).max():.1f}R",
            f"Trades per day: average {t.groupby('date').size().mean():.1f}, most on one day {t.groupby('date').size().max()}",
            f"Average stop distance: {t.risk_pct.mean():.2f}% of the price", "", "How trades ended (first exit / last exit):"]
    out += [f"  {k:32} {v:6}" for k, v in t.first_exit.value_counts().items()]
    out += ["  ---"] + [f"  {k:32} {v:6}" for k, v in t.last_exit.value_counts().items()]
    dev = t[t.date < HOLDOUT_FROM]
    if len(dev):
        out += ["", "WHICH STOCKS DOES FPB WORK ON? (development period only)",
                "  trades / win rate / average net R / total net R per group"]
        out += _buckets(dev, "gap_pct", [-1e9, -10, -3, 3, 10, 1e9],
                        ["gap down 10%+", "gap down 3-10%", "(small gap)", "gap up 3-10%", "gap up 10%+"], "Gap at the open")
        out += _buckets(dev, "price", [0, 10, 20, 50, 100, 1e9], ["$5-10", "$10-20", "$20-50", "$50-100", "$100+"], "Share price")
        out += _buckets(dev, "premarket_volume", [-1, 100_000, 500_000, 2_000_000, 1e12],
                        ["under 100k", "100k-500k", "500k-2M", "2M+"], "Pre-market volume (FPB scanner wants 100k+)")
        out += _buckets(dev, "early_volume_ratio", [-1, 0.05, 0.10, 0.20, 1e9],
                        ["under 5%", "5-10%", "10-20%", "20%+"], "First 10 minutes' volume vs a normal day")
        out += _buckets(dev, "atr_pct", [0, 2, 3, 5, 8, 1e9], ["under 2%", "2-3%", "3-5%", "5-8%", "8%+"], "Daily range (ATR)")
        out += _buckets(dev, "risk_pct", [0, 0.5, 1, 2, 100], ["under 0.5%", "0.5-1%", "1-2%", "2%+"], "Stop distance (% of price)")
    skipped = decisions[decisions.status == "skip"].reasons.str.split("; ").explode()
    if len(skipped):
        out += ["", "Why signals were not traded:"] + [f"  {k:60} {v:6,}" for k, v in skipped.value_counts().head(8).items()]
    out += ["", "Notes: the live bot's rules are used as they are. Differences from live: entry at the minute",
            "after the signal candle closes (live scans every 5 minutes); every gapper is tested, not just",
            "today's 20-stock watchlist; the $500 daily loss limit and buying power are ignored. Stocks that no",
            "longer exist are missing (survivorship bias). Slippage is an estimate (FPB day 1 had $0.35-0.48 on stops)."]
    return "\n".join(out) + "\n"


def main():
    keep_pc_awake(True)
    parser = argparse.ArgumentParser(description="FPB backtest on Alpaca history (see the notes at the top)")
    parser.add_argument("--start", default="2024-07-01")
    parser.add_argument("--end", default="2025-06-30")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    run(start, end, args.label or f"{start}_{end}", Slippage())


if __name__ == "__main__":
    sys.exit(main())
