"""
ORB test suite with made-up candles (no internet, no Alpaca, no orders). Run it after every change
to orb_strategy.py or alpaca_history.py:

    .venv\\Scripts\\python.exe -X utf8 tests\\test_orb_strategy.py              # everything
    .venv\\Scripts\\python.exe -X utf8 tests\\test_orb_strategy.py exits        # some sections

Sections: signal, filters, exits, data.
The rules being tested are in ORB_RULES.md.
"""
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

project = Path(__file__).resolve().parent.parent
only = set(sys.argv[1:])
sys.path.insert(0, str(project))
import alpaca_history as hist  # noqa: E402
import orb_strategy as orb  # noqa: E402

ET = ZoneInfo("America/New_York")
DAY = "2025-05-27"
COLS = ["open", "high", "low", "close", "volume"]
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("  PASS " if ok else "  FAIL ") + name + (f"  ({detail})" if detail else ""))


def section(title, tag):
    if only and tag not in only:
        return False
    print(f"\n{title}")
    return True


def candles(rows, start="09:30", day=DAY):
    """5-minute candles from (open, high, low, close, volume) rows."""
    index = pd.date_range(f"{day} {start}", periods=len(rows), freq="5min", tz=ET)
    return pd.DataFrame(rows, columns=COLS, index=index, dtype=float)


def context(**changes):
    values = dict(prev_close=47.6, prev_high=49.2, prev_low=47.0, atr_pct=4.0)
    values.update(changes)
    return orb.DayContext(**values)


def minute_path(points, day=DAY):
    """1-minute candles moving in straight lines between (time, price) points."""
    rows, index = [], []
    for (t0, p0), (t1, p1) in zip(points, points[1:]):
        start, end = pd.Timestamp(f"{day} {t0}", tz=ET), pd.Timestamp(f"{day} {t1}", tz=ET)
        steps = int((end - start) / pd.Timedelta(minutes=1))
        for i in range(steps):
            o, c = p0 + (p1 - p0) * i / steps, p0 + (p1 - p0) * (i + 1) / steps
            rows.append((o, max(o, c) + 0.01, min(o, c) - 0.01, c, 1000))
            index.append(start + pd.Timedelta(minutes=i))
    return pd.DataFrame(rows, columns=COLS, index=pd.DatetimeIndex(index))


# A clean long: pops to 51.00, two sideways candles, breaks on candle 4
LONG_DAY = [
    (50.00, 51.00, 50.00, 50.90, 10000),   # 9:30 pushes up
    (50.90, 50.95, 50.55, 50.70, 5000),    # 9:35 sideways
    (50.70, 50.98, 50.65, 50.80, 4000),    # 9:40 sideways
    (50.80, 51.40, 50.75, 51.30, 8000),    # 9:45 breaks 51.00
] + [(51.30, 51.35, 51.25, 51.30, 1000)] * 4

# A clean short: drops to 49.00, breaks the floor on candle 3
SHORT_DAY = [
    (50.00, 50.10, 49.00, 49.10, 10000),   # 9:30 drops
    (49.10, 49.45, 49.05, 49.30, 5000),    # 9:35 sideways
    (49.30, 49.40, 48.80, 48.85, 8000),    # 9:40 breaks 49.00
] + [(48.85, 48.90, 48.80, 48.85, 1000)] * 4


if section("Pattern: the line, the 9:40 rule, long and short", "signal"):
    sig = orb.find_orb(candles(LONG_DAY), context())
    check("clean long is a trade", sig.status == "trade" and sig.direction == "long", sig.reasons)
    check("line = high of candles 1-2", sig.lid == 51.00, sig.lid)
    check("breaks on candle 4 at 9:45", sig.candle == 4 and sig.time.strftime("%H:%M") == "09:45")
    check("buys 1 cent above the line", abs(sig.entry - 51.01) < 1e-9, sig.entry)
    expected_vwap = (50.6333333 * 10000 + 50.7333333 * 5000 + 50.81 * 4000) / 19000   # through candle 3
    check("VWAP counts only candles before the break", abs(sig.vwap - expected_vwap) < 1e-4, sig.vwap)
    check("stop = VWAP minus 0.1%", abs(sig.stop - expected_vwap * 0.999) < 1e-3, sig.stop)

    rows = [(50.0, 51.0, 50.0, 50.9, 10000), (50.9, 51.5, 50.8, 51.2, 5000),   # candle 2 goes higher
            (51.2, 51.4, 51.0, 51.1, 4000), (51.1, 51.7, 51.05, 51.6, 8000)] + LONG_DAY[4:]
    sig = orb.find_orb(candles(rows), context())
    check("no entry during candle 2: its high becomes the line", sig.lid == 51.5 and sig.candle == 4, (sig.lid, sig.candle))
    check("... and the break of that line is traded", sig.status == "trade" and abs(sig.entry - 51.51) < 1e-9, sig.reasons)

    rows = LONG_DAY[:2] + [(50.70, 51.30, 50.65, 51.20, 6000)] + LONG_DAY[4:]
    sig = orb.find_orb(candles(rows), context())
    check("a break during candle 3 (9:40) is allowed", sig.candle == 3 and sig.status == "trade", (sig.candle, sig.reasons))

    sig = orb.find_orb(candles(SHORT_DAY), context(prev_close=52.6, prev_high=53.5, prev_low=51.0))
    check("clean short is a trade", sig.status == "trade" and sig.direction == "short", sig.reasons)
    check("short: line = low of candles 1-2, sells 1 cent below", sig.lid == 49.0 and abs(sig.entry - 48.99) < 1e-9)
    check("short: stop above VWAP", sig.stop > sig.vwap > sig.entry, (sig.entry, sig.vwap, sig.stop))

    breakout = (50.8, 51.4, 50.75, 51.3, 8000)
    rows = LONG_DAY[:2] + [(50.70, 50.98, 50.65, 50.80, 4000)] * 15 + [breakout]      # break at 10:55
    sig = orb.find_orb(candles(rows), context())
    check("a break at 10:55 is still an ORB", sig.status == "trade" and sig.time.strftime("%H:%M") == "10:55")
    rows = LONG_DAY[:2] + [(50.70, 50.98, 50.65, 50.80, 4000)] * 16 + [breakout]      # break at 11:00
    sig = orb.find_orb(candles(rows), context())
    check("a break at 11:00 or later is not an ORB", sig.status == "none" and "11:00" in sig.reasons[0], sig.reasons)

    sig = orb.find_orb(candles(LONG_DAY), context(prev_close=53.0))
    check("a 1%+ gap sets the direction, even against candle 1", sig.direction == "short", sig.direction)
    sig = orb.find_orb(candles(LONG_DAY), context(prev_close=50.3))
    check("no gap: candle 1 sets the direction", sig.direction == "long", sig.direction)
    rows = [(50.0, 51.0, 50.0, 50.0, 10000)] + LONG_DAY[1:]
    sig = orb.find_orb(candles(rows), context(prev_close=50.3))
    check("no gap, flat candle 1: close vs yesterday's close decides", sig.direction == "short", sig.direction)
    sig = orb.find_orb(candles(rows), context(prev_close=50.0))
    check("no gap, flat candle 1, unchanged from yesterday: no trade", sig.status == "none", sig.reasons)


if section("Filters: each one can stop a trade", "filters"):
    yesterday_rule = orb.OrbSettings(clear_yesterday=True)
    check("yesterday's range is not a rule by default (Kunal's ORCL, UPST)",
          orb.find_orb(candles(LONG_DAY), context(prev_high=52.0)).status == "trade")
    sig = orb.find_orb(candles(LONG_DAY), context(prev_high=52.0), yesterday_rule)
    check("option: long must be above yesterday's high", sig.status == "skip" and "yesterday" in sig.reasons[0], sig.reasons)
    sig = orb.find_orb(candles(SHORT_DAY), context(prev_close=52.6, prev_high=53.5, prev_low=48.5), yesterday_rule)
    check("option: short must be below yesterday's low", sig.status == "skip" and "yesterday" in sig.reasons[0], sig.reasons)
    sig = orb.find_orb(candles(LONG_DAY), context(atr_pct=1.5))
    check("stock that moves too little is skipped", sig.status == "skip" and "too little" in sig.reasons[0], sig.reasons)
    check("a daily range of 2.1% is enough (Kunal's TKR)", orb.find_orb(candles(LONG_DAY), context(atr_pct=2.1)).status == "trade")

    qqq_falling = candles([(400, 400.5, 399.5, 400, 1), (400, 400, 399, 399, 1),
                           (399, 399, 397.5, 398, 1), (397.9, 398, 397, 397.5, 1)])
    sig = orb.find_orb(candles(LONG_DAY), context(prev_close=49.8, qqq=qqq_falling))      # +0.4% gap
    check("no longs while QQQ is down 0.5%+", sig.status == "skip" and "QQQ" in sig.reasons[0], sig.reasons)
    sig = orb.find_orb(candles(LONG_DAY), context(qqq=qqq_falling))                       # +5% gap: own news
    check("a stock gapping 3%+ on its own news ignores QQQ", sig.status == "trade", sig.reasons)
    sig = orb.find_orb(candles(SHORT_DAY), context(prev_close=52.6, prev_high=53.5, prev_low=51.0, qqq=qqq_falling))
    check("a falling QQQ doesn't block shorts", sig.status == "trade", sig.reasons)

    rows = [(49.0, 51.0, 49.0, 49.2, 100000),   # heavy volume low in candle 1 keeps VWAP far below
            (49.2, 50.5, 49.1, 50.4, 1000), (50.4, 50.9, 50.3, 50.8, 1000), (50.8, 51.3, 50.7, 51.2, 1000)]
    sig = orb.find_orb(candles(rows), context(prev_close=46.6, prev_high=48.0))
    check("entry too far from VWAP is skipped", sig.status == "skip" and "too far" in sig.reasons[0], sig.reasons)

    sig = orb.find_orb(candles(LONG_DAY), context(prev_high=52.0, atr_pct=1.0), orb.OrbSettings.pattern_only())
    check("pattern_only() switches every filter off", sig.status == "trade", sig.reasons)


if section("Exits: stop, 3R + 9 EMA, 11:30", "exits"):
    start = [("09:30", 50.0), ("09:33", 50.95), ("09:36", 50.7), ("09:45", 50.75), ("09:47", 51.2)]
    warmup = pd.Series(50.0, index=pd.date_range("2025-05-23 13:00", periods=36, freq="5min", tz=ET))

    def play(points):
        minutes = minute_path(start + points)
        five = orb.five_minute_candles(minutes)
        sig = orb.find_orb(five, context())
        result = orb.simulate_trade(sig, minutes, pd.concat([warmup, five.close])) if sig.status == "trade" else None
        return sig, result

    sig, res = play([("09:52", 49.5), ("10:30", 49.5)])
    check("set-up for the exit tests is a trade", sig.status == "trade", sig.reasons)
    check("falls through VWAP: stopped out, -1R", res and [e[3] for e in res.exits] == ["stop"] and abs(res.r + 1) < 1e-6,
          res and (res.exits, res.r))

    sig, res = play([("10:05", 53.5), ("10:20", 51.6), ("11:00", 51.6)])
    whys = [e[3] for e in res.exits] if res else []
    check("half sold at 3R", res and whys[0] == "3R target" and res.exits[0][2] == 0.5
          and abs(res.exits[0][1] - (sig.entry + 3 * sig.risk)) < 1e-3, res and res.exits)
    check("rest sold when a 5-min candle closes below the 9 EMA", len(whys) == 2 and "9 EMA" in whys[1], whys)
    if res and len(res.exits) == 2:
        expected = 0.5 * 3 + 0.5 * (res.exits[1][1] - sig.entry) / sig.risk
        check("result in R adds up", abs(res.r - expected) < 1e-3, (res.r, expected))

    sig, res = play([("12:00", 51.3)])
    check("nothing hit: everything sold at 11:30", res and [e[3] for e in res.exits] == ["11:30 time exit"]
          and res.exits[0][0].strftime("%H:%M") == "11:30", res and res.exits)

    sig, res = play([("09:50", 52.4), ("09:55", 50.0), ("10:30", 50.0)])
    check("after the 3R sale the stop sits at breakeven", res and [e[3] for e in res.exits] == ["3R target", "breakeven stop"]
          and abs(res.r - 1.5) < 1e-6, res and (res.exits, res.r))


if section("Price-history downloader (no internet: Alpaca is faked)", "data"):
    tuesday_10am = datetime(2026, 10, 13, 10, 0, tzinfo=ET)
    try:
        hist.check_download_allowed(now=tuesday_10am)
        check("downloads blocked during market hours", False)
    except hist.MarketHoursError:
        check("downloads blocked during market hours", True)
    allowed = []
    for name, now, allow in [("after the close", datetime(2026, 10, 13, 20, 0, tzinfo=ET), False),
                             ("on a Saturday", datetime(2026, 10, 17, 10, 0, tzinfo=ET), False),
                             ("when explicitly allowed", tuesday_10am, True)]:
        try:
            hist.check_download_allowed(allow, now)
            check(f"downloads allowed {name}", True)
        except hist.MarketHoursError:
            check(f"downloads allowed {name}", False)

    calls = []

    def fake_download(symbol, timeframe, start, end, feed):
        calls.append((symbol, start.date()))
        index = pd.date_range(start, periods=3, freq="5min", tz=ET).union(
            pd.date_range(start + pd.Timedelta(days=10, hours=9, minutes=30), periods=3, freq="5min", tz=ET))
        return pd.DataFrame({c: range(1, 7) for c in COLS}, index=index, dtype=float)

    real_download, real_cache = hist._download, hist.CACHE_DIR
    hist._download, hist.CACHE_DIR = fake_download, Path(tempfile.mkdtemp()) / "data_cache"
    try:
        first = hist.get_bars("test", date(2025, 3, 1), date(2025, 3, 31), allow_market_hours=True)
        again = hist.get_bars("TEST", date(2025, 3, 1), date(2025, 3, 31), allow_market_hours=True)
        check("a finished month is downloaded once, then read from disk", len(calls) == 1, calls)
        check("data read back from disk is the same", first.equals(again) and str(again.index.tz) == "America/New_York")
        check("the cache folder is git-ignored", (hist.CACHE_DIR / ".gitignore").exists())
        check("only the requested dates come back",
              len(hist.get_bars("TEST", date(2025, 3, 11), date(2025, 3, 11), allow_market_hours=True)) == 3)
        today = datetime.now(ET).date()
        hist.get_bars("NOW", today, today, allow_market_hours=True)
        check("the current month is not saved (it isn't over)",
              not (hist.CACHE_DIR / "5Min" / "NOW" / f"{today:%Y-%m}.csv.gz").exists())
        rth = hist.regular_hours(first)
        check("regular_hours() keeps 9:30-4:00 only", len(rth) == 3 and rth.index[0].strftime("%H:%M") == "09:30")
    finally:
        hist._download, hist.CACHE_DIR = real_download, real_cache


print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
