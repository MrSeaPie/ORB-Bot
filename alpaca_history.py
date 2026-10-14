"""
Price history from Alpaca, saved on disk so each month is downloaded only once.

Written for the ORB tests (FPB can use it later). It only READS market data: nothing here can
place an order. Keys come from the .env file next to this script, the same keys as the paper trader.

Safety: the live FPB bot uses those keys during market hours, and Alpaca limits how many requests a
key may make per minute. So downloads refuse to run on weekdays from 9:15 AM to 4:05 PM New York
time (reading what is already saved is always fine), unless allow_market_hours=True.

Saved files: data_cache/<timeframe>/<SYMBOL>/<YYYY-MM>.csv.gz, one per stock per month, New York
time, prices as they traded that day (not adjusted for later splits). A month is saved only once it
is over. The folder is git-ignored and can be deleted any time; it is rebuilt when needed.

    from alpaca_history import get_bars, regular_hours
    bars = get_bars("TSLA", date(2025, 5, 1), date(2025, 5, 31), "5Min")
"""
import os
import time as _time
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "data_cache"
COLUMNS = ["open", "high", "low", "close", "volume"]
TIMEFRAMES = {"1Min": (1, "Minute"), "5Min": (5, "Minute"), "1Day": (1, "Day")}
REQUEST_PAUSE = 0.35          # seconds between requests (Alpaca's free plan allows 200 a minute)
BLOCKED_FROM, BLOCKED_UNTIL = time(9, 15), time(16, 5)


def _load_env_file(path: Path):
    """Read KEY=value lines from .env into os.environ (real env vars win). Same as the paper trader."""
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_env_file(HERE / ".env")


class MarketHoursError(RuntimeError):
    """Raised instead of downloading while the live bot may need the Alpaca request limit."""


def check_download_allowed(allow_market_hours=False, now=None):
    """Raise MarketHoursError on weekdays 9:15 AM-4:05 PM New York time (see the module notes)."""
    now = now or datetime.now(ET)
    if not allow_market_hours and now.weekday() < 5 and BLOCKED_FROM <= now.time() <= BLOCKED_UNTIL:
        raise MarketHoursError(
            "Not downloading between 9:15 AM and 4:05 PM New York time on weekdays: the live FPB bot "
            "shares these Alpaca keys and needs the request limit. Run this after the close.")


_client = None


def _alpaca():
    global _client
    if _client is None:
        from alpaca.data.historical import StockHistoricalDataClient
        key, secret = os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_SECRET_KEY", "")
        if not key or key.startswith("YOUR_"):
            raise RuntimeError("Alpaca keys not found. Put them in the .env file next to this script "
                               "(see .env.example).")
        _client = StockHistoricalDataClient(key, secret)
    return _client


def _empty():
    return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], tz=ET, name="timestamp"), dtype=float)


def _download(symbol, timeframe, start: datetime, end: datetime, feed) -> pd.DataFrame:
    """One request to Alpaca (alpaca-py fetches all pages). Returns candles in New York time."""
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    amount, unit = TIMEFRAMES[timeframe]
    request = StockBarsRequest(symbol_or_symbols=symbol, start=start, end=end, feed=DataFeed(feed),
                               timeframe=TimeFrame(amount, getattr(TimeFrameUnit, unit)),
                               adjustment=Adjustment.RAW)
    _time.sleep(REQUEST_PAUSE)
    df = _alpaca().get_stock_bars(request).df
    if df.empty:
        return _empty()
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    df.index = pd.DatetimeIndex(df.index).tz_convert(ET)
    df.index.name = "timestamp"
    return df[COLUMNS].astype(float)


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col="timestamp")
    if df.empty:
        return _empty()
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(ET)
    return df[COLUMNS].astype(float)


def get_bars(symbol: str, start: date, end: date, timeframe="5Min", feed="sip",
             allow_market_hours=False) -> pd.DataFrame:
    """
    Candles for `symbol` from `start` to `end` (dates, both included), New York time, oldest first.
    Includes pre-market and after-hours candles; regular_hours() keeps 9:30-4:00 only.
    feed="sip" is all US exchanges (Alpaca's free plan allows it for data older than 15 minutes).
    """
    symbol, folder = symbol.upper(), CACHE_DIR / timeframe / symbol.upper()
    now = datetime.now(ET)
    pieces = []
    for y, m in _months(start, end):
        first = datetime(y, m, 1, tzinfo=ET)
        after = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=ET)
        path = folder / f"{y:04d}-{m:02d}.csv.gz"
        if path.exists():
            pieces.append(_read(path))
            continue
        check_download_allowed(allow_market_hours, now)
        month_over = after <= now
        df = _download(symbol, timeframe, first, after if month_over else now - timedelta(minutes=20), feed)
        df.index.name = "timestamp"
        if month_over:
            folder.mkdir(parents=True, exist_ok=True)
            ignore = CACHE_DIR / ".gitignore"
            if not ignore.exists():
                ignore.write_text("# Downloaded price history: rebuilt when needed, never uploaded\n*\n")
            df.to_csv(path, compression="gzip")
        pieces.append(df)
    out = pd.concat([p for p in pieces if len(p)]) if any(len(p) for p in pieces) else _empty()
    out = out[~out.index.duplicated()].sort_index()
    days = out.index.date
    return out[(days >= start) & (days <= end)]


def regular_hours(df: pd.DataFrame) -> pd.DataFrame:
    """Keep candles that start between 9:30 AM and 4:00 PM New York time (the regular session)."""
    minutes = df.index.hour * 60 + df.index.minute
    return df[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)]
