"""
Kunal's daily-chart swing setups (SWING_RULES.md) as plain functions on daily candles.

    candles = Candles(df)                      the moving averages, ATR and streaks the rules need
    find_setups(candles, settings, market_up)  every flag / flat top / bear flag / flat bottom break,
                                               with each of Kunal's five questions as a yes/no column
    simulate(candles, setup, settings)         how the trade ends: stop under the 9 EMA, half at 3R,
                                               the rest trailed under the 9 EMA

Day t is judged only from candles up to day t-1; day t itself only supplies the entry (a buy-stop
order one cent past the line fills when the price crosses it, or at the open if it opens past it).
Separate strategy: no FPB or ORB rule is used or changed here.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SwingSettings:
    # which stocks [Kunal scan 76/78]
    min_price: float = 5.0
    min_avg_volume: float = 1_000_000
    # flags [Kunal 74, 77]
    pole_min_pct: float = 10.0
    pole_max_days: int = 10
    flag_min_days: int = 3
    flag_max_days: int = 10
    flag_max_giveback: float = 0.5       # [Proposed] the flag stays in the upper half of the pole
    # flat tops / flat bottoms [Kunal 74, 77, 78]
    base_lookback: int = 120             # [Proposed] the line = highest high of ~6 months (his charts: not a year)
    base_min_history: int = 60           # [Project] days of history needed before a ceiling counts
    base_min_days: int = 20              # at least a month of resting
    min_tests: int = 3                   # three touches of the line or more [Kunal 74, 77, 78]
    test_tolerance_atr: float = 0.5      # [Proposed] a test = a peak within 0.5 ATR of the ceiling
    prior_trend_pct: float = 20.0        # [Proposed] rose 20%+ in the 60 days before the base
    prior_trend_days: int = 60
    base_max_depth_pct: float = 35.0     # [Proposed]
    # the five questions
    max_ema_gap_atr: float = 2.0         # [Proposed] 9 EMA close under the line: at most 2 ATR below it (his charts: 1.0-1.7)
    min_juice: float = 2.0               # [Kunal 77] the last move at least 2x the risk
    max_streak: int = 2                  # 3 green days in a row into the breakout = tired [Kunal 77, 78]
    distribution_days: int = 5           # the week before the breakout [Kunal 74, 77, 78]
    distribution_ratio: float = 1.5      # [Proposed] heaviest red day > 1.5x the heaviest green day
    # stops and exits [Kunal 74, 77]
    long_buffer_atr: float = 0.1         # [Proposed] small cushion under the 9 EMA
    short_buffer_atr: float = 0.5        # [Kunal 74] shorts: half to a full day's ATR above the 9 EMA
    first_target_r: float = 3.0          # [Kunal 77] about 3:1 -> sell half, stop to the buy price
    first_sale: float = 0.5
    tick: float = 0.01
    # two other readings of the course, tested side by side (SWING_RULES.md section 6b)
    entry_mode: str = "line"             # "line": buy-stop at the line during the day [Kunal 74];
                                         # "close": buy at the close if it closed past the line on 2x+ volume [Kunal 78, 74/77]
    confirm_volume_x: float = 2.0        # [Kunal 74, 77] he wants volume 2:1 or more on a breakout
    trail_mode: str = "intraday"         # "intraday": stop order under the 9 EMA, raised each evening;
                                         # "close": sell at the close of a day that closes past the 9 EMA


class Candles:
    """Daily candles of one stock (oldest first) as numpy arrays, plus Kunal's chart lines."""

    def __init__(self, df: pd.DataFrame, base_lookback: int = SwingSettings.base_lookback):
        df = df.reset_index(drop=True)
        close, prev = df.close.astype(float), df.close.astype(float).shift(1)
        self.dates = df.date.astype(str).to_numpy()
        self.o, self.h, self.l, self.c = (df[k].astype(float).to_numpy() for k in ("open", "high", "low", "close"))
        self.v = df.volume.astype(float).to_numpy()
        self.ema9 = close.ewm(span=9, adjust=False).mean().to_numpy()
        self.sma20, self.sma50, self.sma200 = (close.rolling(n).mean().to_numpy() for n in (20, 50, 200))
        true_range = pd.concat([df.high - df.low, (df.high - prev).abs(), (df.low - prev).abs()], axis=1).max(axis=1)
        self.atr = true_range.rolling(10).mean().to_numpy()              # ATR(10), as on Kunal's charts
        self.avg_volume = df.volume.astype(float).rolling(50, min_periods=20).mean().to_numpy()
        up, down = (close > prev).to_numpy(), (close < prev).to_numpy()
        self.up_streak, self.down_streak = _streak(up), _streak(down)    # days in a row ending that day
        h, l = df.high.astype(float), df.low.astype(float)
        self.base_high = h.rolling(base_lookback, min_periods=1).max().shift(1).to_numpy()
        self.base_low = l.rolling(base_lookback, min_periods=1).min().shift(1).to_numpy()

    def __len__(self):
        return len(self.c)


def _streak(flags: np.ndarray) -> np.ndarray:
    out, run = np.zeros(len(flags), dtype=int), 0
    for i, f in enumerate(flags):
        run = run + 1 if f else 0
        out[i] = run
    return out


# ---------------------------------------------------------------- pattern shapes (question 1)

def _flag(a: Candles, t: int, s: SwingSettings, long: bool):
    """
    Bull flag (long) / bear flag (short) breaking on day t.
    The line is drawn the way Kunal connects the dots: from the flag's highest high (lowest low for
    shorts) through the later highs, so it is flat or slopes down (up for shorts) and every flag day
    sits under it. The flag starts on the first day that came within 0.5 ATR of that top.
    """
    side = 1 if long else -1
    first = t - (s.flag_max_days + 1)
    if first - s.pole_max_days < 1:
        return None
    ext, other = (a.h, a.l) if long else (a.l, a.h)          # the flag's top side / bottom side
    seg = side * ext[first:t]
    peak = first + len(seg) - 1 - int(np.argmax(seg[::-1]))   # the last day at the flag's extreme
    top = ext[peak]
    start = first + int(np.argmax(seg >= side * top - s.test_tolerance_atr * a.atr[t - 1]))
    days = t - 1 - start
    if not s.flag_min_days <= days <= s.flag_max_days:
        return None
    if (side * ext[start - s.pole_max_days:start] > side * top).any():
        return None                                           # the pole's top came earlier: not a 3-10 day flag
    slope = max((side * (ext[i] - top) / (i - peak) for i in range(peak + 1, t)), default=0.0)
    line = top + side * slope * (t - peak)
    if not side * (ext[t] - line) > 0:
        return None                                           # today doesn't cross the line
    pole_day = start - s.pole_max_days + int(np.argmin(side * other[start - s.pole_max_days:start]))
    pole_base = other[pole_day]
    move = side * (top - pole_base)
    if move < s.pole_min_pct / 100 * pole_base:
        return None
    flag = slice(start + 1, t)
    worst = other[flag][int(np.argmin(side * other[flag]))]  # the flag's lowest low (highest high for shorts)
    if side * (worst - (top - side * s.flag_max_giveback * move)) < 0:
        return None
    if a.v[t - 3:t].mean() >= a.v[pole_day + 1:start + 1].mean():  # volume dies down before the break
        return None
    return dict(setup="flag" if long else "bear flag", direction="long" if long else "short", level=line,
                move=move, days=days, tests=np.nan, depth_pct=abs(top - worst) / max(top, worst) * 100)


def _count_tests(near_days) -> int:
    """Separate visits to the line: days near it in a row count once; a day away from it starts a new test."""
    return int(len(near_days) and 1 + np.count_nonzero(np.diff(near_days) > 1))


def _base(a: Candles, t: int, s: SwingSettings, long: bool):
    """
    Flat top (long) / flat bottom (short) breaking on day t: the price clears the highest high (lowest
    low) of the last base_lookback days after testing that line 3+ times over a month or more.
    """
    side = 1 if long else -1
    line = a.base_high[t] if long else a.base_low[t]
    if t < s.base_min_history or not side * ((a.h[t] if long else a.l[t]) - line) > 0:
        return None
    ext, other = (a.h, a.l) if long else (a.l, a.h)
    begin = max(0, t - s.base_lookback)
    near = np.nonzero(side * ext[begin:t] >= side * line - s.test_tolerance_atr * a.atr[t - 1])[0] + begin
    start = near[0]
    if t - start < s.base_min_days:
        return None
    tests = _count_tests(near)
    if tests < s.min_tests:
        return None
    before = other[max(0, start - s.prior_trend_days):start + 1]
    before = before.min() if long else before.max()
    worst = other[start:t].min() if long else other[start:t].max()
    depth = abs(line - worst) / max(line, worst) * 100
    move = side * (line - before)
    if move < s.prior_trend_pct / 100 * before or depth > s.base_max_depth_pct:
        return None
    return dict(setup="flat top" if long else "flat bottom", direction="long" if long else "short", level=line,
                move=move, days=t - start, tests=tests, depth_pct=depth)


SHAPES = (lambda a, t, s: _flag(a, t, s, True), lambda a, t, s: _base(a, t, s, True),
          lambda a, t, s: _flag(a, t, s, False), lambda a, t, s: _base(a, t, s, False))


# ---------------------------------------------------------------- entry, stop and the five questions

def _entry_and_checks(a: Candles, t: int, shape: dict, s: SwingSettings, market_up) -> dict | None:
    long = shape["direction"] == "long"
    side, y = (1 if long else -1), t - 1
    level = shape["level"]
    buffer = s.long_buffer_atr if long else s.short_buffer_atr
    if s.entry_mode == "close":                              # confirmation: closed past the line on heavy volume
        if not (side * (a.c[t] - level) > 0 and a.v[t] >= s.confirm_volume_x * a.avg_volume[y]):
            return None
        at_open, entry, stop = False, a.c[t], a.ema9[t] - side * buffer * a.atr[t]
    else:
        at_open = a.o[t] > level if long else a.o[t] < level
        entry = a.o[t] if at_open else level + side * s.tick
        stop = a.ema9[y] - side * buffer * a.atr[y]
    risk = side * (entry - stop)
    if not risk > 0 or not np.isfinite(risk):
        return None                                          # the 9 EMA is on the wrong side: no order possible
    gap_atr = side * (level - a.ema9[y]) / a.atr[y]
    week = np.arange(t - s.distribution_days, t)
    up_days = a.c[week] > a.c[week - 1]
    against, along = (week[~up_days], week[up_days]) if long else (week[up_days], week[~up_days])
    heavy_day_against = bool(len(against)) and a.v[against].max() > s.distribution_ratio * a.v[along].max(initial=0)
    stacked = (a.ema9[y] > a.sma20[y] > a.sma50[y] > a.sma200[y]) if long else \
              (a.ema9[y] < a.sma20[y] < a.sma50[y] < a.sma200[y])
    checks = dict(
        liquid=bool(a.c[y] >= s.min_price and a.avg_volume[y] >= s.min_avg_volume),                     # Q2
        no_distribution=not heavy_day_against,                                                          # Q2
        ema_tight=bool(0 <= gap_atr <= s.max_ema_gap_atr),                                               # Q3
        ema_sloped=bool(side * (a.ema9[y] - a.ema9[y - 1]) > 0),                                          # Q3
        bone_zone=bool(side * (a.ema9[y] - a.sma20[y]) > 0),                                              # Q4
        juice=bool(shape["move"] >= s.min_juice * risk),                                                  # Q5
        not_tired=bool((a.up_streak[y] if long else a.down_streak[y]) <= s.max_streak),
        market=bool(market_up == long) if market_up is not None else False,
    )
    return dict(shape, t=t, date=a.dates[t], entry=entry, entry_at_open=bool(at_open),
                entry_at_close=s.entry_mode == "close", stop=stop, risk=risk,
                risk_pct=risk / entry * 100, price=a.c[y], avg_volume=a.avg_volume[y],
                dollar_volume_m=a.c[y] * a.avg_volume[y] / 1e6, atr_pct=a.atr[y] / a.c[y] * 100,
                ema_gap_atr=gap_atr, juice_x=shape["move"] / risk, stacked=bool(stacked),
                breakout_volume_x=a.v[t] / a.avg_volume[y], **checks,
                kunal=all(v for k, v in checks.items() if k != "market"),
                kunal_market=all(checks.values()))


def find_setups(a: Candles, s: SwingSettings, market_up=None, first_day: int = 0) -> list[dict]:
    """
    Every day from `first_day` on where one of the four shapes breaks, with Kunal's checks attached.
    market_up[t] = QQQ closed above its 50-day average on day t-1 (None = unknown).
    If two shapes break the same day in the same direction, the one whose line is crossed first is kept.
    """
    found = []
    for t in range(max(first_day, s.flag_max_days + s.pole_max_days + 2, 2), len(a)):
        if not a.atr[t - 1] > 0 or not np.isfinite(a.ema9[t - 2]):
            continue
        by_side = {}
        for shape_of in SHAPES:
            shape = shape_of(a, t, s)
            if shape is None:
                continue
            setup = _entry_and_checks(a, t, shape, s, None if market_up is None else market_up[t])
            if setup is not None:
                by_side.setdefault(setup["direction"], []).append(setup)
        for direction, setups in by_side.items():
            side = 1 if direction == "long" else -1
            first = min(setups, key=lambda x: side * x["entry"])          # the line the price crosses first
            found.append(dict(first, setup="+".join(sorted(x["setup"] for x in setups))))
    return found


def daily_setup_ready(a: Candles, t: int, s: SwingSettings, long: bool, market_up=None) -> dict:
    """
    Is one of the four shapes READY on the morning of day t (built from candles up to day t-1; the line
    doesn't have to break today)? For using the daily chart as a day-trade scanner [Kunal 77: the daily
    chart decides]. Returns {"shape": name or None, "agrees": shape + bone zone + market on the same side}.
    """
    if t < 30 or t >= len(a) or not a.atr[t - 1] > 0:
        return dict(shape=None, agrees=False)
    keep = a.h[t], a.l[t]
    if long:
        a.h[t] = np.inf                                      # pretend today crosses: only the shape is judged
    else:
        a.l[t] = -np.inf
    try:
        shape = _flag(a, t, s, long) or _base(a, t, s, long)
    finally:
        a.h[t], a.l[t] = keep
    side = 1 if long else -1
    zone = side * (a.ema9[t - 1] - a.sma20[t - 1]) > 0
    agrees = shape is not None and bool(zone) and market_up is not None and bool(market_up) == long
    return dict(shape=shape["setup"] if shape else None, agrees=agrees)


# ---------------------------------------------------------------- the trade

def simulate(a: Candles, setup: dict, s: SwingSettings, worst_case_entry_day: bool = True) -> dict:
    """
    Follow one trade day by day. Exits are (day index, price, fraction of the position, why).
    worst_case_entry_day: if the breakout day's low also reached the stop, count the stop (we can't tell
    from a daily candle whether the low came before or after the breakout). False = assume before.
    """
    t, long = setup["t"], setup["direction"] == "long"
    side, entry, stop = (1 if long else -1), setup["entry"], setup["stop"]
    risk, first_stop = setup["risk"], setup["stop"]
    target = entry + side * s.first_target_r * risk
    buffer = s.long_buffer_atr if long else s.short_buffer_atr
    exits, left, took = [], 1.0, False
    unclear_entry = unclear_day = False

    def stop_hit(i):
        return side * ((a.l[i] if long else a.h[i]) - stop) <= 0

    def target_hit(i):
        return side * ((a.h[i] if long else a.l[i]) - target) >= 0

    def stop_name():
        return "stop" if stop == first_stop else ("breakeven stop" if stop == entry else "trailing stop")

    at_close = setup.get("entry_at_close", False)
    for i in range(t + 1 if at_close else t, len(a)):
        if i == t:
            if stop_hit(i) and (setup["entry_at_open"] or worst_case_entry_day):
                unclear_entry = not setup["entry_at_open"]
                exits.append((i, stop, left, "stop (breakout day)"))
                left = 0
                break
            unclear_entry = stop_hit(i)
        else:
            if side * (a.o[i] - stop) <= 0:                      # opened past the stop
                exits.append((i, a.o[i], left, "gap through stop"))
                left = 0
                break
            if not took and side * (a.o[i] - target) >= 0:      # opened past the 3R target
                exits.append((i, a.o[i], s.first_sale, "3R (gap)"))
                left, took = left - s.first_sale, True
                stop = max(stop, entry) if long else min(stop, entry)
            if stop_hit(i):
                unclear_day |= (not took) and target_hit(i)      # both touched: count the stop (worst case)
                exits.append((i, stop, left, stop_name()))
                left = 0
                break
        if not took and target_hit(i):
            exits.append((i, target, s.first_sale, "3R: half sold"))
            left, took = left - s.first_sale, True
            stop = max(stop, entry) if long else min(stop, entry)
        if s.trail_mode == "close":                               # out at the close of a day past the 9 EMA
            if side * (a.c[i] - a.ema9[i]) < 0:
                exits.append((i, a.c[i], left, "closed past the 9 EMA"))
                left = 0
                break
            continue
        trail = a.ema9[i] - side * buffer * a.atr[i]              # evening: move the stop up to the 9 EMA
        stop = max(stop, trail) if long else min(stop, trail)
    if left > 1e-9:
        exits.append((len(a) - 1, a.c[-1], left, "still open (end of data)"))
    gross = sum(f * side * (p - entry) for _, p, f, _ in exits) / risk
    return dict(exits=exits, gross_r=gross, exit_day=exits[-1][0], exit_date=a.dates[exits[-1][0]],
                days_held=exits[-1][0] - t, first_exit=exits[0][3], last_exit=exits[-1][3],
                unclear_entry=unclear_entry, unclear_day=unclear_day)


def slippage_r(setup: dict, result: dict, slip, times: float = 1.0) -> float:
    """
    Trading costs of one trade in R (orb_strategy.Slippage numbers): entries at the line and stop exits
    are stop orders (stop_pct), fills at the open are market orders (market_pct), 3R sales are limit orders.
    """
    pct = slip.market_pct if setup["entry_at_open"] or setup.get("entry_at_close") else slip.stop_pct
    cost = setup["entry"] * pct / 100 + slip.cents
    for _, price, fraction, why in result["exits"]:
        if why.startswith("3R:"):
            cost += fraction * slip.cents
        else:
            pct = slip.stop_pct if ("stop" in why and "gap" not in why) else slip.market_pct
            cost += fraction * (price * pct / 100 + slip.cents)
    return cost * times / setup["risk"]
