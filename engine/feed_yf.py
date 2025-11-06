# engine/feed_yf.py
import pandas as pd
import yfinance as yf

def fetch_history(symbol: str, days: int = 60) -> pd.DataFrame:
    """
    Always return intraday data when days <= 60.
    Yahoo rules (practical):
      - 1m: ~7 days max
      - 5m: ~60 days max
      - >=60d: fall back to 30m
    """
    if days <= 7:
        interval = "1m"
    elif days <= 60:
        interval = "5m"
    else:
        interval = "30m"

    df = yf.download(
        tickers=symbol,
        period=f"{days}d",
        interval=interval,
        auto_adjust=False,
        prepost=False,      # RTH only
        progress=False,
        threads=True,
    )

    # Make sure we get a DatetimeIndex and lower-case OHLCV cols
    if df is None or len(df) == 0:
        return pd.DataFrame()

    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            return pd.DataFrame()

    # Normalize column names
    rename_map = {c: c.lower() for c in df.columns}
    df = df.rename(columns=rename_map)

    # Keep only expected columns if present
    cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[cols]

    # Drop days with no RTH (rare)
    df = df.sort_index()
    return df
