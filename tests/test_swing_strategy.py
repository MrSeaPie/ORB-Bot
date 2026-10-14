"""
Offline checks of the swing rules (swing_strategy.py) on made-up daily candles. No internet.

    .venv\\Scripts\\python.exe -X utf8 tests\\test_swing_strategy.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orb_strategy import Slippage  # noqa: E402
from swing_strategy import Candles, SwingSettings, find_setups, simulate, slippage_r  # noqa: E402

S = SwingSettings()
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("  PASS " if ok else "  FAIL ") + name + (f"  ({detail})" if detail else ""))


def candles(closes, volumes=None, spread=0.01, opens=None, highs=None, lows=None):
    """Daily candles: each day opens at yesterday's close and ranges +-spread around its close."""
    closes = np.asarray(closes, float)
    o = np.r_[closes[0], closes[:-1]] if opens is None else np.asarray(opens, float)
    h = np.maximum(o, closes) * (1 + spread) if highs is None else np.asarray(highs, float)
    lo = np.minimum(o, closes) * (1 - spread) if lows is None else np.asarray(lows, float)
    v = np.full(len(closes), 2e6) if volumes is None else np.asarray(volumes, float)
    dates = pd.bdate_range("2024-01-02", periods=len(closes)).strftime("%Y-%m-%d")
    return pd.DataFrame(dict(date=dates, open=o, high=h, low=lo, close=closes, volume=v))


def flag_chart(flag_days=9, breakout=True):
    """80 quiet up-days, a 4-day pole of about +16% on heavy volume, a tight flag, then the breakout day."""
    base = list(np.linspace(40, 50, 80))
    pole = [52, 54.5, 56.5, 58.0]
    flag = [57.9, 57.6, 57.9, 57.7, 58.0, 57.8, 58.0, 57.9, 58.1, 58.0][:flag_days]
    closes = base + pole + flag + ([59.5] if breakout else [57.6])
    vol = [2e6] * 80 + [6e6] * 4 + [1.5e6] * flag_days + [5e6]
    df = candles(closes, vol, spread=0.015)
    top = df.high[80:84].max()
    last = 84 + flag_days - (0 if breakout else -1)          # without a breakout the last day stays under too
    df.loc[84:last - 1, "high"] = np.minimum(df.high[84:last], top - 0.05)
    df.loc[84 + flag_days - 1, "high"] = top                 # the last flag day tests the top: a flat line
    return df


print("\nPattern shapes")
df = flag_chart()
a = Candles(df)
found = [x for x in find_setups(a, S, np.ones(len(a), bool)) if x["t"] == len(a) - 1]
flag = found[0] if found else {}
check("a pole + 9 quiet days + a break of the top is a flag", flag.get("setup") == "flag", found)
check("entry one cent above the flag top", abs(flag.get("entry", 0) - (df.high[80:84].max() + 0.01)) < 1e-9)
check("stop = yesterday's 9 EMA minus 0.1 ATR",
      abs(flag.get("stop", 0) - (a.ema9[-2] - 0.1 * a.atr[-2])) < 1e-9)
check("all five questions pass on a clean flag", flag.get("kunal_market"),
      {k: flag.get(k) for k in ("liquid", "no_distribution", "ema_tight", "ema_sloped", "bone_zone", "juice", "not_tired", "market")})

slope = flag_chart()
top = slope.high[80:84].max()
slope.loc[84:92, "high"] = top - 0.3 - 0.12 * np.arange(9)          # flag highs stepping down: a sloped line
slope.loc[93, ["open", "high", "close"]] = [57.3, 57.6, 57.5]        # breaks the sloped line, still under the top
join = max((slope.high[i] - top) / (i - 83) for i in range(84, 93))  # the line from the top over every flag high
x = [s for s in find_setups(Candles(slope), S) if s["t"] == 93]
check("a flag sloping down: the line connects the highs, entry under the flag's top",
      x and x[0]["setup"] == "flag" and abs(x[0]["entry"] - (top + join * 10 + 0.01)) < 1e-9 and x[0]["entry"] < top - 1,
      x and (round(x[0]["entry"], 3), round(top + join * 10, 3), round(top, 3)))

a2 = Candles(flag_chart(breakout=False))
check("no break of the top, no signal", not [x for x in find_setups(a2, S) if x["t"] == len(a2) - 1])
a3 = Candles(flag_chart(flag_days=2))
check("a 2-day pause is too short to be a flag", not [x for x in find_setups(a3, S) if x["t"] == len(a3) - 1
                                                     and "flag" in x["setup"]])

dist = flag_chart()
dist.loc[len(dist) - 3, ["close", "volume"]] = [57.5, 4e6]           # red day 2.7x the green days, 2 days before
x = [s for s in find_setups(Candles(dist), S) if s["t"] == len(dist) - 1]
check("heaviest day of the week before was a down day: distribution flagged",
      x and x[0]["no_distribution"] is False, x and x[0]["no_distribution"])

bear = flag_chart()
for col in ("open", "high", "low", "close"):
    bear[col] = 3000 / bear[col]                                     # upside down, keeping % moves
bear[["high", "low"]] = bear[["low", "high"]].to_numpy()
b = Candles(bear)
x = [s for s in find_setups(b, S, np.zeros(len(b), bool)) if s["t"] == len(b) - 1]
check("the mirror image is a bear flag (short), stop = 9 EMA + 0.5 ATR",
      x and x[0]["setup"] == "bear flag" and x[0]["direction"] == "short"
      and abs(x[0]["stop"] - (b.ema9[-2] + 0.5 * b.atr[-2])) < 1e-9, x and (x[0]["setup"], x[0]["stop"]))
check("a short needs the market below its 50-day: market check", x and x[0]["market"] is True)



def flat_chart(test_days=(62, 70, 78)):
    """Run-up to ~59, then 4 weeks under a ceiling of 59.95 touched on `test_days`, then a break to 60.8."""
    up = list(np.linspace(40, 58, 60))
    wave = [56, 57.5, 58.9, 58, 56.5, 55.5, 55, 55.5, 56.5, 57.5, 58.9, 58, 56.5, 55.5, 55, 56, 57, 58.0, 58.9,
            58.2, 57.4, 57, 57.4, 58, 58.3, 58.5, 58.6, 58.7]
    df = candles(up + wave + [60.8], spread=0.005)
    df.loc[60:87, "high"] = np.minimum(df.high[60:88], 59.0)
    df.loc[list(test_days), "high"] = 59.95
    return df


f = Candles(flat_chart())
x = [s for s in find_setups(f, S) if s["t"] == len(f) - 1]
check("3 tests of a ceiling over 25+ days, then a break: flat top",
      x and "flat top" in x[0]["setup"] and x[0]["tests"] == 3, x and (x[0]["setup"], x[0]["tests"]))
two = Candles(flat_chart((62, 78)))
x = [s for s in find_setups(two, S) if s["t"] == len(two) - 1 and "flat top" in s["setup"]]
check("only 2 tests: not a flat top (3 touches needed)", not x, x and x[0]["tests"])

tired = flag_chart()
y = len(tired) - 1
tired.loc[y - 3:y - 1, "close"] = [57.95, 58.05, 58.15]                  # 3 up closes in a row before the break
x = [s for s in find_setups(Candles(tired), S) if s["t"] == y]
check("3 up days in a row into the breakout: 'tired' flagged", x and x[0]["not_tired"] is False,
      x and x[0]["not_tired"])


from swing_strategy import daily_setup_ready  # noqa: E402

ready_chart = flag_chart(breakout=False)
r = daily_setup_ready(Candles(ready_chart), len(ready_chart) - 1, S, True, market_up=True)
check("daily scanner: a finished flag counts as ready that morning, before any break", r["shape"] == "flag"
      and r["agrees"], r)
r = daily_setup_ready(Candles(ready_chart), len(ready_chart) - 1, S, True, market_up=False)
check("daily scanner: market below its 50-day -> doesn't agree with a long", r["shape"] == "flag" and not r["agrees"], r)
c_ready = Candles(ready_chart)
before = (c_ready.h.copy(), c_ready.l.copy())
daily_setup_ready(c_ready, len(ready_chart) - 1, S, True, market_up=True)
check("daily scanner leaves the candles unchanged", (c_ready.h == before[0]).all() and (c_ready.l == before[1]).all())

print("\nThe trade (simulate)")


def trade_chart(path, ema, atr=1.0, opens=None):
    """Day 0 = breakout day (entry 50, stop 49 -> 1R = $1); later days follow `path` of (high, low, close)."""
    rows = [(50.5, 49.6, 50.3)] + path
    df = candles([r[2] for r in rows], highs=[r[0] for r in rows], lows=[r[1] for r in rows],
                 opens=opens or [50.0] + [r[2] for r in rows[:-1]])
    c = Candles(df)
    c.ema9[:] = ema
    c.atr[:] = atr
    return c, dict(t=0, direction="long", entry=50.0, entry_at_open=False, stop=49.0, risk=1.0)


c, setup = trade_chart([(50.4, 48.8, 49.0)], ema=49.1)
r = simulate(c, setup, S)
check("next day trades below the stop: -1R", r["last_exit"] == "stop" and abs(r["gross_r"] + 1) < 1e-9, r["exits"])

c, setup = trade_chart([(50.2, 48.0, 48.2)], ema=49.1, opens=[50.0, 48.5])
r = simulate(c, setup, S)
check("opens below the stop: out at the open, worse than -1R", r["last_exit"] == "gap through stop"
      and abs(r["gross_r"] + 1.5) < 1e-9, r["exits"])

c, setup = trade_chart([(51.5, 50.2, 51.4), (53.2, 51.3, 53.0), (54.0, 52.8, 53.8), (53.9, 51.0, 51.2)],
                       ema=[49.5, 50.0, 51.0, 52.0, 52.5])
r = simulate(c, setup, S)
check("3R reached: half sold at 53, the rest trailed under the 9 EMA",
      [e[3] for e in r["exits"]] == ["3R: half sold", "trailing stop"]
      and abs(r["exits"][1][1] - (52.0 - 0.1)) < 1e-9
      and abs(r["gross_r"] - (0.5 * 3 + 0.5 * 1.9)) < 1e-9, r["exits"])

c, setup = trade_chart([(53.2, 51.0, 52.0), (52.5, 49.9, 50.1)], ema=[49.0, 49.4, 49.6])
r = simulate(c, setup, S)
check("after the half sale the stop is at least the entry price (breakeven)",
      [e[3] for e in r["exits"]] == ["3R: half sold", "breakeven stop"] and abs(r["gross_r"] - 1.5) < 1e-9, r["exits"])

c, setup = trade_chart([(51.0, 50.1, 50.8)], ema=49.1)
c.l[0] = 48.9                                                          # breakout day low under the stop
worst, best = simulate(c, setup, S), simulate(c, setup, S, worst_case_entry_day=False)
check("breakout-day low under the stop: worst case = -1R and marked unclear",
      worst["first_exit"] == "stop (breakout day)" and worst["unclear_entry"] and abs(worst["gross_r"] + 1) < 1e-9)
check("best case ignores it (the low came before the breakout)", best["first_exit"] != "stop (breakout day)"
      and best["unclear_entry"])

short = dict(t=0, direction="short", entry=50.0, entry_at_open=False, stop=51.0, risk=1.0)
c, _ = trade_chart([(51.2, 49.5, 51.1)], ema=50.8)
r = simulate(c, short, S)
check("short: price above the stop next day: -1R", r["last_exit"] == "stop" and abs(r["gross_r"] + 1) < 1e-9, r["exits"])

print("\nOther readings: buy at the close on volume, exit on a close past the 9 EMA")
from dataclasses import replace  # noqa: E402

CLOSE = replace(S, entry_mode="close")
df = flag_chart()
a = Candles(df)
x = [s_ for s_ in find_setups(a, CLOSE) if s_["t"] == len(a) - 1]
check("closed above the line on 2x+ volume: bought at the close, stop under today's 9 EMA",
      x and x[0]["entry"] == df.close.iloc[-1] and x[0]["entry_at_close"]
      and abs(x[0]["stop"] - (a.ema9[-1] - 0.1 * a.atr[-1])) < 1e-9, x and (x[0]["entry"], x[0]["stop"]))
quiet = flag_chart()
quiet.loc[len(quiet) - 1, "volume"] = 3e6                             # only ~1.3x normal volume
check("not on 2x volume: no end-of-day entry", not [s_ for s_ in find_setups(Candles(quiet), CLOSE)
                                                     if s_["t"] == len(quiet) - 1])
c, setup = trade_chart([(50.2, 48.8, 49.0)], ema=49.1)
r = simulate(c, dict(setup, entry_at_close=True), CLOSE)
check("bought at the close: the breakout day itself can't stop it out (starts the next day)",
      r["exits"][0][0] == 1, r["exits"])
c, setup = trade_chart([(51.5, 50.2, 51.4), (51.6, 50.0, 50.3), (50.6, 49.5, 49.6)], ema=[49.5, 50.5, 50.6, 50.7])
r = simulate(c, setup, replace(S, trail_mode="close"))
check("close-basis exit: a dip under the 9 EMA during the day is ignored, a close under it sells at the close",
      [e[3] for e in r["exits"]] == ["closed past the 9 EMA"] and r["exits"][0][0] == 2 and r["exits"][0][1] == 50.3,
      r["exits"])

slip = Slippage()
c, setup = trade_chart([(50.4, 48.8, 49.0)], ema=49.1)
r = simulate(c, setup, S)
cost = slippage_r(setup, r, slip)
check("slippage: stop-order entry + stop exit", abs(cost - (50 * 0.002 + 0.01 + 49 * 0.002 + 0.01)) < 1e-9, cost)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
