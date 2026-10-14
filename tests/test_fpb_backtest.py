"""
Offline checks of the FPB backtest's live-style exits (run_fpb_backtest_alpaca.py). No internet.
The entry rules are the live fpb_strategy.py functions themselves, so they are not re-tested here.

    .venv\\Scripts\\python.exe -X utf8 tests\\test_fpb_backtest.py
"""
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run_fpb_backtest_alpaca as fpb  # noqa: E402

ET = ZoneInfo("America/New_York")
DAY = "2025-05-27"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("  PASS " if ok else "  FAIL ") + name + (f"  ({detail})" if detail else ""))


def minute_path(points):
    """1-minute candles moving in straight lines between (time, price) points."""
    rows, index = [], []
    for (t0, p0), (t1, p1) in zip(points, points[1:]):
        start, end = pd.Timestamp(f"{DAY} {t0}", tz=ET), pd.Timestamp(f"{DAY} {t1}", tz=ET)
        steps = int((end - start) / pd.Timedelta(minutes=1))
        for i in range(steps):
            o, c = p0 + (p1 - p0) * i / steps, p0 + (p1 - p0) * (i + 1) / steps
            rows.append((o, max(o, c) + 0.01, min(o, c) - 0.01, c, 1000))
            index.append(start + pd.Timedelta(minutes=i))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=pd.DatetimeIndex(index))


def play(points, direction="LONG", entry=50.0, stop=49.0, ema=49.0):
    minutes = minute_path(points)
    ema9 = pd.Series(ema, index=pd.date_range(f"{DAY} 09:30", f"{DAY} 15:55", freq="5min", tz=ET))
    side = 1 if direction == "LONG" else -1
    risk = abs(entry - stop)
    r1, r2 = entry + side * 1.5 * risk, entry + side * 3 * risk
    return fpb.simulate_live_exits(direction, entry, minutes.index[0], stop, r1, r2, risk, minutes, ema9)


print("\nLive-style FPB exits")
check("live settings are read from fpb_paper_trader.py",
      (fpb.LIVE.TARGET_R1, fpb.LIVE.TARGET_R2, fpb.LIVE.EOD_EXIT_TIME, fpb.LIVE.MAX_POSITIONS) == (1.5, 3.0, "15:55", 3))

exits, r = play([("10:00", 50.0), ("10:10", 48.5), ("10:30", 48.5)])
check("falls to the stop: -1R", [e[3] for e in exits] == ["stop"] and abs(r + 1) < 1e-9, (exits, r))

exits, r = play([("10:00", 50.0), ("10:05", 51.6), ("10:15", 49.8), ("10:30", 49.8)], ema=40.0)
check("1.5R: half sold, then the stop at the entry price (+0.75R)",
      [e[3] for e in exits] == ["R1 (1.5R): half sold", "breakeven stop"] and abs(r - 0.75) < 1e-9, (exits, r))

exits, r = play([("10:00", 50.0), ("10:20", 53.2), ("10:30", 53.2)], ema=40.0)
check("then 3R: the rest sold (+2.25R)", [e[3] for e in exits] == ["R1 (1.5R): half sold", "R2 (3R)"]
      and abs(r - 2.25) < 1e-9, (exits, r))

exits, r = play([("10:00", 50.0), ("10:05", 51.6), ("15:58", 51.7)], ema=40.0)
check("nothing else hit: the rest sold at 3:55 PM", exits[-1][3] == "3:55 PM exit"
      and exits[-1][0].strftime("%H:%M") == "15:55", exits)

exits, r = play([("10:00", 50.0), ("10:05", 51.6), ("10:30", 52.5), ("10:40", 50.6), ("11:00", 50.6)], ema=50.5)
trail = [e for e in exits if e[3] == "trailing stop"]
check("after 1.5R the stop follows the 9 EMA and catches the drop above breakeven",
      len(trail) == 1 and trail[0][1] > 50.0 and trail[0][0].strftime("%H:%M") > "10:30" and r > 0.75, (exits, r))

exits, r = play([("10:00", 50.0), ("10:05", 51.6), ("10:30", 51.6)], ema=52.0)
check("like live: if the 9 EMA is above the price at 1.5R, the rest is sold at once",
      [e[3] for e in exits] == ["R1 (1.5R): half sold", "trailing stop"] and exits[0][0] == exits[1][0], exits)

exits, r = play([("10:00", 50.0), ("10:10", 51.6), ("10:30", 51.6)], direction="SHORT", stop=51.0)
check("short: stop above the entry, -1R", [e[3] for e in exits] == ["stop"] and abs(r + 1) < 1e-9, (exits, r))

cost = fpb.slippage_r(50.0, [(None, 49.0, 1.0, "stop")], 1.0, fpb.Slippage())
check("slippage: market entry + stop exit", abs(cost - (50 * 0.0005 + 0.01 + 49 * 0.002 + 0.01)) < 1e-9, cost)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
