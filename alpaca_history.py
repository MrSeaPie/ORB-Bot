"""
Price history from Alpaca, saved on disk so each month is downloaded only once.

Written for the ORB tests (FPB can use it later). It only READS market data and Alpaca's list of
stocks: nothing here places, changes or cancels an order. Keys come from the .env file next to this
script, the same keys as the paper trader.

Safety: the live FPB bot uses those keys during market hours, and Alpaca limits how many requests a
key may make per minute. So downloads refuse to run on weekdays from 9:15 AM to 4:05 PM New York
time (reading what is already saved is always fine), unless allow_market_hours=True.

Saved files: data_cache/<timeframe>/<SYMBOL>/<YYYY-MM>.csv.gz, one per stock per month, New York
time, prices as they traded that day (not adjusted for later splits). A month is saved only once it
is over. The folder is git-ignored and can be deleted any time; it is rebuilt when needed.

    from alpaca_history import get_bars, regular_hours
    bars = get_bars("TSLA", date(2025, 5, 1), date(2025, 5, 31), "5Min")      # one stock, intraday
    daily = get_daily_many(["TSLA", "NVDA"], date(2025, 1, 1), date(2025, 5, 31))  # many stocks, daily
"""
import os
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "data_cache"
COLUMNS = ["open", "high", "low", "close", "volume"]
TIMEFRAMES = {"1Min": (1, "Minute"), "5Min": (5, "Minute"), "1Day": (1, "Day")}
REQUEST_PAUSE = 0.35          # seconds between requests, all threads together (free plan: 200 a minute)
WORKERS = 6                   # downloads running at once (each request takes a few seconds)
BLOCKED_FROM, BLOCKED_UNTIL = time(9, 15), time(16, 5)
# Real tickers Windows can't use as folder names (e.g. CON, PRN): their folders get a "_" added
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)}


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


_local = threading.local()          # one Alpaca connection per thread
_rate_lock = threading.Lock()
_next_request = 0.0


def _wait_turn():
    """Space requests REQUEST_PAUSE apart across all threads, so we stay under Alpaca's limit."""
    global _next_request
    with _rate_lock:
        now = _time.monotonic()
        wait = _next_request - now
        _next_request = max(now, _next_request) + REQUEST_PAUSE
    if wait > 0:
        _time.sleep(wait)


def _alpaca():
    client = getattr(_local, "client", None)
    if client is None:
        from alpaca.data.historical import StockHistoricalDataClient
        key, secret = os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_SECRET_KEY", "")
        if not key or key.startswith("YOUR_"):
            raise RuntimeError("Alpaca keys not found. Put them in the .env file next to this script "
                               "(see .env.example).")
        client = _local.client = StockHistoricalDataClient(key, secret)
    return client


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
    _wait_turn()
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


def _month_path(timeframe, symbol, y, m) -> Path:
    symbol = symbol.upper()
    folder = CACHE_DIR / timeframe / (symbol + "_" if symbol.split(".")[0] in WINDOWS_RESERVED else symbol)
    return folder / f"{y:04d}-{m:02d}.csv.gz"


def prefetch(symbol_days, timeframe="5Min", allow_market_hours=False, progress=None):
    """
    Download, several at once, the month files get_bars() will need for these (symbol, date) pairs,
    so a long backtest isn't waiting on one request at a time. Saved months are skipped.
    Returns (months downloaded, months that failed). `progress(done, total)` is called now and then.
    """
    months = sorted({(s.upper(), d.year, d.month) for s, d in symbol_days})
    todo = [(s, y, m) for s, y, m in months if not _month_path(timeframe, s, y, m).exists()]
    if not todo:
        return 0, 0
    check_download_allowed(allow_market_hours)

    def one(item):
        s, y, m = item
        try:
            get_bars(s, date(y, m, 1), date(y, m, 1), timeframe, allow_market_hours=allow_market_hours)
            return True
        except MarketHoursError:
            raise
        except Exception:
            return False

    failed = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        for done, ok in enumerate(pool.map(one, todo), 1):
            failed += not ok
            if progress and (done % 200 == 0 or done == len(todo)):
                progress(done, len(todo))
    return len(todo), failed


def get_bars(symbol: str, start: date, end: date, timeframe="5Min", feed="sip",
             allow_market_hours=False) -> pd.DataFrame:
    """
    Candles for `symbol` from `start` to `end` (dates, both included), New York time, oldest first.
    Includes pre-market and after-hours candles; regular_hours() keeps 9:30-4:00 only.
    feed="sip" is all US exchanges (Alpaca's free plan allows it for data older than 15 minutes).
    """
    symbol = symbol.upper()
    now = datetime.now(ET)
    pieces = []
    for y, m in _months(start, end):
        first = datetime(y, m, 1, tzinfo=ET)
        after = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=ET)
        path = _month_path(timeframe, symbol, y, m)
        folder = path.parent
        if path.exists():
            pieces.append(_read(path))
            continue
        check_download_allowed(allow_market_hours, now)
        month_over = after <= now
        df = _download(symbol, timeframe, first, after if month_over else now - timedelta(minutes=20), feed)
        df.index.name = "timestamp"
        if month_over:
            folder.mkdir(parents=True, exist_ok=True)
            _ignore_cache_folder()
            df.to_csv(path, compression="gzip")
        pieces.append(df)
    out = pd.concat([p for p in pieces if len(p)]) if any(len(p) for p in pieces) else _empty()
    out = out[~out.index.duplicated()].sort_index()
    days = out.index.date
    return out[(days >= start) & (days <= end)]


def get_assets(allow_market_hours=False) -> pd.DataFrame:
    """
    Today's active, tradable US stocks and ETFs on the main exchanges (OTC left out), saved once a day.
    Only READS Alpaca's asset list. Note: only stocks that still exist today, so stocks that went bust or
    were bought out are missing from any backtest built on it ("survivorship bias").
    """
    path = CACHE_DIR / "assets" / f"{datetime.now(ET):%Y-%m-%d}.csv"
    if path.exists():
        return pd.read_csv(path, keep_default_na=False)
    check_download_allowed(allow_market_hours)
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest
    _alpaca()                                            # checks the keys are there
    trading = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)
    assets = trading.get_all_assets(GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE))
    df = pd.DataFrame([{"symbol": a.symbol, "name": a.name or "", "exchange": str(a.exchange).split(".")[-1],
                        "shortable": bool(a.shortable), "easy_to_borrow": bool(a.easy_to_borrow)}
                       for a in assets if a.tradable and str(a.exchange).split(".")[-1] != "OTC"])
    path.parent.mkdir(parents=True, exist_ok=True)
    _ignore_cache_folder()
    df.sort_values("symbol").to_csv(path, index=False)
    return df


def _ignore_cache_folder():
    ignore = CACHE_DIR / ".gitignore"
    if not ignore.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ignore.write_text("# Downloaded price history: rebuilt when needed, never uploaded\n*\n")


def _download_daily_many(symbols, start: datetime, end: datetime, feed):
    """
    Daily candles (split-adjusted) for many stocks, several batches at once.
    Returns (candles, failed symbols). A batch that keeps failing is split in half until the bad
    symbol is found; failed symbols are reported so they are not saved as "done".
    """
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    def fetch(batch):
        for attempt in range(3):
            request = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day, start=start, end=end,
                                       adjustment=Adjustment.SPLIT, feed=DataFeed(feed))
            _wait_turn()
            try:
                df = _alpaca().get_stock_bars(request).df
                break
            except Exception:
                _time.sleep(2 * (attempt + 1))
        else:
            if len(batch) == 1:
                return [], batch
            halves = [fetch(batch[:len(batch) // 2]), fetch(batch[len(batch) // 2:])]
            return halves[0][0] + halves[1][0], halves[0][1] + halves[1][1]
        if df.empty:
            return [], []
        df = df.reset_index()
        df["date"] = pd.to_datetime(df.timestamp).dt.tz_convert(ET).dt.strftime("%Y-%m-%d")
        return [df[["symbol", "date"] + COLUMNS]], []

    batches = [symbols[i:i + 200] for i in range(0, len(symbols), 200)]
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(fetch, batches))
    frames = [f for found, _ in results for f in found]
    failed = [s for _, bad in results for s in bad]
    out = pd.concat(frames) if frames else pd.DataFrame(columns=["symbol", "date"] + COLUMNS)
    return out, failed


def get_daily_many(symbols, start: date, end: date, feed="sip", allow_market_hours=False) -> pd.DataFrame:
    """
    Daily candles for many stocks at once: columns symbol, date ("YYYY-MM-DD"), open, high, low,
    close, volume. Alpaca's daily candles cover regular hours (they match the 9:30-4:00 candles), and
    these are ADJUSTED for splits so a split never looks like a gap. Intraday candles from get_bars()
    are not adjusted: convert with the day's opening price (see run_orb_backtest.py).
    Saved per month in data_cache/1Day_many/, with a list of which stocks each file already holds.
    """
    folder, now = CACHE_DIR / "1Day_many", datetime.now(ET)
    want = sorted({s.upper() for s in symbols})
    frames = []
    for y, m in _months(start, end):
        first = datetime(y, m, 1, tzinfo=ET)
        after = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=ET)
        path, listed = folder / f"{y:04d}-{m:02d}.csv.gz", folder / f"{y:04d}-{m:02d}.symbols.txt"
        cached = pd.read_csv(path, keep_default_na=False) if path.exists() else None
        have = set(listed.read_text().split()) if listed.exists() else set()
        missing = [s for s in want if s not in have]
        if missing:
            check_download_allowed(allow_market_hours, now)
            month_over = after <= now
            new, failed = _download_daily_many(missing, first, after if month_over else now - timedelta(minutes=20), feed)
            if failed:
                print(f"  ({len(failed)} stock(s) could not be downloaded for {y}-{m:02d}; a later run tries again)")
            cached = new if cached is None else pd.concat([cached, new])
            if month_over:
                folder.mkdir(parents=True, exist_ok=True)
                _ignore_cache_folder()
                cached.to_csv(path, index=False, compression="gzip")
                listed.write_text("\n".join(sorted(have | (set(missing) - set(failed)))))
        if cached is not None and len(cached):
            frames.append(cached[cached.symbol.isin(want)])
    if not frames:
        return pd.DataFrame(columns=["symbol", "date"] + COLUMNS)
    out = pd.concat(frames)
    out = out[(out.date >= f"{start}") & (out.date <= f"{end}")].drop_duplicates(["symbol", "date"])
    return out.sort_values(["symbol", "date"]).reset_index(drop=True)


MORNING = (time(9, 30), time(11, 35))   # ORB trades are over by 11:30


def _morning_path(symbol, day: date) -> Path:
    symbol = symbol.upper()
    folder = CACHE_DIR / "1Min_morning" / (symbol + "_" if symbol.split(".")[0] in WINDOWS_RESERVED else symbol)
    return folder / f"{day:%Y-%m-%d}.csv.gz"


def get_morning_minutes(symbol: str, day: date, feed="sip", allow_market_hours=False) -> pd.DataFrame:
    """
    1-minute candles from 9:30 to 11:35 New York time on one day: all a backtested ORB trade needs.
    One small request per stock-day instead of a month of 1-minute candles. Saved per day.
    """
    path = _morning_path(symbol, day)
    if path.exists():
        return _read(path)
    check_download_allowed(allow_market_hours)
    start, end = (datetime.combine(day, t, tzinfo=ET) for t in MORNING)
    df = _download(symbol.upper(), "1Min", start, end, feed)
    df.index.name = "timestamp"
    if end < datetime.now(ET) - timedelta(minutes=20):          # only a finished morning is saved
        path.parent.mkdir(parents=True, exist_ok=True)
        _ignore_cache_folder()
        df.to_csv(path, compression="gzip")
    return df


def prefetch_mornings(symbol_days, allow_market_hours=False, progress=None):
    """get_morning_minutes() for many (symbol, date) pairs, several at once. Returns (downloaded, failed)."""
    todo = sorted({(s.upper(), d) for s, d in symbol_days if not _morning_path(s, d).exists()})
    if not todo:
        return 0, 0
    check_download_allowed(allow_market_hours)

    def one(item):
        try:
            get_morning_minutes(*item, allow_market_hours=allow_market_hours)
            return True
        except MarketHoursError:
            raise
        except Exception:
            return False

    failed = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        for done, ok in enumerate(pool.map(one, todo), 1):
            failed += not ok
            if progress and (done % 200 == 0 or done == len(todo)):
                progress(done, len(todo))
    return len(todo), failed


def regular_hours(df: pd.DataFrame) -> pd.DataFrame:
    """Keep candles that start between 9:30 AM and 4:00 PM New York time (the regular session)."""
    minutes = df.index.hour * 60 + df.index.minute
    return df[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)]
