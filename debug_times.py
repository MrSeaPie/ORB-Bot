import yfinance as yf
import pandas as pd

# Download AAPL
df = yf.download("AAPL", period="5d", interval="5m", progress=False)

# Handle multiindex
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# Normalize columns
df = df.rename(columns={c: c.lower() for c in df.columns})

print("="*60)
print("CHECKING ACTUAL BAR TIMES")
print("="*60)

# Look at one recent day
recent_day = df.index[-1].date()
day_df = df[df.index.date == recent_day]

print(f"\nDate: {recent_day}")
print(f"Total bars: {len(day_df)}")
print(f"\nIndex timezone: {day_df.index.tz}")
print(f"\nFirst 10 bars of the day:")
print(day_df.head(10)[['open', 'high', 'low', 'close']])

# Show what time the first bar is
if len(day_df) > 0:
    first_bar_time = day_df.index[0].time()
    print(f"\n⭐ First bar time: {first_bar_time}")
    print(f"   (We're looking for 9:30, but getting {first_bar_time})")