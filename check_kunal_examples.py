"""
First real test of the ORB rules: do they find Kunal's own marked trades?

Runs orb_strategy.py on the 19 ORB charts Kunal marked (ORB_RULES.md, section 13) with real Alpaca
price history, and compares where the bot sees the break with where his arrow is.
These are winners he picked to teach with, so this only shows whether the bot RECOGNISES the
pattern. It says nothing about how often ORB makes money; that is the big backtest's job.

    .venv\\Scripts\\python.exe -X utf8 check_kunal_examples.py

The first run downloads about two months of 5-minute and one month of 1-minute candles per stock,
plus QQQ (a few minutes; refuses to run during market hours, see alpaca_history.py). Later runs read
from disk. Writes logs/orb_checks/kunal_examples.csv.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from alpaca_history import get_bars, regular_hours
from orb_strategy import OrbSettings, day_context, find_orb, simulate_trade

# chart number, stock, date, Kunal's direction, candles where his arrow / break is (as read from his chart)
EXAMPLES = [
    (1, "SOXL", "2025-04-24", "long", (3, 3)),
    (2, "TEM", "2025-05-08", "long", (5, 5)),
    (3, "TSSI", "2025-05-16", "long", (6, 6)),
    (4, "RDW", "2025-05-27", "long", (4, 5)),
    (5, "SOUN", "2025-05-27", "long", (4, 6)),
    (6, "RKLB", "2025-05-27", "long", (6, 6)),
    (7, "BBAI", "2025-05-27", "long", (4, 4)),
    (8, "TMC", "2025-07-24", "long", (4, 5)),
    (9, "ACMR", "2025-07-28", "long", (4, 4)),
    (10, "PI", "2025-07-31", "long", (4, 4)),
    (11, "TKR", "2025-07-30", "short", (6, 6)),
    (12, "SMG", "2025-07-30", "short", (3, 3)),
    (14, "PEW", "2025-08-15", "short", (7, 7)),
    (15, "ORCL", "2025-08-19", "short", (3, 3)),
    (16, "UPST", "2025-08-19", "short", (3, 3)),
    (17, "PLTR", "2025-08-19", "short", (3, 3)),
    (18, "DKNG", "2025-09-30", "short", (3, 3)),
    (19, "DOCU", "2025-09-30", "short", (3, 3)),
    (20, "KC", "2025-03-20", "short", (11, 13)),
]
TOLERANCE = 1     # candles: reading his small screenshots can be off by one


def run_one(symbol, day):
    five = regular_hours(get_bars(symbol, day - timedelta(days=45), day, "5Min"))
    minutes = regular_hours(get_bars(symbol, day, day, "1Min"))
    qqq = regular_hours(get_bars("QQQ", day, day, "5Min"))
    today, before = five[five.index.date == day], five[five.index.date < day]
    ctx = day_context(before, qqq)
    closes5 = five[five.index.date <= day].close
    pattern = find_orb(today, ctx, OrbSettings.pattern_only())     # where the bare pattern breaks
    signal = find_orb(today, ctx)                                   # the real decision, all filters on
    result = simulate_trade(signal, minutes, closes5) if signal.status == "trade" else None
    what_if = simulate_trade(pattern, minutes, closes5) if pattern.status == "trade" else None
    return ctx, pattern, signal, result, what_if


def main():
    rows, notes = [], []
    print(f"\n{'#':>2}  {'Stock':5} {'Date':10}  {'Kunal':11} {'Bot sees':17} {'Same?':5}  "
          f"{'Decision':8} {'Entry':>8} {'Stop':>8} {'Risk':>5}  Result")
    for num, symbol, day_text, direction, (lo, hi) in EXAMPLES:
        day = date.fromisoformat(day_text)
        kunal = f"{direction} c{lo}" + (f"-{hi}" if hi != lo else "")
        try:
            ctx, pattern, signal, result, what_if = run_one(symbol, day)
        except Exception as error:      # one bad download must not stop the others
            print(f"{num:>2}  {symbol:5} {day_text}  {kunal:11} ERROR: {error}")
            rows.append({"chart": num, "stock": symbol, "date": day_text, "error": str(error)})
            continue
        seen = (f"{pattern.direction:5} c{pattern.candle} {pattern.time:%H:%M}" if pattern.candle
                else f"{pattern.direction or '-':5} no break")
        same = (pattern.direction == direction and pattern.candle
                and lo - TOLERANCE <= pattern.candle <= hi + TOLERANCE)
        if signal.status == "trade":
            decision, shown, r = "TRADE", signal, result.r
            outcome = f"{r:+.1f}R  ({', '.join(e[3] for e in result.exits)})"
        else:
            decision, shown, r = signal.status, pattern, None
            outcome = f"(if traded: {what_if.r:+.1f}R)" if what_if else ""
            notes.append(f"#{num} {symbol}: " + "; ".join(signal.reasons))
        risk_pct = shown.risk / shown.entry * 100 if shown.entry else 0
        print(f"{num:>2}  {symbol:5} {day_text}  {kunal:11} {seen:17} {'yes' if same else 'NO':5}  "
              f"{decision:8} {shown.entry:8.2f} {shown.stop:8.2f} {risk_pct:4.1f}%  {outcome}")
        rows.append({"chart": num, "stock": symbol, "date": day_text, "kunal_direction": direction,
                     "kunal_candle": kunal, "bot_direction": pattern.direction, "bot_candle": pattern.candle,
                     "bot_time": f"{pattern.time:%H:%M}" if pattern.time is not None else "",
                     "same_as_kunal": bool(same), "decision": decision, "reasons": "; ".join(signal.reasons),
                     "entry": round(shown.entry, 4), "stop": round(shown.stop, 4), "risk_pct": round(risk_pct, 2),
                     "result_r": r, "if_traded_r": what_if.r if what_if else None,
                     "gap_pct": round(signal.gap_pct, 2), "daily_atr_pct": round(ctx.atr_pct, 2),
                     "yesterday_high": ctx.prev_high, "yesterday_low": ctx.prev_low})

    table = pd.DataFrame(rows)
    out = Path(__file__).resolve().parent / "logs" / "orb_checks"
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "kunal_examples.csv", index=False)

    ok = table[table.get("error").isna()] if "error" in table else table
    trades = ok[ok.decision == "TRADE"]
    print(f"\nPattern found where Kunal marked it (same direction, within {TOLERANCE} candle): "
          f"{int(ok.same_as_kunal.sum())} of {len(EXAMPLES)}")
    print(f"Passed every filter (the bot would have traded it): {len(trades)} of {len(EXAMPLES)}")
    if len(trades):
        print(f"Those trades: {int((trades.result_r > 0).sum())} up, {int((trades.result_r <= 0).sum())} "
              f"flat or down, average {trades.result_r.mean():+.2f}R (before slippage and fees)")
    if notes:
        print("\nWhy the others were skipped:")
        for line in notes:
            print("  " + line)
    print("\nReminder: these are winners Kunal chose to show. This checks recognition, not profitability.")
    print(f"Saved: {out / 'kunal_examples.csv'}")


if __name__ == "__main__":
    sys.exit(main())
