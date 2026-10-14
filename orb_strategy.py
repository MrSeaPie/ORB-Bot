"""
ORB (Opening Range Breakout) rules as code. What each rule is and where it comes from:
ORB_RULES.md (defaults confirmed by Hassan on 2026-10-13). ORB is separate from FPB: this file
does not use or change any FPB code.

Plain functions: no internet, no orders.
  find_orb()        looks at one stock's 5-minute candles for one day and says whether an ORB
                    trade triggered (when, at what price, with which stop) or why it was skipped
  simulate_trade()  plays a triggered trade forward on 1-minute candles: sell half at 3R and move
                    the stop to breakeven, the rest follows the 9 EMA, everything out by 11:30
  day_context()     yesterday's high/low/close and the daily ATR, from earlier 5-minute candles

Times are New York time. Candle numbers count from 1 = the 9:30-9:35 opening candle.
Results are in R (multiples of the risk per share), before slippage and fees.
"""
from dataclasses import dataclass, field
from datetime import time, timedelta

import pandas as pd


@dataclass
class OrbSettings:
    earliest_entry: time = time(9, 40)  # two candles finished, break during candle 3 [Kunal]
    last_entry: time = time(11, 0)      # no new ORB entries from 11:00 [Kunal]
    hard_exit: time = time(11, 30)      # sell whatever is left [Proposed]
    stop_buffer_pct: float = 0.1        # stop = VWAP minus (long) / plus (short) 0.1% [Proposed]
    max_vwap_share: float = 0.6         # skip if entry-to-VWAP > 60% of the opening range [Proposed]
    min_atr_pct: float = 2.0            # daily ATR must be 2%+ of the price [Kunal 71, Armando, his TKR chart]
    qqq_limit_pct: float = 0.5          # no longs if QQQ is down 0.5%+ since 9:30, no shorts if up [Proposed]
    news_gap_pct: float = 3.0           # ... but a stock gapping 3%+ (its own news) ignores QQQ [Kunal 72, Armando]
    gap_direction_pct: float = 1.0      # a gap this big sets the direction; smaller: candle 1 does [Proposed]
    clear_yesterday: bool = False       # option: long above yesterday's high, short below its low [Kunal 71]
    first_target_r: float = 3.0         # sell part at 3R [Kunal: 2-3R]
    first_sale: float = 0.5             # ... half the position [Kunal]
    ema_period: int = 9                 # the rest follows the 9 EMA [Kunal]
    tick: float = 0.01

    @classmethod
    def pattern_only(cls):
        """Same pattern rules, every filter switched off: shows where the bare pattern triggered."""
        return cls(max_vwap_share=99, min_atr_pct=0, qqq_limit_pct=99, clear_yesterday=False)


@dataclass
class DayContext:
    prev_close: float
    prev_high: float
    prev_low: float
    atr_pct: float                  # daily ATR (14 days) as % of yesterday's close
    qqq: pd.DataFrame = None        # QQQ's regular-hours 5-minute candles for the same day, if known


@dataclass
class OrbSignal:
    status: str                     # "trade", "skip" (it broke out but a filter said no) or "none"
    direction: str = ""             # "long" or "short" (from the opening candle)
    reasons: list = field(default_factory=list)
    candle: int = 0                 # number of the candle that broke the line (1 = 9:30 candle)
    time: pd.Timestamp = None       # start of that candle
    entry: float = 0.0
    stop: float = 0.0
    lid: float = 0.0                # the line: highest (long) / lowest (short) price of candles 1-2
    vwap: float = 0.0
    gap_pct: float = 0.0

    @property
    def risk(self):
        return abs(self.entry - self.stop)


@dataclass
class TradeResult:
    exits: list                     # (time, price, fraction of the position, why)
    r: float                        # result in R


@dataclass
class Slippage:
    """
    How much worse than the chart price real fills are, per share: a % of the price plus a cent.
    [Proposed] estimates. FPB's first paper day had stop fills $0.35-0.48 worse, so stops get the
    most. The 3R sale is a limit order, so it gets none. Backtest reports also show double slippage.
    """
    entry_pct: float = 0.05             # the entry is a stop order: it fills a little past the line
    stop_pct: float = 0.20              # stop orders in a fast move
    market_pct: float = 0.05            # 9 EMA and 11:30 exits (market orders)
    cents: float = 0.01

    def r(self, sig: "OrbSignal", result: "TradeResult", times=1.0) -> float:
        """Total slippage of one trade in R (subtract from the result)."""
        cost = sig.entry * self.entry_pct / 100 + self.cents
        for _, price, fraction, why in result.exits:
            if "target" not in why:
                pct = self.stop_pct if "stop" in why else self.market_pct
                cost += fraction * (price * pct / 100 + self.cents)
        return cost * times / sig.risk


def vwap(candles: pd.DataFrame) -> pd.Series:
    """VWAP after each candle, counted from the first candle given (pass one day's candles)."""
    typical = (candles.high + candles.low + candles.close) / 3
    return (typical * candles.volume).cumsum() / candles.volume.cumsum()


def five_minute_candles(minutes: pd.DataFrame) -> pd.DataFrame:
    """Join 1-minute candles into 5-minute candles (labelled by their start time)."""
    grouped = minutes.resample("5min", label="left", closed="left")
    out = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna(subset=["open"])


def daily_candles(candles: pd.DataFrame) -> pd.DataFrame:
    """One open/high/low/close row per day from regular-hours intraday candles."""
    by_day = candles.groupby(candles.index.date)
    return pd.DataFrame({"open": by_day.open.first(), "high": by_day.high.max(),
                         "low": by_day.low.min(), "close": by_day.close.last()})


def day_context(earlier: pd.DataFrame, qqq: pd.DataFrame = None, atr_days=14) -> DayContext:
    """
    Context for a trading day from the regular-hours 5-minute candles of the days before it:
    yesterday's close/high/low and the average daily range (ATR) of the last `atr_days` days.
    """
    days = daily_candles(earlier)
    if days.empty:
        raise ValueError("no earlier days to compare with")
    prev_close = days.close.shift(1)
    true_range = pd.concat([days.high - days.low, (days.high - prev_close).abs(),
                            (days.low - prev_close).abs()], axis=1).max(axis=1)
    atr = true_range.tail(atr_days).mean()
    last = days.iloc[-1]
    return DayContext(prev_close=last.close, prev_high=last.high, prev_low=last.low,
                      atr_pct=atr / last.close * 100, qqq=qqq)


def find_orb(candles: pd.DataFrame, ctx: DayContext, s: OrbSettings = None) -> OrbSignal:
    """
    One day's regular-hours 5-minute candles (first one at 9:30) -> the ORB decision for that day.
    Direction: a gap of 1%+ sets it (gap up = long, gap down = short); without a gap the opening
    candle does (and if that closed where it opened, where it closed versus yesterday's close).
    The first break of the line from 9:40 to 11:00 decides (one ORB per stock per day).
    Filters only use what was known at the moment of the break.
    """
    s = s or OrbSettings()
    if len(candles) < 3 or [t.time() for t in candles.index[:2]] != [time(9, 30), time(9, 35)]:
        return OrbSignal("none", reasons=["no 9:30 and 9:35 candles, or too few candles"])
    c1, c2 = candles.iloc[0], candles.iloc[1]
    gap = (c1.open / ctx.prev_close - 1) * 100
    move = gap if abs(gap) >= s.gap_direction_pct else (c1.close - c1.open) or (c1.close - ctx.prev_close)
    if move == 0:
        return OrbSignal("none", reasons=["no gap and a flat opening candle: no direction"], gap_pct=gap)
    long = move > 0
    sig = OrbSignal("none", "long" if long else "short", gap_pct=gap)
    sig.lid = max(c1.high, c2.high) if long else min(c1.low, c2.low)
    running_vwap = vwap(candles)
    for k in range(2, len(candles)):
        start = candles.index[k]
        if start.time() < s.earliest_entry:
            continue
        if start.time() >= s.last_entry:
            break
        bar = candles.iloc[k]
        if long and bar.high > sig.lid:
            entry = max(bar.open, sig.lid + s.tick)
        elif not long and bar.low < sig.lid:
            entry = min(bar.open, sig.lid - s.tick)
        else:
            continue
        sig.candle = int((start - candles.index[0]) / timedelta(minutes=5)) + 1
        sig.time, sig.entry = start, round(entry, 4)
        sig.vwap = running_vwap.iloc[k - 1]              # VWAP known when the break happens
        buffer = s.stop_buffer_pct / 100
        sig.stop = round(sig.vwap * (1 - buffer if long else 1 + buffer), 4)
        sig.reasons = _filter_reasons(sig, long, candles.iloc[:k], ctx, s)
        sig.status = "skip" if sig.reasons else "trade"
        return sig
    sig.reasons = ["no break of the line before 11:00"]
    return sig


def _filter_reasons(sig, long, before, ctx, s):
    """Why the break may not be traded (empty list = trade it). `before` = candles before the break."""
    reasons = []
    if (long and sig.entry <= sig.vwap) or (not long and sig.entry >= sig.vwap):
        reasons.append("price on the wrong side of VWAP")
    else:
        far_end = before.low.min() if long else before.high.max()
        width = abs(sig.lid - far_end)
        share = abs(sig.entry - sig.vwap) / width if width > 0 else float("inf")
        if share > s.max_vwap_share:
            reasons.append(f"too far from VWAP ({share:.0%} of the opening range)")
    if s.clear_yesterday:
        if long and sig.entry <= ctx.prev_high:
            reasons.append(f"not above yesterday's high ({ctx.prev_high:.2f})")
        if not long and sig.entry >= ctx.prev_low:
            reasons.append(f"not below yesterday's low ({ctx.prev_low:.2f})")
    if ctx.atr_pct < s.min_atr_pct:
        reasons.append(f"moves too little (daily ATR {ctx.atr_pct:.1f}%)")
    if ctx.qqq is not None and len(ctx.qqq) and abs(sig.gap_pct) < s.news_gap_pct:
        so_far = ctx.qqq.loc[:sig.time]
        change = (so_far.open.iloc[-1] / ctx.qqq.open.iloc[0] - 1) * 100
        if long and change <= -s.qqq_limit_pct:
            reasons.append(f"QQQ down {change:.1f}% since the open")
        if not long and change >= s.qqq_limit_pct:
            reasons.append(f"QQQ up {change:+.1f}% since the open")
    return reasons


def simulate_trade(sig: OrbSignal, minutes: pd.DataFrame, closes5: pd.Series,
                   s: OrbSettings = None) -> TradeResult:
    """
    Play a "trade" signal forward on that day's regular-hours 1-minute candles.
    `closes5` = 5-minute closes up to that day (include earlier days so the 9 EMA is warmed up).
    Within one minute the stop is checked before the target (the cautious assumption). In the
    minute of the break only its close can stop the trade out: its low may have come before the break.
    """
    s = s or OrbSettings()
    long = sig.direction == "long"
    side, risk = (1 if long else -1), sig.risk
    target = sig.entry + side * s.first_target_r * risk
    ema = closes5.ewm(span=s.ema_period, adjust=False).mean()
    stop, left, sold_first, entered, exits = sig.stop, 1.0, False, False, []

    def out(when, price, fraction, why):
        nonlocal left
        exits.append((when, round(price, 4), fraction, why))
        left -= fraction

    for when, m in minutes.loc[sig.time:].iterrows():
        if not entered:
            if not ((long and m.high > sig.lid) or (not long and m.low < sig.lid)):
                continue
            entered = True
            if (long and m.close <= stop) or (not long and m.close >= stop):
                out(when, m.close, left, "stopped out in the breakout minute")
                break
        else:
            if when.time() >= s.hard_exit:
                out(when, m.open, left, f"{s.hard_exit:%H:%M} time exit")
                break
            if (long and m.low <= stop) or (not long and m.high >= stop):
                gapped = (long and m.open < stop) or (not long and m.open > stop)
                out(when, m.open if gapped else stop, left, "breakeven stop" if sold_first else "stop")
                break
        if not sold_first and ((long and m.high >= target) or (not long and m.low <= target)):
            out(when, target, s.first_sale, f"{s.first_target_r:g}R target")
            sold_first, stop = True, sig.entry
        if sold_first and when.minute % 5 == 4:          # last minute of a 5-minute candle
            candle = when.floor("5min")
            if candle in ema.index:
                close, average = closes5.loc[candle], ema.loc[candle]
                if (long and close < average) or (not long and close > average):
                    out(candle + timedelta(minutes=5), close, left, f"closed past the {s.ema_period} EMA")
                    break
    if left > 1e-9 and entered:
        last = minutes.iloc[-1]
        out(minutes.index[-1], last.close, left, "end of data")
    r = sum(fraction * side * (price - sig.entry) for _, price, fraction, _ in exits) / risk if exits else 0.0
    return TradeResult(exits=exits, r=round(r, 3))
