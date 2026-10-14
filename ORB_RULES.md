# ORB RULES (Opening Range Breakout)

> Status: **Defaults confirmed by Hassan on 2026-10-13** ("if nothing in the course says otherwise,
> the defaults are OK"). These are the rules the ORB code is built and tested on. The backtest may
> still change the [Proposed] numbers.
> Sources: Kunal's ORB lessons, Bulls Bootcamp classes **71, 72, 73, 74, 76, 77**; his two scanning
> classes (**scan 76, scan 78**); two webinars by **Armando**, a guest trader in Kunal's group; and
> **20 of Kunal's marked charts** (10 long, 10 short; section 13). All rewritten in our own words.
> Transcripts and charts stay on the PC only (`private/`), never in this repo. Section 12 lists what
> changed in each draft.
>
> ORB is a **separate strategy** from FPB: its own files, logs, Alpaca paper account and test
> results (section 9). The FPB bot is not changed by any of this.

**Every rule has one of these tags:**
- **[Kunal 72, 74]**: in the course. The numbers are the classes where he says it ("scan 76/78" =
  his scanning classes).
- **[Armando]**: from the guest trader's webinars: course-adjacent, not Kunal himself.
- **[Proposed]**: NOT in the course. Claude picked a number so a bot can measure the rule. Needs your OK.
- **[Project]**: our own testing rules (from `CLAUDE.md`), not Bootcamp rules.

---

## 0. Words used here (one line each)

| Word | Meaning |
|---|---|
| Candle | One bar on the chart. Here always a **5-minute** candle (open, high, low, close for those 5 minutes). |
| Opening candle | The first 5-minute candle of the day, 9:30–9:35 AM New York time. |
| The lid / the floor | The **highest** price of the first two candles (for a long) / the **lowest** (for a short). |
| Long / short | Long = buy, hoping it goes up. Short = sell first, hoping it goes down, buy back later. |
| VWAP | "Volume-weighted average price": the average price everyone has paid today. Starts fresh each morning. |
| 9 EMA | A moving average of the last 9 candles that reacts quickly to new prices. Used to follow a trend. |
| R | Your risk per share: entry price minus stop price. "3R" = a profit three times that size. |
| Daily ATR | How much the stock normally moves in a day (average daily high-to-low range). "ATR%" = that as a % of the price. |
| Gap | The stock opens well above (gap up) or below (gap down) yesterday's close. |
| Float | How many shares can actually be traded. Small float = wilder moves. |

---

## 1. The idea in one paragraph

A stock that has a reason to move makes a quick move at the open, then **pauses sideways for a few
candles under the high of its first candles**. When the price breaks above that high, you buy. The
stop goes just under VWAP. You take profits quickly, because this is a morning-only trade that
usually runs out of steam around 10:30–11:00. Shorts are the same trade in reverse.

---

## 2. When: mornings only

- 5-minute candles. 1- and 2-minute charts give more fake-outs; he uses them only rarely. **[Kunal 71, 72, 73, 74]**
- The day has three parts: the open (9:30–11:00, fast), midday (11:00–1:00, slow), the close
  (1:00–4:00). ORB is an **open** pattern only; at midday it doesn't work. **[Kunal 71, 72, 73, 77]**
- Best in the first 30 minutes. **No new ORB entries after 11:00 AM.** **[Kunal 72, 74, 76, 77]**
- Earnings season brings the most ORBs, both up and down. **[Kunal 71, 77]**

---

## 3. Which stocks

**A stock needs one of three reasons to be traded at all. [Kunal 72, 73, 74, 76, 77]**
1. **News:** earnings or a press release. His scan: moved **3% or more before the open** on at least
   **50,000 shares** of pre-market volume ($1–$5 stocks: 500,000+). **[Kunal 71, 72, 76]**
2. **A good daily chart pattern:** e.g. flat-top breakout or flag (longs); breakdown or bear flag (shorts).
3. **A "go-to" stock:** a stock in a strong trend, with big volume and big daily moves, traded often while it stays hot.

**It must be a stock that moves.** He prefers stocks with a history of big moves (former momentum stocks);
one that moves about 1% a day isn't for this. **[Kunal 71]**
- Bot version: **daily ATR at least 2% of the price** (average of the last 14 days, before the trade day).
  The course draws the line here: about 1% a day is a no **[Kunal 71]**, 1.75% is a no **[Armando's
  oil-stock example]**, and 2.1% was fine (Kunal's TKR short). Draft 4 said 2.5%; the real-data check
  showed that would have rejected his TKR trade (section 12).

**"Look left": the daily chart must not fight the trade.** **[Kunal 71, 76]**
- The easiest longs are clearing the previous days' price ranges. **[Kunal 71]** Armando says ORBs
  work best above yesterday's high (longs) or below yesterday's low (shorts). **[Armando]**
  - But it is **not a rule**: Kunal's own ORCL and UPST shorts broke out while still inside
    yesterday's range, and both worked. "Above yesterday's high / below yesterday's low" is a
    backtest option. **[Project]** For now the bot has no look-left filter; the backtest tries the
    three versions in this section.
- A gap up that runs straight into the 200-day average, or into a messy old price range, tends to
  fail even on great news. **[Kunal 71, 76]** A great 5-minute setup on a messy daily chart loses to
  an average setup on a clean one. **[Kunal 71]**
  - Tested as backtest options, not rules yet: no 200-day average within 3% above a long; no
    3-month high within 5% above a long. **[Proposed]**
- For shorts, a bearish daily chart helps, but it is **not required**: ORCL and PLTR were in strong
  daily uptrends and still gave clean ORB shorts on a weak market day (section 13).

**Other stock notes:**
- No gap is required; any price, any company size. **[Kunal 72, 73, 74, 77]** His charts range from a
  $5 small cap (PEW) to Oracle (ORCL). Several opened about flat and moved in the first candle (TEM,
  TMC, ORCL, UPST). So a pre-market gap list alone misses ORBs.
- Small float = bigger, wilder moves; big float = slower, steadier. Affects size, not a filter. **[Kunal 71, 72, 76]**
- He doesn't read the news story itself; the chart decides. **[Kunal 71, 76]**
- He treats pre-market highs and lows as noise unless there was news. **[Kunal 76]**
- His morning scans: liquid gainers (his screen shows price over $2), top losers (for shorts), and his
  go-to stocks. Then he narrows to the best **4–6** to watch, because a person can't watch more.
  **[Kunal 74]** A bot can watch more. The backtest compares "top 6" with "all candidates". **[Project]**
- Our scanner today: only 3 of the 10 long-chart stocks are in `universe.txt`, and its $5 minimum
  drops BBAI. It could not have found most of his examples.

**The market:**
- He keeps QQQ (the Nasdaq fund) on screen and won't buy while the market is dropping hard. **[Kunal 72]**
- When the market keeps making new highs, stocks move cleanly; in a choppy market (a couple of days
  up, a couple down) only the very best charts work. **[Kunal 71]**
- In class 77 he seems to say longs in a hot market, shorts in a weak one (the audio is garbled
  there). His charts agree: four longs on one strong day (May 27, 2025), three shorts on one day when
  big tech names fell together (Aug 19, 2025).
- QQQ's **50-day average is his line in the sand**: above it, the market gaps up and breakouts
  follow through; below it, breakouts fail more and you need more shorts on the list. **[Kunal scan 76]**
- Armando's best months were when the market ground steadily up or down, his worst when it was stuck in
  a range. In a range, take profits faster and favour stocks with their own news. A stock with no
  news of its own that just moves with the Nasdaq should be traded in the Nasdaq's direction. **[Armando]**
- Bot version: skip new longs if QQQ is down more than **0.5%** since 9:30; skip new shorts if it's
  up more than 0.5%. **[Proposed]** This applies only to stocks **without** their own news, i.e. a gap
  under 3%. Kunal's warning is about buying just any stock while the market tanks, and Armando
  says stocks with their own news move regardless of the market. (His KC short, a China stock with a 4%
  news gap, fell while QQQ rose 1.3%.) The backtest also tries "longs only while QQQ is above its 50-day
  average, shorts only while below" **[Project]**. (The full "market weather" detector comes later.)

### 3b. ORB's own stock finder (from the scanning classes)

ORB gets **its own** stock finder in the ORB folder. The FPB scanner and its stock list are not
changed. Kunal stresses that there's no secret scan: he scans for heat (momentum, volume,
liquidity), not for one pattern, then looks through the charts. **[Kunal scan 76]**

**Who gets on the morning list** (any one of these, then the filters below):
1. **Gappers:** moved 3%+ up or down before the open, 50,000+ pre-market shares, price over $5. **[Kunal 71, scan 78]**
2. **Yesterday's movers:** closed up (or down, for shorts) 2%+ on 1 million+ shares, with about
   double the normal volume. These are his "good gainers" and "top losers" lists. **[Kunal scan 76, scan 78]**
3. **"Go-to" stocks:** Kunal keeps about 100 trending, big-range stocks he's traded over the past
   year and trims the list every quarter. **[Kunal scan 78]** We don't have his list, so the bot builds one by rule:
   - liquid: average volume 1 million+ shares a day
   - moves: daily ATR 2%+ of the price
   - trending: above its 9/20/50-day averages (or below them, for short candidates; his "trenders
     over MAs" scan)

   It starts with the 19 stocks from his charts. **[Proposed]**

**Filters for every stock:**
- **Liquid:** stocks trading only 200,000–400,000 shares a day are too thin to day-trade; he filters for
  1 million+. **[Kunal scan 76]** Armando wants 3–5 million: his losses piled up in stocks trading under
  5–10 million shares that day, his profits in stocks trading 10–25 million+. **[Armando]**
  - Bot version: average daily volume **1 million+** **[Kunal]**. Busier stocks rank higher. **[Armando]**
- **Moves enough:** an ORB only pays on a stock that can run 5–7%. On a quiet stock it breaks out
  0.5–1% and chops you up. His example: no ORBs on a $40 oil stock that moves 70 cents a day (under
  2%). **[Armando, quoting Kunal]** That backs the **daily ATR 2%+** rule.
- **Price:** his gapper list uses over $5 and his movers list over $2. Armando does best between $20
  and $200. Kunal warns that small caps are the quickest way to zero for a small account.
  **[Kunal scan 76, scan 78; Armando]**
  - Bot version: $5+ for gappers, $2+ for the other lists, as on his screens. **[Kunal]**
- **Not stretched:** a stock up five or more days in a row usually needs a rest first. **[Kunal scan 76]**
  The backtest tries this as an option for longs. **[Project]**
- **Has it moved like this before?** A stock that has never moved 10% in a day probably won't today.
  **[Armando; Kunal 71]** The ATR rule covers most of this.

**Narrowing down:** a person watches only the best 4–6 at the open. **[Kunal 74; Armando]**
Busier and more volatile stocks rank first. The backtest compares "top 6" with "all". **[Project]**

**Armando on ORBs specifically** (all match the rules above):
- ORBs work best above the previous day's high for longs and below the previous day's low for shorts.
- The stop goes at the nearest support: VWAP or the low of the opening candles.
- A stock that has already traded a big chunk of its normal daily volume in the first 15–20
  minutes, just as it reaches its ORB line, is a strong sign. (A backtest option.)
- Once a stock has used up most of its normal daily range without news, don't start new trades in
  it; take profits instead.

**Backtesting a stock finder honestly:** Alpaca's stock list only contains stocks that still exist.
Stocks that went bust or were bought out are missing, which makes old results look better than they
were ("survivorship bias"). We'll note this in every backtest result.

---

## 4. The long setup, step by step

1. **Direction: the stock gaps up on news, or pops up at the open.** **[Kunal 71, 74, 77]**
   - Bot version: a gap of **1%+** sets the direction (gap up = long, gap down = short). Without a gap,
     the opening candle decides; if it closed exactly where it opened, where it closed versus
     yesterday's close decides. **[Proposed]**
   - Draft 4 let the opening candle alone decide. Real data broke that on three of his charts: SOXL
     gapped up 8% but its first candle closed 8 cents lower; KC gapped down 4% with a slightly green
     first candle; UPST's first candle closed exactly where it opened. The new rule gets all 19 right.
2. **Sideways candles stay under the lid.** Any colour; a slow drift lower is fine. It should be a
   clean, obvious shelf: no up-down-up whipsaw. If you have to squint to find the range, it isn't an
   ORB. **[Kunal 72, 74, 76, 77]**
   - Kunal describes the line as the top of the first candle. **His charts:** where he drew the line, it sits at the
     high (or low, for shorts) of the **first two** candles (PI, TSSI, TKR, PEW, UPST, DOCU).
   - Bot version: **the lid = the highest price of the first two candles.** **[Proposed]**
   - His shelves are looser than his words: in TEM and RDW the 2nd candle poked above the 1st; in
     RKLB the 2nd candle was a big red drop and a shelf candle closed under VWAP; in TKR (short) the
     3rd candle bounced all the way back up. All are still his ORBs. So the bot must not be too strict
     here. Strict filters are what killed the Nov 2025 "Elite ORB".
   - No "skip if candle 2 goes past candle 1" rule: in TEM and DKNG the 2nd candle closed a hair past
     the 1st. The backtest tries a version that skips only if candle 2 closes past candle 1 by more
     than a quarter of candle 1's height. **[Project]**
3. **Earliest entry 9:40**, i.e. two candles finished, break during candle 3. **[Kunal 71, 72, 73, 74, 76, 77]**
   In every class he says both that the pattern needs at least three candles, with the third one
   allowed as the entry candle, and that at least two 5-minute candles must be finished before entry.
   - **His charts confirm it.** Longs broke on candle 3 once, mostly on candle 4, some on 5–6. Shorts
     broke on candle **3 in 6 of 9**. Waiting until 9:45 would have missed 7 of his 19 ORBs.
   - **Never buy during the first two candles.** Guessing the breakout early cost him more than any
     other mistake. **[Kunal 72, 73, 74, 76]**
   - A shelf can last much longer: his KC short broke around 10:30, after about 11 sideways candles.
     Any time up to 11:00 is fine. **[Kunal 77, 76]**
4. **Entry:** buy **as the price breaks above the lid**, not at the candle's close (a big breakout
   candle would leave you chasing). Latest 11:00. **[Kunal 76, 77]**
5. **Stop: just under VWAP.** He says it in nearly every class and is firm that other stops get hit;
   in class 74 he lost a trade by not using VWAP. **[Kunal 71, 72, 73, 76, 77]**
   - When VWAP sits right at the bottom of the shelf he sometimes uses the shelf's low instead (class 74),
     about the same spot. Once, on a short, he used the 9 EMA (class 71). The main rule is VWAP.
   - Bot version: stop = VWAP at entry minus **0.1%** of the price (about 5 cents on a $50 stock),
     kept there until the first profit is taken. **[Proposed]** The backtest also tries "under the shelf's low".
6. **Too far from VWAP? Skip.** The further the entry is from VWAP, the riskier the trade. **[Kunal 71, 72, 74, 76, 77]**
   (His only yardstick is roughly a finger's width on the chart.)
   - Bot version: measure it against **today's opening range** (lid minus the lowest price so far).
     Skip if the entry is more than **60%** of that range away from VWAP. **[Proposed]** In his charts it
     was about 15–50%. (Draft 2 used the 5-min ATR; at 9:40 that still includes yesterday's quiet
     candles, and it would have rejected his TSSI example.)
7. **Size:** decide the dollars you're willing to lose; shares = that ÷ R. Never oversize; stops fill
   a few cents worse than planned. **[Kunal 72, 77]**
   - **1% of the account** per trade. **[Proposed]** (Matches FPB. In a class 77 Q&A Kunal suggested
     about 1% while you're new, but the question isn't on the recording.)
   - No trade bigger than 50% of the account, as in FPB (`MAX_POSITION_PCT`). **[Proposed]**

## 5. The short setup: the same in reverse

Kunal teaches the short as the same trade flipped: drop, sideways, short the break, stop over VWAP.
**[Kunal 71, 72, 73, 74, 76, 77]** (class 76 says it in those words)
- The opening candle pushes **down**, but it doesn't need to be a big drop. **[Kunal 77]** **The floor
  = the lowest price of the first two candles**; the sideways candles stay above it.
- **Short as the price breaks below the floor.** Earliest 9:40, latest 11:00. Shorts tend to break
  early: candle 3 in 6 of his 9 short charts.
- Stop **just above VWAP**; skip if too far from VWAP.
- Bad-news gap-downs and bearish daily charts are the classic case, but his ORCL and PLTR shorts were
  stocks in daily uptrends falling on a weak market day.
- Shorts often fall faster than longs rise; a bad-news gap-down has few buyers. **[Kunal 73, 77]**
- The bot details (the 0.1% buffer, the 60% limit, "below yesterday's low") are **[Proposed]**, as for longs.

---

## 6. Getting out

ORB is a **quick trade made for the open**, not held all day; many last 15–20 minutes. **[Kunal 71, 74, 76, 77]**

What the course says:
- Once you're up **2:1 to 3:1**, sell some. 3:1 is the number he uses most. Sometimes he sells half
  to three-quarters right into the first spike. **[Kunal 71, 72, 73, 74, 76]**
- Then move the stop to your buy price (breakeven: you can't lose on the rest). **[Kunal 71, 73, 77]**
- Follow the rest with the **9 EMA**: get out when it breaks the 9 EMA. **[Kunal 71, 72, 73, 76, 77]**
  He trails by the chart and doesn't use automatic "-1%" trailing stops: they get hit too easily. **[Kunal 72]**
- His personal habit: sell half, then a quarter, keep a quarter for the 9 EMA, selling into every
  quick spike. But he tells students they don't have to sell his way. **[Kunal 71, 73, 74]**
- **Never add more shares** to an ORB trade. **[Kunal 74]**
- Other signs a move is done: the stock has already moved about its normal daily range (daily ATR)
  **[Kunal 72, 73]**; the 9 EMA flattens out **[Kunal 74]**; the trade sits going nowhere, and money
  stuck in a trade that isn't moving earns nothing **[Kunal 71]**.

Bot version (simple, fixed rules):

| When | Do this | Tag |
|---|---|---|
| Price reaches **3R** | Sell **half**. Move the stop to the entry price. | [Kunal] range 2–3R; 3R picked as his most-used number |
| After that | The other half follows the 9 EMA: sell when a 5-min candle **closes** past it. | [Kunal] 9 EMA; "closes" is [Proposed] |
| **11:30 AM** | Sell whatever is left. | [Proposed] (Kunal: moves stall 10:30–11:00, no clock time) |

- The backtest also tries these as options **[Project]**:
  - the first sale at 2R
  - his half / quarter / quarter style
  - selling the rest once the day's move reaches one daily ATR
  - exiting when the 9 EMA goes flat
  - a "dead money" exit if the trade does nothing for 30 minutes
- **One ORB trade per stock per day.** **[Proposed]**

## 7. What Kunal does NOT use for ORB

- No volume rule on the breakout candle; 5-minute volume tells him little. **[Kunal 76, 77]**
- No minimum gap, no price limit, no reading of the news story. **[Kunal 71, 72, 73, 76]**
- No automatic percentage trailing stops. **[Kunal 72]**

---

## 8. A worked example (made-up numbers)

Account $6,500, so 1% risk = **$65**. Stock XYZ gapped up 5% on earnings; its daily ATR is 4% of the
price; yesterday's high was $49.20.

| Time | What happens |
|---|---|
| 9:30–9:35 | Opens $50.00, high **$51.00**, closes $50.90 (it pushed up). |
| 9:35–9:40 | Trades $50.55–$50.95. **Lid = $51.00** (highest of the first two candles). |
| 9:40–9:45 | Trades $50.65–$50.98: still under the lid. |
| 9:46 | VWAP is $50.50. Price trades $51.01 → **buy**. |

- Stop = $50.50 − 0.1% (about $0.05) = **$50.45**. R = $51.01 − $50.45 = **$0.56 per share**.
- Too far? The opening range is $50.00 to $51.00 = $1.00, so the limit is 60% = $0.60. Entry is
  $0.51 above VWAP → OK.
- Shares by risk: $65 ÷ $0.56 = 116 shares ($5,917). The 50% cap ($3,250) allows only **63 shares**,
  so the real risk is about **$35**. (Same as FPB day 1: with tight stops the cap decides the size.)
- 3R = $51.01 + 3 × $0.56 = **$52.69** → sell 31 shares; the stop moves to $51.01.
- The other 32 shares: sell when a 5-min candle closes below the 9 EMA, or at 11:30 at the latest.
- If it fails instead: stopped at $50.45, losing about $35 plus a few cents per share of slippage.

---

## 9. ORB is a separate strategy from FPB (tested on its own) [Project]

As agreed in `CLAUDE.md` ("How to work in parallel"): two strategies, kept apart so results never mix.

| | FPB (running now) | ORB (new) |
|---|---|---|
| Rules | `fpb_strategy.py` | this file, then `orb_strategy.py` |
| Backtest | `run_fpb_backtest.py` → `logs/fpb_trades/` | `run_orb_backtest.py` → `logs/orb_trades/` |
| Paper trading | `fpb_paper_trader.py` → `logs/paper_trades/` | its own bot → `logs/orb_paper_trades/` |
| Alpaca account | current paper account (`ALPACA_API_KEY`) | a **second** paper account with its own keys |
| Schedule | Task "ORB-Bot daily" (9:20 AM) | its own scheduled task |
| Built in | `C:\Users\Hassan\ORB-Bot` (live, don't touch) | `C:\Users\Hassan\ORB-Bot-orb` (branch `orb-rules`) |

**Why a second Alpaca account:** the FPB bot treats Alpaca as the truth. Anything in its account
that it didn't open counts as a leftover: it won't trade that stock and it cleans up stray orders.
ORB trades in the same account would confuse FPB and mix both results.

**Shared, read-only:** ORB can read the morning watchlist (`output/watchlist.json`) but never changes
the scanner or the FPB files. Since that scanner misses most of Kunal's examples (section 3), ORB will
probably need its own stock list. The backtest starts with the stocks in section 13, and the shared
`universe.txt` (which FPB uses live) is left alone.

**Test plan, in order:**
1. **Rules confirmed:** this document, with your answers. ✅ 2026-10-13
2. **More history:** Yahoo gives only ~60 days of 5-minute candles, far too few trades. ✅ 2026-10-13:
   `alpaca_history.py` downloads Alpaca's history (all US exchanges) and keeps it on disk.
3. **First check: Kunal's 19 ORB charts** (10 long, 9 short). ✅ 2026-10-13: run with
   `check_kunal_examples.py`. With the fixes in section 12, the bot finds **all 19 at the same candle as
   his arrow (one is one candle off), and all 19 pass the filters**. These are winners he picked, so this
   only shows the bot recognises the pattern. It says nothing about how often ORB makes money.
4. **Backtest ORB alone:** at least 200 trades, with slippage, on the right kind of stocks. Every
   skipped setup is logged with the reason. Choose between the options (stop, exits, candle-2 rule)
   on older data, then check the winner on newer data the test never saw, so it doesn't fool us.
   Built 2026-10-13: `run_orb_backtest.py` + `orb_stock_finder.py`. How it works:
   - **Stocks:** every active US stock and ETF on Alpaca's list (about 13,200). Each morning, ORB's
     own finder (section 3b) picks up to 10 using only what was known before the open. Results are
     also shown for the top 6 alone (Kunal watches 4–6).
   - **Each listed stock:** the ORB rules run on its 5-minute candles. A trade is then played
     minute by minute on 1-minute candles (stop before target within a minute, the cautious choice).
     Gainers and uptrending go-to stocks are long only; losers and downtrending ones short only.
     Shorts need a stock Alpaca allows shorting.
   - **Periods:** 2024-01 to 2026-09. "Development" = up to 2025-06 (options may be chosen here);
     "holdout" = 2025-07 on (only to confirm).
   - **Slippage** (my estimates): entry 0.05% + 1¢, stop exits 0.2% + 1¢, market exits 0.05% + 1¢,
     the 3R limit sale none. The report also shows double slippage.
   - **Known limits:**
     - stocks that no longer exist are missing (survivorship bias)
     - pre-market volume isn't checked
     - "can be shorted" uses today's list
     - the 9 EMA starts from yesterday's close
     - results are in R per trade, ignoring how many trades the account could hold at once
   - Output: `logs/orb_trades/<label>_summary.txt`, `_trades.csv` and `_decisions.csv` (every
     listed stock, with the reason for each skip).
5. **Only if the backtest holds up:** paper trade ORB in its own account and schedule, next to FPB.
6. **Judge ORB on its own** after 150+ paper trades. Only then can it join the strategy selector.

**Decision for later (step 5):** `CLAUDE.md` planned to split `fpb_paper_trader.py` into shared
parts before a second strategy goes live. If the FPB code must stay untouched, the alternative is a
standalone ORB bot that copies the proven parts (Alpaca connection, stop orders, broker sync).
Steps 1–4 need neither: they are all new files.

---

## 10. What went wrong with ORB last time (Nov 2025), and what changes

- The old code took entries **until 3:30 PM**. Kunal: none after 11:00.
- It used fixed targets only (half at 2R, the rest at 3R). Kunal: the rest follows the 9 EMA.
- It was tested on mega-caps (AAPL, NVDA, TSLA, AMD) **on ordinary days**. His charts show big names
  can work (ORCL, PLTR), but only on days they really move. A reason to move is required.
- Old notes record **349 trades with a 0.3% win rate** using VWAP stops. That isn't believable;
  even random entries win far more often. It was almost certainly a bug (probably VWAP computed
  wrong), and the code was never saved, so it can't be checked. It led to moving the stop to the
  bottom of the shelf, which is not Kunal's main rule. Plan: test the VWAP stop properly first.

---

## 11. Decisions from Hassan

**2026-10-13: Hassan: defaults OK** (where nothing in the course says otherwise). The defaults below
are what the code uses. #7 and #9 are still open; #10: Hassan has no failed-ORB charts.

| # | Question | Default |
|---|---|---|
| 1 | Lid / floor = highest / lowest price of the first two candles, with no "candle 2" skip rule (the backtest tries one with a tolerance) | Yes |
| 2 | "Look left": ~~a long must be above yesterday's high, a short below yesterday's low~~. Changed after the data check: Kunal's ORCL and UPST broke that rule and worked, so all three look-left versions are backtest options only | Option, not a rule |
| 3 | The **[Proposed]** numbers: 0.1% stop buffer, 60% "too far" limit, daily ATR ≥ ~~2.5%~~ **2%**, QQQ ±0.5% (only for stocks without a 3%+ news gap) | Starting points. The backtest checks them; none may reject his 19 charts |
| 4 | Buy as price breaks the lid (Kunal), or wait for a candle to close past it? | Kunal's way; the backtest tries both |
| 5 | Exits: half at 3R, stop to breakeven, other half on the 9 EMA, everything out by 11:30 | Yes (the other exit ideas are tested as options) |
| 6 | Risk per trade | 1% of the ORB account (same as FPB) |
| 7 | "Go-to" stocks (reason 3). Which ones? | Start the ORB test list with the 19 chart stocks; add your own names |
| 8 | Kunal's tip from class 74 (not about ORB in particular): stops tighter than one 5-min ATR get hit by noise (like DELL/ARM on FPB day 1). Make it a "too tight, skip" rule? | Not yet; the backtest compares with and without |
| 9 | CRK (chart 13) breaks around 12:35 PM, so it isn't an ORB by his own 11:00 rule. Where did it come from? | Treat it as a different pattern; leave it out of the ORB check |
| 10 | Can you get Kunal's **failed** ORB charts (the price breaks the line, then turns back and hits the stop)? | Nice to have, not required: all 20 so far are winners, and the backtest will show the failures on real data |

(Settled: the earliest entry is **9:40**, from his words and his charts; section 4 step 3.)

---

## 12. Review notes (what changed in each draft)

**Draft 2: feedback on draft 1** (pasted by Hassan), checked against the six transcripts.
- Agreed and changed:
  - Every course rule now carries class numbers; our own testing rules are tagged [Project].
  - The VWAP stop now notes the occasional candle-low stop.
  - Exits now start at 3R (his most-used number); 1% risk became a proposal.
- Kept, because the transcripts say otherwise: the 11:00 cut-off (72, 74, 76, 77), the 9 EMA for the
  rest (71, 72, 73, 76, 77), shorts as the mirror image (all classes; 76 in those words), buying on
  the third candle (all classes).

**Draft 3: 10 long charts.** Claude enlarged the first candles of each and checked the rules.
- Earliest entry 9:40 confirmed.
- "Skip if candle 2 pokes above" and "no shelf candle closes below VWAP" were too strict (TEM, RDW,
  RKLB) and were removed.
- The "too far" yardstick moved from the 5-min ATR to today's opening range (TSSI).
- Found that our scanner misses 7 of the 10 stocks.

**Draft 4: 10 short charts + a second pass through all six transcripts.**
- From the charts:
  - Shorts break early (candle 3 in 6 of 9), which strengthens the 9:40 rule.
  - His drawn lines sit at the extreme of the first **two** candles, so the lid/floor is defined that way.
  - The daily chart doesn't have to point the same way (ORCL, PLTR).
  - The remaining "candle 2" skip rule was dropped (TEM, DKNG).
  - CRK is a midday break, not an ORB.
- Missed in drafts 1–3, now added:
  - stocks must have a history of big moves (71) → daily ATR filter
  - clearing the previous days' ranges (71) → the yesterday's-high/low rule
  - gapping into the 200-day average fails (71, 76)
  - market trend vs. chop, and longs/shorts by market mood (71, 77)
  - "ATR used up", 9 EMA flattening and "dead money" as exit signs (71, 72, 73, 74)
  - no automatic % trailing stops (72)
  - he watches only 4–6 stocks (74)
  - pre-market levels are noise without news (76)
  - shorts don't need a big first drop (77)
  - he sometimes sells half to three-quarters into the first spike (74)

---

**2026-10-13: first check with real prices** (`check_kunal_examples.py`, Alpaca data). The first run
found 16 of 19 and let 14 through. Four rules were wrong for his own trades and were changed. Each
change is backed by the course, not just bent to fit:
- **Direction:** the first candle alone got SOXL, KC and UPST wrong. Now a 1%+ gap sets the direction
  (Kunal: gap up on news = long, gap down = short).
- **Yesterday's range:** it rejected his ORCL and UPST shorts. Now a backtest option (Kunal 71 says
  "easiest", not "required").
- **Daily ATR:** 2.5% rejected his TKR short (2.1%). Now 2%, which sits between Armando's "no" at 1.75%
  and Kunal's TKR trade.
- **QQQ check:** it rejected his KC short (a China stock with its own 4% news gap). Now it applies only
  to stocks without a 3%+ news gap (Kunal warns against buying just any stock in a falling market; Armando: news stocks move on their own).

Result: all 19 found at the same candle as his arrow (TSSI one candle earlier), all 19 traded. Bot
entries land within cents of his drawn lines (e.g. PI 149.22, TKR 74.63). Honest caveats:
- Loosening filters to accept known winners can't show they help. The backtest over all days, where
  most breakouts fail, decides whether they stay.
- The "+3.1R average" on these 19 means nothing: they are winners he picked, and slippage isn't
  counted yet.

**2026-10-13: first backtest pilot (May 2025, top 10 of each morning list by gap size).**
- Result: 74 trades, +0.04R each after slippage (about break-even; −4.2R in total with double slippage).
  Longs +13.6R, shorts −10.8R. One month is far too little to judge.
- The real lesson was the stock finder:
  - About 90 liquid stocks gap 3%+ on a normal day (160 on May 27, 2025). A top 10 by gap size
    fills up with tiny pump stocks.
  - **None of Kunal's six May stocks made the list.** RDW, SOUN and RKLB were gappers but ranked
    28th–56th by gap size. TSSI was cut by the 1M-share average (948k), though Kunal judges gappers
    by pre-market volume. BBAI was under the $5 gapper minimum. TEM was one of yesterday's movers,
    but the list was already full.
  - The 6 biggest gaps each morning did worse (−6.3R) than ranks 7–10 (+9.1R).
- Changed: the finder is now wide ("research mode"). Every candidate is tested, and the backtest
  records what each stock was like:
  - pre-market volume (Kunal's real gapper test)
  - first-15-minute volume (Armando's sign)
  - price and dollar liquidity
  - gap size and daily range

  The development period will show which kinds of stocks ORB works on. That becomes the ranking,
  and the holdout period checks it. Gappers now need 500k+ shares a day (not 1M), and every candidate
  needs a daily ATR of 2%+.

## 13. Kunal's 20 marked charts

Screenshots saved on the PC only: `private/charts/orb_kunal_examples/` (course material, never uploaded).
Each shows his daily chart on the left and the 5-minute chart, with his arrow at the entry, on the right.
"Day's move" comes from each screenshot's header. Candle counts and opening gaps are by eye from
small screenshots, so each could be off by one candle.

**Longs**

| # | Date | Stock | Day's move | Daily chart | Break came on | What happened after |
|---|---|---|---|---|---|---|
| 1 | 2025-04-24 | SOXL | +16% | Long downtrend, bouncing; gapped above a 2-week range | candle 3 | Ran hard to ~10:15, then crept up all day |
| 2 | 2025-05-08 | TEM | +11% | Rising from April lows; cleared a month-long base; opened about flat | candle 5 (candle 2's wick set the lid) | Steady climb until ~2 PM |
| 3 | 2025-05-16 | TSSI | +74% | Huge news gap through a falling trend line | candle 6 (he drew a line at the first candles' high) | Ran to ~10:15, then flat |
| 4 | 2025-05-27 | RDW | +23% | Uptrend; broke out of a May base. No fresh news visible | candle 4–5 | Ran to 10:30, flat midday, up again late |
| 5 | 2025-05-27 | SOUN | +16% | Pulled back after a mid-May spike; same-day analyst news | candle 6 (candle 4 if you use the first candle's body, not its wick) | Ran to ~10:15, then sideways |
| 6 | 2025-05-27 | RKLB | +13% | Strong uptrend, new highs | candle 6 (candle 2 a big red drop; candle 3 closed under VWAP) | Ran to ~10:30, flat the rest of the day |
| 7 | 2025-05-27 | BBAI | +23% | Uptrend from April; ~$4 stock. No fresh news visible | candle 4 | Ran to 10:30, flat midday, up late |
| 8 | 2025-07-24 | TMC | +6% | Strong uptrend; opened about flat, the first candle popped | candle 4–5 | Spiked by ~9:55, gave back half by 10:15, choppy all day |
| 9 | 2025-07-28 | ACMR | +6% | Steady uptrend; broke a 3-week flag; small gap (~1%) | candle 4 | Up, stalled 10–11, then climbed again to noon |
| 10 | 2025-07-31 | PI | +26% | Earnings gap above the 200-day average | candle 4 (he drew a line at the top of the first two candles) | Ran to ~10:30, then flat |

**Shorts** (Kunal calls these "opening range break**downs**": the short version, not failed trades.
In every one the price kept falling after his arrow, so shorting there made money.)

| # | Date | Stock | Day's move | Daily chart | Break came on | What happened after |
|---|---|---|---|---|---|---|
| 11 | 2025-07-30 | TKR | −9% | Earnings day; gap down through the 200-day average after a run to highs | candle 6 (candle 3 bounced back above VWAP first) | Fell steadily to ~11:30 |
| 12 | 2025-07-30 | SMG | −8% | Earnings day; had stalled at the 200-day average | candle 3 | Fell to ~10:30, then drifted lower |
| 13 | 2025-08-01 | CRK | −8% | Downtrend; gap down under the 200-day | **~12:35 PM**, below the morning's low after ~2 hours sideways | Kept sliding. **Not an ORB by his own 11:00 rule** |
| 14 | 2025-08-15 | PEW | −18% | Day after earnings; downtrend; ~$5–6 small cap | candle 7 (first candles had long wicks, no clear drop) | Fell to ~noon, bounced in the afternoon |
| 15 | 2025-08-19 | ORCL | −6% | **Strong daily uptrend** near highs; opened about flat | candle 3 | Dropped to ~10:15, chopped, fell again into the afternoon |
| 16 | 2025-08-19 | UPST | −6% | Falling since early-August earnings; opened about flat | candle 3 | Fell to ~10:45, bounced at noon, lower again |
| 17 | 2025-08-19 | PLTR | −9% | **Strong daily uptrend**, pulling back from highs | candle 3 | Fell to ~10:30, bounced to noon, fell again |
| 18 | 2025-09-30 | DKNG | −10% | Gap down to the 200-day average and through it | candle 3 | Steady fall all morning |
| 19 | 2025-09-30 | DOCU | −9% | Pulling back after a September run | candle 3 | Steady fall to ~10:45 |
| 20 | 2025-03-20 | KC | −11% | Gap down out of a month-long sideways range | ~candle 12 (~10:30), after a long shelf | Slid all day |

**What they tell us (beyond sections 3–6):**
- Nearly all moved hardest in the first hour, then went flat, bounced or gave some back between
  10:30 and noon. That backs up quick profit-taking. TMC shows it most clearly.
- Big days come in clusters: four longs on May 27, 2025; three shorts on Aug 19, 2025; two each on
  Jul 30 and Sep 30. Several ORBs can set up at once, so the ORB bot needs a limit on how many
  trades it holds at a time, as FPB has.
- Every chart whose header shows it has a daily ATR of 3.3% or more (some up to 11%).
- **CRK (13) is left out of the ORB check.** It breaks the morning's low after midday, which looks
  like his separate "day-long consolidation" pattern (class 71 lists it apart from ORBs).
- **Important:** these are winners Kunal chose to show. They teach what the setup looks like; they
  say nothing about how often ORB wins. Only the backtest and paper trading can tell us that.
