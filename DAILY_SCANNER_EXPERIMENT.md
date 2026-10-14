# Experiment: Kunal's daily chart as the day-trade scanner

> Written 2026-10-14 **before** running it. The rules and the pass mark below don't change after we see
> results. If it fails, we stop hunting for a day-trading edge (agreed with Hassan the same day).

## Why
- Every ORB and FPB day trade from the test year (Jul 2024 – Jun 2025) was kept only if, that morning,
  the stock's daily chart agreed with the trade. "Agreed" means:
  - one of Kunal's named setups (flag, flat top, bear flag, flat bottom) was ready, pointing the same way;
  - the shading (9 EMA vs 20-day average) was the right colour;
  - QQQ was on the right side of its 50-day average.
- With that filter, both strategies turned positive before costs (+0.13R a trade) but stayed negative
  after costs (ORB −0.10R, FPB −0.25R).
- The cause is the tight intraday stop. It sits 1.3–1.6% from the entry, so the normal cost of getting in
  and out (about 0.3–0.4% of the price) eats 23–38% of the risk on every trade.

## The rules (fixed)
1. **Entries:** exactly the ORB and FPB entries already tested (same stocks, same days, same entry
   price and time). Nothing about the entry is re-tuned.
2. **Scanner:** keep a trade only if the daily chart agreed with it that morning (the filter above, unchanged).
3. **New exit, the only change ("daily-chart day trade"):**
   - stop = **one daily ATR** from the entry (the stock's average daily range over the last 14 days),
     instead of the tight intraday stop;
   - no profit target: if the stop isn't hit, sell at **3:55 PM**;
   - simulated on 5-minute candles. If the stop is touched in the candle where we bought, it counts as hit (worst case).
4. **Costs** (same model as before):
   - entry 0.05% + 1 cent;
   - exit at the stop 0.20% + 1 cent;
   - exit at 3:55 PM 0.05% + 1 cent.
5. **Version B, after 4:05 PM:** the same, but only stocks with at least one news headline (Alpaca's news
   feed) between 4 PM the day before and 9:30 AM that morning.

## Pass mark (development year Jul 2024 – Jun 2025)
- **at least +0.10R a trade after costs, AND at least 7 of 12 months positive.**
- Checked separately for ORB entries and FPB entries.
- If either passes: one unchanged confirmation run on years the bot has never seen. Only a pass there counts.
- If neither passes (with or without news): stop.

## Results

**Version A (2026-10-14, `run_daily_scanner_experiment.py`): FAILS for both.** Output in `logs/daily_scanner/A_*`.

| Entries (daily chart agreed) | Trades | Old exit, after costs | New exit, before / after costs | Months up |
|---|---|---|---|---|
| ORB | 1,038 | −0.10R | +0.07R / **+0.03R** | 5 of 12 |
| FPB | 561 | −0.25R | −0.00R / **−0.05R** | 4 of 12 |

- The wider stop did what it was meant to: costs fell to about 0.04R a trade.
- But the edge before costs shrank too. The extra profit came mostly from the tight stops cutting losers.
- ORB's small plus comes from one month (April 2025, +31.8R); the other 11 months add up to about zero.

**Version B (news only):** runs after tonight's downloads.
