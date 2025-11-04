# MINI ORB BACKTEST (5m, first 5m range, simple PnL)
import pandas as pd, numpy as np, yfinance as yf
from datetime import time

SYMBOL   = "AAPL"
PERIOD   = "30d"      # more days = more trades
INTERVAL = "5m"
TZ       = "America/New_York"
RISK    = 100.0      # fixed $ risk per trade
ATR_P    = 14

def load_data(sym=SYMBOL):
    df = yf.download(sym, period=PERIOD, interval=INTERVAL, progress=False)
    # handle multiindex columns
    if isinstance(df.columns, pd.MultiIndex):
        try: df = df.xs(sym, axis=1, level=1, drop_level=True)
        except Exception: df = df.droplevel(-1, axis=1)
    df = df.rename(columns=lambda c: str(c).strip().lower().replace(" ", "_"))
    df = df[["open","high","low","close","volume"]].dropna()
    df.index = (df.index.tz_localize("UTC").tz_convert(TZ) if df.index.tz is None else df.index.tz_convert(TZ))
    df["date"] = df.index.date
    return df

def atr(df, n=ATR_P):
    pc = df["close"].shift(1)
    tr = pd.concat([(df["high"]-df["low"]).abs(),
                    (df["high"]-pc).abs(),
                    (df["low"]-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def run(df):
    # Opening Range = first 5m bar (simple for now)
    open_t, or_end_t = time(9,30), time(9,35)
    or_mask = (df.index.time >= open_t) & (df.index.time < or_end_t)
    or_tbl = df[or_mask].groupby("date").agg(or_high=("high","max"), or_low=("low","min"))
    df = df.join(or_tbl, on="date")
    df["atr5"] = atr(df)

    # trade window: after OR, before 11:30
    last_t = time(11,30)
    df["in_window"] = (df.index.time >= or_end_t) & (df.index.time <= last_t)
    long_sig  = df["in_window"] & (df["high"] >= df["or_high"])
    short_sig = df["in_window"] & (df["low"]  <= df["or_low"])

    trades = []
    done_long, done_short = set(), set()

    for ts, r in df.iterrows():
        d = r["date"]
        if pd.isna(r.get("or_high")) or pd.isna(r.get("or_low")): 
            continue

        # LONG
        if long_sig.loc[ts] and d not in done_long:
            entry = float(r["or_high"])
            stop  = float(r["or_low"])
            R     = max(entry-stop, 1e-6)
            qty   = max(int(RISK/R), 1)
            # simple intrabar exit: TP at 1.5R, else stop, else close
            tp = entry + 1.5*R
            if r["high"] >= tp:
                out = tp
            elif r["low"] <= stop:
                out = stop
            else:
                out = float(r["close"])
            trades.append(qty*(out-entry))
            done_long.add(d)

        # SHORT
        if short_sig.loc[ts] and d not in done_short:
            entry = float(r["or_low"])
            stop  = float(r["or_high"])
            R     = max(stop-entry, 1e-6)
            qty   = max(int(RISK/R), 1)
            tp = entry - 1.5*R
            if r["low"] <= tp:
                out = tp
            elif r["high"] >= stop:
                out = stop
            else:
                out = float(r["close"])
            trades.append(qty*(entry-out))
            done_short.add(d)

    trades = np.array(trades) if trades else np.array([0.0])
    winrate = float((trades>0).mean())
    pf = float(trades[trades>0].sum() / (abs(trades[trades<0].sum())+1e-9)) if (trades<0).any() else float("inf")
    print({
        "symbol": SYMBOL,
        "trades": int(len(trades)),
        "winrate": round(winrate,3),
        "profit_factor": round(pf,2),
        "total_pnl": round(float(trades.sum()),2),
        "avg_trade": round(float(trades.mean()),2),
    })

if __name__ == "__main__":
    data = load_data()
    run(data)
