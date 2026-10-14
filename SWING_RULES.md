# SWING RULES (Kunal's daily-chart setups)

> Status: **DRAFT 2 (2026-10-14)**, written by Claude for Hassan to confirm. Draft 2 = after checking the
> rules against Kunal's own setup-vault charts (section 10). Until Hassan says
> otherwise, the [Proposed] defaults below are what the code tests (same deal as ORB: "if nothing
> in the course says otherwise, the defaults are OK").
> Sources: Bulls Bootcamp swing classes **74** (breakout trading, flag breakouts, base breakout,
> bear flags), **76** (scanning routine), **77** (breakouts, flag breakout, base breakout 2, shorting
> stocks), **78** (intro + market cycle, trends, flat top breakout, scanning routine), and
> **20 charts from Kunal's School "setup vault"** (section 11). All rewritten in our own words.
> Transcripts are on Hassan's Desktop (`whisper\Release\`); charts in `private/charts/swing_kunal_examples/`.
> Never upload or quote them in this repo. There is no written rule book (no PDF): the classes and
> the setup vault are the only sources.
>
> Swing trading is a **separate strategy** from FPB and ORB: trades last days to weeks, decisions
> are made once a day after the close, and the orders wait at the broker. Nothing here changes the
> live FPB bot.

**Tags:**
- **[Kunal 74, 77]**: in the course (class numbers). "scan 76/78" = his scanning classes.
- **[Vault]**: seen in his setup-vault charts, not said in a class.
- **[Proposed]**: NOT in the course. Claude picked a number so a program can measure the rule. Needs your OK.
- **[Project]**: our own testing rules, not Bootcamp rules.

---

## 0. Words used here (one line each)

| Word | Meaning |
|---|---|
| Daily candle | One bar = one trading day (open, high, low, close). All swing rules use daily candles. |
| Swing trade | A trade held for days to weeks, not closed the same day. |
| 9 EMA | Average of the last 9 daily closes that reacts quickly. Kunal's short-term trend and the stop. |
| 20 / 50 / 200 SMA | Plain averages of the last 20 / 50 / 200 daily closes: medium and long-term trend. |
| Bone zone | Kunal's shading between the 9 EMA and the 20 SMA: green = 9 above 20 (uptrend), red = below (downtrend). |
| ATR | Average True Range over 10 days: how much the stock normally moves in a day, in dollars. |
| R | The risk per share: entry price minus stop price. "3R" = a profit three times that. |
| Breakout / breakdown | Price goes above a ceiling (long) / below a floor (short). |
| Test | A time the price came up to the ceiling (or down to the floor) and turned back. |
| Pole / flag | Pole = the fast move up; flag = the quiet sideways days right after it. |
| Base | A long sideways period (a month to years) under a ceiling or above a floor. |
| Distribution / accumulation | Big selling (red days on heavy volume) / big buying (green days on heavy volume). |
| QQQ | A fund that tracks the Nasdaq-100: Kunal's "the market". |

---

## 1. The idea in one paragraph

Kunal trades trends. Stocks don't rise smoothly: they jump for 3–7 days, rest, and jump again. The
trade is to buy a trending stock **as it comes out of a tight rest**, with the 9 EMA right under the
breakout so the stop is close, and to hold for the next burst. Shorts are the mirror image: a
falling stock rests, then breaks down. Because the stop is a few percent away and the move can last
days, trading costs are a small part of each trade (the intraday ORB/FPB problem). **[Kunal 74, 77, 78]**

---

## 2. The five questions before every trade **[Kunal 74, 77, 78]**

Kunal treats each trade like building a case in court. All five must be yes (shorts: the mirror image).

1. **Is there a named pattern?** No name, no trade (flag, flat top, base breakout, bear flag, flat bottom).
2. **Volume.**
   - Liquid: at least 1 million shares a day on average. **[Kunal 74, 77, 78]**
   - No distribution in the 5 days before the breakout: no big red days with more volume than the green days.
     Shorts: no accumulation (no big green days). **[Kunal 74, 77, 78]**
   - Bot: distribution = the heaviest red day of those 5 had more than 1.5× the volume of the heaviest
     green day (his idea: selling volume much bigger than buying volume). **[Proposed]**
3. **Do the moving averages support the trade?** The 9 EMA is rising and sits right under the breakout
   level. If the 9 EMA is far below the line, the setup is too loose and breakouts tend to fail.
   - Bot: breakout level minus 9 EMA at most **2 × ATR**, and the 9 EMA rose yesterday. **[Proposed]**
     (Draft 1 used 1 × ATR; on his own vault charts the gap is 1.0–1.7 × ATR on the breakout day.)
4. **Am I trading with the trend?** Bone zone green for longs, red for shorts. Ideal: 9 > 20 > 50 > 200. **[Kunal 74, 77, 78]**
5. **Is the possible reward worth the risk?** The stock's last big move should be many times the risk. Kunal
   assumes he will only catch part of it, and still wants several times the risk.
   - Bot: the pole (flags) or the run into the base (flat tops) at least **2 × the risk** (class 77: you
     need about $2 for each $1 risked). Draft 1 used 4×; his vault charts measure 2.4–4.3×.

Also true of every breakout **[Kunal 74, 77, 78]**:
- **At least 3 tests** of the level for flat tops and bases (two touches are not enough for him).
- **Not after 3 green days in a row** into the breakout: by then the stock has usually spent its burst.
  Bot: skip if the 3 days before were all up days.
- **Volume grows after the breakout** (he likes 2× normal or more). It confirms; it is never the reason
  to buy, and big volume BEFORE the breakout means you're late. The bot can't know the day's volume when
  it buys, so it records it for research but doesn't filter on it. **[Proposed]**
- **Don't wait for the candle to close:** buy as it crosses, or a big day ruins the risk. **[Kunal 74]**

---

## 3. The market **[Kunal 76, 78]**

- QQQ's 50-day average is the line in the sand for swing and day traders: above it, gaps follow
  through and breakouts work; below it, gap-downs and failed breakouts, so the watchlist needs more shorts.
- Market cycle: accumulation → run-up → distribution → run-down. Flags work best in the run-up and
  coming out of accumulation; in distribution they get sold into. Breakouts are a run-up trade.
- Bot: **longs only when QQQ closed above its 50-day average the day before; shorts only when below.**
  The line is Kunal's; using it as an on/off switch is **[Proposed]**. The other side is measured too.

---

## 4. Which stocks **[Kunal scan 76, 78; 74, 77]**

- Price **$5 or more**, average volume **1 million shares or more** (his scan filters).
  - He notes swing trading needs less liquidity than day trading.
  - He also stopped students from trading cheap small caps.
  - Some of his own base-breakout and pullback examples are under $5 (XNET, QUBT, LAES). The bot keeps $5 for now.
- He scans for momentum first (liquid gainers, top losers, stocks above all their averages, hot
  sectors), then sorts what he finds into patterns. The bot checks every liquid stock every day for
  the patterns (research mode).
- He sells before earnings **[Kunal 77]**. We have no earnings dates in the price data, so this is
  NOT applied yet (some test trades will hold through earnings).

---

## 5. The setups

### 5a. Flag breakout (bull flag) **[Kunal 74, 77; Vault: MU, LUMN, SNDK, ANF, CIFR]**
- **Pole:** the stock rises 10% or more, in one day or a few days.
  - Bot: the pole's top is at least 10% above the lowest low of the 10 days before it, and is the highest point of those days.
- **Flag:** 3–10 days of quiet sideways movement after the top. Volume and day-to-day swings shrink;
  the 9 EMA catches up under the price.
  - Bot: the flag starts on the first day within 0.5 ATR of the top, so a candle poking a little above
    the earlier tops doesn't restart the count (as on MU).
  - Bot: the flag stays in the upper half of the pole. **[Proposed]**
  - Bot: the last 3 days before the break trade less volume than the pole did.
- **Entry:** when the price breaks the flag's line. Like Kunal, the bot connects the highs: a line from
  the flag's top through the later highs, flat or sloping down (ANF, SNDK, CIFR), every flag day under it.
- **Stop:** under the daily 9 EMA, with a small cushion. Bot: 9 EMA − 0.1 × ATR. **[Kunal 74/77; buffer Proposed]**

### 5b. Flat top breakout **[Kunal 74, 77, 78; Vault: RVI, TTMI, PR, RGTI, CDE, FUTU]**
- A stock that has been trending up rests **a month or more** (often 2–4 months) under a flat ceiling,
  tests it **3+ times**, and the 9 EMA curls up under it. A flag is just a short flat top.
- Bot:
  - ceiling = highest high of the last ~6 months (120 trading days). Draft 1 used a year, but on PR,
    LUMN and RGTI an older, unrelated peak was higher than Kunal's line;
  - tests = separate visits within 0.5 × ATR of the ceiling (days in a row count once), 3 or more;
  - the base lasts at least 20 trading days from the first test;
  - the stock rose 20%+ in the 60 days before the base;
  - the base is no deeper than 35% below the ceiling. **[test spacing, 20% and 35% Proposed]**
- Entry and stop as for flags. RGTI's ceiling slopes down; v1 uses flat ceilings only.

### 5c. Shorts: bear flag and flat bottom breakdown **[Kunal 74, 77]**
- Mirror images:
  - bear flag: a drop of 10%+, then 3–10 quiet days, short the break of the flag's low;
  - flat bottom: a falling stock sits on a floor for a month+ with 3+ tests, short the break.
- Stop above the 9 EMA. Kunal gives shorts more room: about half to a full day's ATR. Bot: 9 EMA + 0.5 × ATR.
- Week before: no accumulation. Bone zone red, 9 EMA falling.
- Stocks fall faster than they rise, then snap back toward the bone zone, so he takes profits quickly
  on shorts. Most short opportunities come in bear markets.
- The live bot must check the stock can be borrowed (easy-to-borrow); history can't show that.

### 5d. Base breakout **[Kunal 74, 77; Vault: BAND, OUST, MP, XNET]**: phase 2, not in the first test
- After a crash of 50% or more, a long sideways base (months to years); the averages flatten and turn up;
  3+ tests of the base top; breakout on rising volume. He uses weekly charts.
  - The first pullback that holds confirms the new trend.
  - The longer the base, the bigger the move.
- He does only a handful a year, and it needs years of history. It comes after the first test.

### 5e. Pullbacks to the 9 EMA / 20 SMA **[Vault: ANF, QUBT, LAES, GOOGL]**: phase 2
- His other way to buy: buying a dip in an uptrend, not a breakout. The classes so far only mention
  it (light volume on the dip = buyable; stochastics matter more for pullbacks). **Needs his pullback
  class before it can be written as rules.**

---

## 6. Getting out **[Kunal 74, 77]**

- **Stop under the 9 EMA**, raised each evening as the 9 EMA rises, never lowered. If price breaks the
  9 EMA, you're out.
- **Sell half at 3 × the risk**, then the stop can't be below the entry price. (Class 77: at about 3:1 he
  sells half and moves the stop to his buy price; class 74: start selling at 2:1–3:1.)
- **The rest:** trail under the 9 EMA until it's hit. No time limit **[Proposed]**: moves come in 3–7 day
  bursts, so most trades should end within a few weeks.
- Not in v1: selling some when price is far outside the upper Bollinger band or stochastics are very
  high **[Kunal 77]**, and reloading on later pullbacks.

### 6b. Two other readings, tested side by side **[Kunal 74, 77, 78]**
- **Buy at the close instead of during the day.**
  - Class 78: swing traders often buy at the end of the day, for confirmation.
  - Bot: buy at the close only if the day closed past the line on at least 2× normal volume (classes
    74/77: he wants 2:1 volume on a breakout).
  - Stop under that day's 9 EMA.
- **"Breaks the 9 EMA" = a daily close past it.**
  - Bot: sell at the close of a day that closes past the 9 EMA, ignoring dips during the day.
  - The first stop and the breakeven stop stay as real stop orders.

---

## 7. How the test fills orders (daily candles only) **[Project]**

- **Entry:** a buy-stop order one cent past the breakout line. If the stock opens past the line, it fills at the open.
- **Unclear entry days:** a daily candle doesn't show the order of events. If the low on the breakout day
  also reached the stop, the test counts a **loss** (worst case). These days are counted, and a best-case
  total is shown next to it.
- **Unclear later days:** if the stop and the 3R target are both touched on the same later day, the
  stop counts first (worst case).
- **Gaps:** a gap through the stop fills at the open.
- **Slippage** (same model as ORB):
  - stop-type fills (entries at the line, stop exits): 0.20% + 1 cent;
  - fills at the open: 0.05% + 1 cent;
  - target (limit) fills: 1 cent.
- One trade per stock at a time.

---

## 8. Test plan **[Project]**

1. **Development year** July 2024 – June 2025, from the daily prices already on disk. Choices are made here only.
2. **Kunal's charts** (section 11): the finder should spot his marked breakouts. This is recognition
   only, since they are hand-picked winners. Most are from after June 2025, so this needs a
   download after 4:05 PM.
3. **Holdout** July 2025 – September 2026, run once, only if the development year shows a clear edge after costs.
4. Every qualifying signal is measured (research mode). Then a **realistic account**:
   - up to 5 positions, 1% risk each, at most 20% of the account in one stock;
   - compared with simply holding QQQ over the same months. If it can't beat that after costs, it isn't worth doing.
5. **Survivorship bias:** stocks that were delisted are missing, which flatters longs a little.

---

## 8b. Results so far (development year July 2024 – June 2025, every liquid US stock)

| Version | Trades | Per trade before / after costs | Months up | 5-position account | Holding QQQ |
|---|---|---|---|---|---|
| Original rules (buy-stop at the line, stop under the 9 EMA) | 6,664 | −0.03R / −0.15R | 3 of 12 | −33% | +14.5% |
| Buy at the close on 2× volume | 253 | +0.06R / +0.01R | 5 of 12 | +5.7% | +14.5% |
| Exit on a close past the 9 EMA | 6,347 | −0.03R / −0.13R | 2 of 12 | −32% | +14.5% |
| Both | 251 | −0.02R / −0.06R | 6 of 12 | −2.2% | +14.5% |

- No version has a clear edge, and none comes close to just holding QQQ.
- Costs are much smaller than in day trading (0.04–0.12R a trade), so costs are no longer the reason:
  the setups themselves don't pay.
- In the original rules, most trades end at the 9 EMA stop within about 5 days; only about 1 in 8 reaches 3R.
- Output files: `logs/swing_trades/dev_v2_*` (kept on the PC only).

**Extra out-of-sample check, 2021–2023 (decided before running, settings unchanged): NO EDGE either.**

| Version | Trades | Per trade before / after costs | Months up | 5-position account | Holding QQQ |
|---|---|---|---|---|---|
| Original rules | 18,662 | −0.08R / −0.20R | 4 of 36 | −45% (worst drop 56%) | +32% |
| Buy at the close on 2× volume | 531 | −0.08R / −0.13R | 12 of 36 | −9% (worst drop 37%) | +32% |

- The short slice that looked good in the development year (+0.26R) lost **−0.27R** here (200 trades, 5 of 22
  months up), even through the 2022 crash. It was luck.
- One small slice was positive (flag + flat top together, 124 trades, +0.12R). That was noticed after looking
  and is exactly the kind of result we don't chase.
- Output files: `logs/swing_trades/early_2021-2023_*`. The swing setups are closed as a strategy.

## 9. Open questions for Hassan
1. Half at **3R** (his class 77 words) or 2R?
2. Keep the **$5** minimum (his scan) although some of his examples are under $5?
3. Flags: is a flat line at the pole top OK for the first test (his lines often slope down)?
4. More material, most useful first:
   - the pullback classes (9 EMA / 20 SMA);
   - the selling class;
   - bear flag and flat bottom examples from the setup vault (with dates);
   - more flat top / flag vault charts with the date visible.

---

## 10. Review notes
- 2026-10-14, draft 1: written from the classes listed at the top and 20 setup-vault charts.
- 2026-10-14, draft 2: checked against his 11 breakout charts with Yahoo prices. This is recognition only:
  they are hand-picked winners, and most are from after June 2025.
  - Draft 1 was too strict. Changes:
    - flag lines can slope;
    - a flag starts within 0.5 ATR of its top;
    - the ceiling is the 6-month high, not the 1-year high;
    - tests count separate visits to the line;
    - the 9 EMA may be up to 2 ATR under the line;
    - the move needs to be 2× the risk;
    - distribution = red volume 1.5× green volume;
    - flag volume is measured on the last 3 days.
  - After the changes, 7 of 11 are found at or near his marked day and line, passing every check
    (PR, ANF, LUMN, SNDK, FUTU, CIFR, MU).
  - 2 are found but break one of his own rules: TTMI (3 green days in a row) and RVI (under 1M shares a day).
  - 2 are missed: RGTI (sloped ceiling) and CDE (one wick above his line raised ours).
- 2026-10-14, decided BEFORE running: one extra out-of-sample check on **2021-01 to 2023-12**, never looked
  at and including the 2022 bear market.
  - Same code and settings, unchanged, for the original rules and the buy-at-the-close version.
  - The 2025-07+ holdout stays untested.
- 2026-10-14, noticed AFTER looking (so it is only a question, not a finding): in the development year,
  shorts bought at the close on 2× volume made +0.26R a trade after costs, on only 87 trades. It counts
  only if the same slice is positive in tonight's unchanged 2021–2023 run (which includes the 2022 crash).

---

## 11. Kunal's setup-vault charts (`private/charts/swing_kunal_examples/`)

| # | Setup (vault folder) | Stock | Breakout (read from the chart, approximate) |
|---|---|---|---|
| 1 | Flat top | RVI | ~$36, early May 2026 (fund listed March 2026) |
| 2 | Flat top | TTMI | ~$113, 2026 (date not visible) |
| 3 | Flat top | PR | ~$15.2, late January 2026 |
| 4 | Flat top (sloped ceiling) | RGTI | ~$18, September 2025 |
| 5 | Flat top | CDE | ~$9.7, early August 2025 |
| 6 | Flat top | FUTU | ~$128, July 2025 |
| 7 | Bull flag | MU | ~$535, early May 2026 |
| 8 | Bull flag | LUMN | ~$7.4, late October 2025 |
| 9 | Bull flag | SNDK | ~$135–140, mid October 2025 |
| 10 | Bull flag (sloped) | ANF | ~$97, ~December 8, 2025 |
| 11 | Bull flag (sloped) | CIFR | ~$8, early September 2025 |
| 12 | Base breakout (weekly) | BAND | $30, late April 2026 |
| 13 | Base breakout (weekly) | OUST | ~$16–17, mid 2025 |
| 14 | Base breakout (weekly) | MP | $30, July 2025 |
| 15 | Base breakout (weekly) | XNET | ~$2.3, early 2025 |
| 16 | 9 EMA pullback | ANF | ~$95, December 2025 |
| 17 | 9 EMA pullback | QUBT | ~$3, November 2024 |
| 18 | 9 EMA pullback | LAES | ~$2.5, December 2024 |
| 19 | 20 SMA pullback | GOOGL | (no arrow) early 2026 |
| 20 | 20 SMA pullback | QUBT | (no arrow) December 2024 |

The vault has 35 flat tops, 33 bull flags, 27 base breakouts, 17 9-EMA pullbacks and 19 20-SMA pullbacks.
