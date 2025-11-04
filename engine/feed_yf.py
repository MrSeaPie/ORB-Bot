import pandas as pd, yfinance as yf

def load_5m(sym: str, period="30d", tz="America/New_York") -> pd.DataFrame:
    df = yf.download(sym, period=period, interval="5m", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.xs(sym, axis=1, level=1, drop_level=True)
        except Exception:
            df = df.droplevel(-1, axis=1)
    df = df.rename(columns=lambda c: str(c).lower())
    df = df[["open","high","low","close","volume"]].dropna()
    df.index = (df.index.tz_localize("UTC").tz_convert(tz)
                if df.index.tz is None else df.index.tz_convert(tz))
    df["date"] = df.index.date
    return df
