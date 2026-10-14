"""
ORB's own stock finder (ORB_RULES.md, section 3b). Separate from the FPB scanner: it does not use
or change scanners/ or universe.txt.

From daily candles of many stocks it builds each morning's list the way Kunal's scans do:
  1. gappers: open 3%+ above or below yesterday's close, price $5+            [Kunal 71, scan 78]
  2. yesterday's movers: closed 2%+ up or down on 1M+ shares and 2x the normal volume,
     price $2+ (gainers are long candidates, losers short candidates)       [Kunal scan 76, 78]
  3. go-to stocks: moving (daily ATR 2%+) and trending above (or below) their 9/20/50-day
     averages, price $2+ (long candidates in uptrends, short in downtrends)  [Kunal scan 76, 78; Proposed]
Liquid: 1M+ shares a day on average (last 20 days) [Kunal scan 76]; for gappers 500k+, because
Kunal checks gappers by their pre-market volume instead (the backtest records it). Every stock must
move: daily ATR 2%+ (the ORB rule, so stocks ORB would skip anyway aren't fetched).
Order: gappers (biggest gap first), then movers (highest relative volume first), then go-to stocks
(biggest daily range first); a stock appears once.

The defaults are WIDE on purpose ("research mode"). The May 2025 pilot showed that a top-10 list by
gap size fills up with tiny pump stocks and misses Kunal's own picks: about 90 liquid stocks gap 3%+
on a normal day. So the backtest tests every candidate and records what it was like. The
development period then shows which kinds of stocks ORB works on, and that becomes the ranking.

Only uses what was known before the open, plus the opening price for the gap.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class FinderSettings:
    min_avg_volume: float = 1_000_000   # shares a day, 20-day average [Kunal scan 76]
    gapper_min_avg_volume: float = 500_000  # gappers: Kunal judges them by pre-market volume [Proposed]
    gap_pct: float = 3.0                # gappers [Kunal 71, scan 78]
    gapper_min_price: float = 5.0       # [Kunal scan 78]
    mover_pct: float = 2.0              # yesterday's movers [Kunal scan 78]
    mover_min_volume: float = 1_000_000
    mover_rel_volume: float = 2.0       # yesterday's volume vs its 20-day average [Kunal scan 78]
    min_price: float = 2.0              # movers and go-to stocks [Kunal's screen]
    min_atr_pct: float = 2.0            # same as the ORB rule [orb_strategy.OrbSettings.min_atr_pct]
    max_goto: int = 15                  # go-to stocks per day (there can be hundreds)
    per_day: int = 0                    # cap on the whole list; 0 = no cap (research mode)


def daily_features(daily: pd.DataFrame) -> pd.DataFrame:
    """
    `daily`: columns symbol, date, open, high, low, close, volume (split-adjusted), any order.
    Adds, for every stock and day, what was known at that day's open (all from earlier days except
    `gap_pct`, which uses the day's opening price).
    """
    df = daily.sort_values(["symbol", "date"]).reset_index(drop=True)
    g = df.groupby("symbol", sort=False)
    df["prev_close"] = g.close.shift(1)
    df["prev_high"] = g.high.shift(1)
    df["prev_low"] = g.low.shift(1)
    df["prev_volume"] = g.volume.shift(1)
    df["gap_pct"] = (df.open / df.prev_close - 1) * 100
    df["move_pct"] = (df.prev_close / g.close.shift(2) - 1) * 100
    df["avg_volume"] = g.volume.transform(lambda v: v.shift(1).rolling(20).mean())
    df["rel_volume"] = df.prev_volume / g.volume.transform(lambda v: v.shift(2).rolling(20).mean())
    true_range = np.maximum(df.high - df.low, np.maximum((df.high - df.prev_close).abs(),
                                                         (df.low - df.prev_close).abs()))
    df["atr_pct"] = true_range.groupby(df.symbol).transform(lambda t: t.shift(1).rolling(14).mean()) / df.prev_close * 100
    ema9 = g.close.transform(lambda c: c.ewm(span=9, adjust=False).mean().shift(1))
    sma20 = g.close.transform(lambda c: c.rolling(20).mean().shift(1))
    sma50 = g.close.transform(lambda c: c.rolling(50).mean().shift(1))
    above = (df.prev_close > ema9) & (df.prev_close > sma20) & (df.prev_close > sma50)
    below = (df.prev_close < ema9) & (df.prev_close < sma20) & (df.prev_close < sma50)
    df["trend"] = np.where(above, 1, np.where(below, -1, 0))
    df.loc[sma50.isna(), "trend"] = 0
    up = (df.close > g.close.shift(1)).astype(int)
    streak = up.groupby((up != up.groupby(df.symbol).shift()).cumsum()).cumsum() * up
    df["up_days"] = streak.groupby(df.symbol).shift(1).fillna(0)       # up days in a row before today
    return df


def candidates_for_day(day_rows: pd.DataFrame, s: FinderSettings = None) -> pd.DataFrame:
    """
    `day_rows`: the daily_features() rows of one date. Returns the morning list, best first, with
    columns rank, source ("gapper" / "mover" / "go-to") and side ("long", "short" or "" = either).
    """
    s = s or FinderSettings()
    d = day_rows[day_rows.prev_close.notna() & (day_rows.atr_pct >= s.min_atr_pct)]
    liquid = d[d.avg_volume >= s.min_avg_volume]
    gappers = d[(d.avg_volume >= s.gapper_min_avg_volume) & (d.gap_pct.abs() >= s.gap_pct)
                & (d.open >= s.gapper_min_price)].assign(source="gapper", side="", score=lambda x: x.gap_pct.abs())
    movers = liquid[(liquid.move_pct.abs() >= s.mover_pct) & (liquid.prev_volume >= s.mover_min_volume)
                    & (liquid.rel_volume >= s.mover_rel_volume) & (liquid.prev_close >= s.min_price)].assign(
        source="mover", side=lambda x: np.where(x.move_pct > 0, "long", "short"), score=lambda x: x.rel_volume)
    goto = liquid[(liquid.trend != 0) & (liquid.prev_close >= s.min_price)].assign(
        source="go-to", side=lambda x: np.where(x.trend > 0, "long", "short"), score=lambda x: x.atr_pct)
    goto = goto.sort_values("score", ascending=False).head(s.max_goto or len(goto))
    lists = [x.sort_values("score", ascending=False) for x in (gappers, movers, goto) if len(x)]
    if not lists:
        return d.head(0).assign(source="", side="", score=0.0, rank=0)
    out = pd.concat(lists).drop_duplicates("symbol", keep="first")
    out = out.head(s.per_day) if s.per_day else out
    return out.assign(rank=range(1, len(out) + 1)).reset_index(drop=True)
