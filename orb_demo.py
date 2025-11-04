# -------- ORB DEMO (no trading yet) --------
# This script downloads 5-minute data for AAPL,
# finds the first 5-min bar (opening range),
# and prints messages if price breaks above or below that range.

import pandas as pd
import yfinance as yf
from datetime import time

# --- SETTINGS ---
SYMBOL = "AAPL"      # stock symbol
INTERVAL = "5m"      # 5-minute candles
PERIOD = "5d"        # last 5 trading days
TZ = "America/New_York"

# --- DOWNLOAD DATA ---
df = yf.download(SYMBOL, interval=INTERVAL, period=PERIOD, progress=False)

# If Yahoo returns MultiIndex columns (e.g., ('High','AAPL')), collapse to single level
import pandas as pd
if isinstance(df.columns, pd.MultiIndex):
    # usually level 0 = OHLCV, level 1 = ticker
    try:
        df = df.xs(SYMBOL, axis=1, level=1, drop_level=True)
    except Exception:
        # fallback: take the first sublevel if symbol-level selection fails
        df = df.droplevel(-1, axis=1)

# standardize names and keep just OHLCV
df = df.rename(columns=lambda c: str(c).strip().lower().replace(" ", "_"))
missing = set(["open","high","low","close","volume"]) - set(df.columns)
if missing:
    raise RuntimeError(f"Downloaded data missing columns: {missing}. Try a different period or symbol.")
df = df[["open","high","low","close","volume"]].dropna(how="any")

# make sure index is in New York time
TZ = "America/New_York"
if df.index.tz is None:
    df = df.tz_localize("UTC").tz_convert(TZ)
else:
    df = df.tz_convert(TZ)

df["date"] = df.index.date


# --- DEFINE OPENING RANGE ---
ET_OPEN = time(9, 30)
ET_OR_END = time(9, 35)  # 5 minutes after open

or_mask = (df.index.time >= ET_OPEN) & (df.index.time < ET_OR_END)
or_by_day = df[or_mask].groupby("date").agg(
    or_high=("high", "max"),
    or_low=("low", "min")
)
df = df.join(or_by_day, on="date")

# --- DETECT BREAKOUTS ---
df["long_signal"]  = (df["high"] >= df["or_high"])
df["short_signal"] = (df["low"]  <= df["or_low"])

# --- PRINT ALERTS ---
long_done = set()
short_done = set()

for ts, row in df.iterrows():
    d = row["date"]
    if pd.isna(row.get("or_high")) or pd.isna(row.get("or_low")):
        continue

    if row["long_signal"] and d not in long_done:
        print(f"[{ts}] LONG ORB on {SYMBOL} above {row['or_high']:.2f}")
        long_done.add(d)

    if row["short_signal"] and d not in short_done:
        print(f"[{ts}] SHORT ORB on {SYMBOL} below {row['or_low']:.2f}")
        short_done.add(d)

print("✅ Done. This demo only prints breakout alerts.")
