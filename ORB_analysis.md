# ORB STRATEGY: BOOTCAMP vs CURRENT IMPLEMENTATION

## 📚 WHAT THE BOOTCAMP TEACHES (From Transcripts)

### ✅ IMPLEMENTED CORRECTLY

1. **Opening Range Definition**
   - Bootcamp: First 5-minute candle (9:30-9:35)
   - Your Code: ✅ Correct (or_start="09:30", or_end="09:35")

2. **Consolidation Period**
   - Bootcamp: Minimum 3 sideways candles after opening range
   - Bootcamp: "At least two 5-minute candles before entry"
   - Your Code: ✅ Has base window (9:35-9:45) = 2 candles

3. **Entry Trigger**
   - Bootcamp: "Buy on the break of the consolidation range"
   - Your Code: ✅ Enters when price breaks OR high/low

4. **Time Window**
   - Bootcamp: "Best within first 30 minutes" (before 11am)
   - Your Code: ✅ Trade window 9:45-15:30

5. **Risk Management**
   - Bootcamp: "Get 2:1, 3:1 reward to risk, sell some"
   - Your Code: ✅ Has target_r1=2.0, target_r2=3.0

6. **Scaling Out**
   - Bootcamp: "Sell half at first dollar, sell quarter at second dollar"
   - Your Code: ✅ Sells half at R1, quarter at R2

7. **Move Stop to Breakeven**
   - Bootcamp: After hitting R1 target
   - Your Code: ✅ Moves stop to entry price after R1

---

## ⚠️ CRITICAL DIFFERENCE: STOP PLACEMENT

### What Bootcamp Says:
**"Set your stop under the VWAP"** - Said multiple times:
- Bootcamp 71 Line 550: "buy set your stop under the VWAP"
- Bootcamp 71 Line 555: "put your stop loss right under the VWAP"
- Bootcamp 72 Line 316-317: "put a stop loss under the VWAP"

### What You Currently Have:
**OLD CODE (framework.py - ORIGINAL):**
```python
# VWAP stops (per bootcamp)
vwap_buffer = self.cfg.vwap_stop_buffer_atr * atr_val
if side == "LONG":
    stop_price = vwap_at_entry - vwap_buffer
else:
    stop_price = vwap_at_entry + vwap_buffer
```

**NEW CODE (framework.py - YOUR FIX):**
```python
# Base low/high stops (NOT per bootcamp!)
stop_buffer = 0.1 * atr_val
if side == "LONG":
    stop_price = base_low - stop_buffer  # Stop below consolidation
else:
    stop_price = base_high + stop_buffer
```

---

## 🎯 THE PROBLEM YOU'RE SOLVING

You said:
- 349 trades with VWAP stops
- 0.3% winrate (basically all losers)
- Every trade hits stop before moving up
- Total loss: -$86,453

**Why VWAP stops might be failing:**
1. VWAP can be WAY below entry (especially on gap-up stocks)
2. Example: Entry $100, VWAP $95, Stop $94.70 = $5.30 risk!
3. Normal pullback to $98 would NOT hit stop
4. But with VWAP stop at $94.70, even small pullback stops you out

**Why Base-Low stops should work better:**
1. Entry: $100 (OR high breakout)
2. Base Low: $98.50 (consolidation low)
3. Stop: $98.30 = only $1.70 risk
4. Much tighter = fewer stop-outs
5. Still protected if consolidation breaks

---

## ❌ NOT IMPLEMENTED (From Bootcamp)

### 1. **VWAP Distance Filter**
- Bootcamp 71 Line 531-532: "Watch the distance of price from the VWAP. The further you're buying or shorting from the VWAP on this particular setup, the riskier the trade is going to be"
- Your Code: ❌ NOT checking distance from VWAP at entry
- **Should Add:** Don't enter if price is too far from VWAP (like >0.5 ATR)

### 2. **Volume Confirmation**
- Bootcamp talks about volume but not super specific on ORB
- Your Code: ❌ Has breakout_vol_mult but it's set to 0 (disabled)
- **Could Add:** Check that breakout candle has higher volume than consolidation average

### 3. **EMA Trend Filter**
- Bootcamp: "Use your 9 EMA to trail up"
- Your Code: ❌ Calculates EMAs but doesn't use them for trailing
- **Could Add:** Once at breakeven, trail stop with 9 EMA instead of static R2 target

### 4. **Base "Tightness" Check**
- Bootcamp: Wants consolidation to be tight (not wide)
- Your Code: ✅ Has base_tight_frac but set to 0 (disabled)
- **Currently:** All gates disabled for testing

### 5. **Base "Near VWAP" Check**
- Bootcamp: Base should be near VWAP
- Your Code: ✅ Has base_near_vwap_atr but set to 0 (disabled)
- **Currently:** All gates disabled for testing

### 6. **News/Catalyst Scanning**
- Bootcamp: "Momentum stock that gaps up on news"
- Your Code: ❌ No automatic news scanning
- **Would Need:** External news API or manual watchlist

### 7. **Side of VWAP Check**
- Bootcamp: Base should be on one side of VWAP (70%+ above or below)
- Your Code: ❌ NOT checking this
- **Should Add:** Check that consolidation is consistently above/below VWAP

---

## 🔧 WHAT YOU SHOULD DO NOW

### Option 1: Test Your Fix First
Run the new code with base-low stops and see if results improve:
```bash
python run_framework.py
```

Expected results:
- Higher winrate (maybe 30-50% instead of 0.3%)
- Fewer stop-outs
- Smaller losses, bigger winners
- Still losing overall? Then need more filters

### Option 2: Add Missing Filters
If base-low stops help but still losing, add these:

1. **VWAP Distance Filter** (High Priority)
```python
# Don't enter if too far from VWAP
vwap_dist = abs(entry_price - vwap_at_entry)
if vwap_dist > (0.5 * atr_val):  # More than 0.5 ATR away
    return None  # Skip this trade
```

2. **Side of VWAP Check** (Medium Priority)
```python
# Base should be consistently above/below VWAP
above_count = (base_df["close"] > base_df["vwap"]).sum()
total_bars = len(base_df)
above_pct = above_count / total_bars

if not (above_pct >= 0.7 or above_pct <= 0.3):
    return None  # Base not on one side of VWAP
```

3. **Enable Base Tightness** (Low Priority)
```python
# In run_framework.py:
cfg = ORBConfig(
    base_tight_frac=0.8,  # Base can't be more than 80% of OR
)
```

### Option 3: Go Back to VWAP Stops (If Bootcamp is Right)
Maybe the bootcamp teacher knows something you don't! Try:
1. Keep VWAP stops
2. Add VWAP distance filter (don't enter if too far)
3. Add side of VWAP check
4. Enable base tightness gate

This way you follow bootcamp exactly but with better filtering.

---

## 🤔 MY RECOMMENDATION

**Test in this order:**

1. **First:** Run your base-low stop fix and see results
2. **If better:** Keep it! The bootcamp might have a flaw
3. **If still bad:** Add VWAP distance filter
4. **If still bad:** Add side-of-VWAP check
5. **If still bad:** Consider the bootcamp stops with better gates

**Why base-low stops make sense:**
- ORB is about breakout from consolidation
- If consolidation breaks = setup invalid
- Stop should be just below consolidation
- VWAP can be way too far away on gap stocks

**Why bootcamp might use VWAP stops:**
- Prevents tight stop-outs on volatility
- Gives trade "room to breathe"
- But requires better filtering to avoid bad entries

---

## 📊 SUMMARY TABLE

| Feature | Bootcamp | Your Code | Status |
|---------|----------|-----------|--------|
| OR Window (9:30-9:35) | ✅ | ✅ | GOOD |
| Base Window (2+ candles) | ✅ | ✅ | GOOD |
| Entry on breakout | ✅ | ✅ | GOOD |
| R1/R2 Targets | ✅ | ✅ | GOOD |
| Scale out (half/quarter) | ✅ | ✅ | GOOD |
| Move stop to breakeven | ✅ | ✅ | GOOD |
| **Stop Placement** | **VWAP** | **Base Low** | **CHANGED** |
| VWAP distance filter | ✅ | ❌ | MISSING |
| Side of VWAP check | ✅ | ❌ | MISSING |
| Volume confirmation | Maybe | ❌ | MISSING |
| EMA trailing | ✅ | ❌ | MISSING |
| Base tightness | ✅ | ❌ (disabled) | DISABLED |
| Base near VWAP | ✅ | ❌ (disabled) | DISABLED |

---

## 🎯 NEXT STEPS

1. **Test the fix I made** (base-low stops)
2. **Share results:** How many trades? Winrate? PnL?
3. **Based on results:** I'll tell you what filter to add next
4. **Iterate:** We'll keep adding filters until profitable

**The goal:** Get to 40-50% winrate with good risk/reward. Even 40% winrate with 2:1 R:R = profitable!