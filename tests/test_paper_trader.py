"""
Paper-trader test suite against a FAKE broker (no real orders, no Alpaca connection, no
internet). Run it after every change to fpb_paper_trader.py or the scanners:

    .venv\\Scripts\\python.exe -X utf8 tests\\test_paper_trader.py              # everything
    .venv\\Scripts\\python.exe -X utf8 tests\\test_paper_trader.py stops size   # some sections

Sections: sync, size, fresh, stops, calendar, scanner, prices.
The fake broker copies Alpaca's rules that matter, e.g. shares held by a stop order can't be
closed until that order is cancelled. Fake positions: + = long shares, - = short shares.
"""
import contextlib
import importlib.util
import io
import itertools
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd

project = Path(__file__).resolve().parent.parent
only = set(sys.argv[1:])
sys.path[:0] = [str(project), str(project / "scanners")]
time.sleep = lambda s: None
tmp = tempfile.mkdtemp()
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("  PASS " if ok else "  FAIL ") + name + (f"  ({detail})" if detail else ""))


def section(title, tag):
    if only and tag not in only:
        return False
    print(f"\n{title}")
    return True


spec = importlib.util.spec_from_file_location("bot", project / "fpb_paper_trader.py")
bot = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(bot)
bot.LOG_DIR = tmp + "/logs"
bot.STATE_FILE = tmp + "/logs/position_state.json"
bot.FILL_WAIT_SECONDS = 0.2
OPEN = {"new", "accepted", "partially_filled", "pending_new"}


class FakeBroker:
    """Acts like Alpaca: market orders fill at the test's price; stop orders wait for trigger()."""
    def __init__(self, prices):
        self.prices, self.pos, self.avg, self.orders = prices, {}, {}, {}
        self.ids = itertools.count(1)
        self.equity, self.buying_power = 10000.0, 40000.0
        self.offline = False
        self.account_offline = False
        self.fail_close = 0
        self.fill_ratio = 1.0
        self.never_fill = False
        self.reject_stops = False
        self.not_shortable = set()
        self.manual_open_orders = set()
        self.cancelled = []

    def _guard(self):
        if self.offline:
            raise ConnectionError("Alpaca unreachable")

    def _move(self, symbol, signed):
        self.pos[symbol] = self.pos.get(symbol, 0) + signed
        self.avg.setdefault(symbol, self.prices[symbol])
        if self.pos[symbol] == 0:
            del self.pos[symbol]
            self.avg.pop(symbol, None)

    def held(self, symbol):
        return sum(o.qty for o in self.orders.values() if o.symbol == symbol and o.type == "stop" and o.status in OPEN)

    def _market(self, symbol, signed, cid=None):
        filled = 0 if self.never_fill else int(abs(signed) * self.fill_ratio)
        if filled:
            self._move(symbol, filled if signed > 0 else -filled)
        oid = next(self.ids)
        status = "new" if self.never_fill else ("filled" if filled == abs(signed) else "partially_filled")
        self.orders[oid] = NS(id=oid, symbol=symbol, side="buy" if signed > 0 else "sell", qty=abs(signed),
                              type="market", status=status, filled_qty=str(filled), client_order_id=cid,
                              filled_avg_price=str(self.prices[symbol]) if filled else None, stop_price=None)
        return self.orders[oid]

    def submit_order(self, req):
        self._guard()
        qty = int(float(req.qty))
        side = "buy" if req.side == bot.OrderSide.BUY else "sell"
        if getattr(req, "stop_price", None) is not None:
            if self.reject_stops:
                raise Exception("stop order rejected")
            oid = next(self.ids)
            self.orders[oid] = NS(id=oid, symbol=req.symbol, side=side, qty=qty, type="stop", status="new",
                                  filled_qty="0", filled_avg_price=None, stop_price=float(req.stop_price),
                                  client_order_id=req.client_order_id)
            return self.orders[oid]
        return self._market(req.symbol, qty if side == "buy" else -qty, req.client_order_id)

    def close_position(self, symbol, opts):
        self._guard()
        if self.fail_close > 0:
            self.fail_close -= 1
            raise Exception("temporary error")
        have, qty = self.pos.get(symbol, 0), int(opts.qty)
        if have == 0:
            raise Exception("position does not exist")
        if qty > abs(have) - self.held(symbol):
            raise Exception("insufficient qty available for order")
        return self._market(symbol, -qty if have > 0 else qty)

    def trigger(self, symbol, price):
        """Test helper: the market trades at `price`; fire any stop orders it crosses."""
        self.prices[symbol] = price
        for o in list(self.orders.values()):
            if o.symbol == symbol and o.type == "stop" and o.status in OPEN:
                if (o.side == "sell" and price <= o.stop_price) or (o.side == "buy" and price >= o.stop_price):
                    self._move(symbol, o.qty if o.side == "buy" else -o.qty)
                    o.status, o.filled_qty, o.filled_avg_price = "filled", str(o.qty), str(price)

    def get_order_by_id(self, oid):
        self._guard()
        return self.orders[int(oid)]

    def cancel_order_by_id(self, oid):
        self._guard()
        o = self.orders[int(oid)]
        if o.status not in OPEN:
            raise Exception(f"order is not cancelable ({o.status})")
        self.cancelled.append(int(oid))
        o.status = "canceled"

    def get_all_positions(self):
        self._guard()
        return [NS(symbol=s, qty=str(q), side=NS(value="long" if q > 0 else "short"),
                   avg_entry_price=str(self.avg.get(s, 0)), current_price=str(self.prices.get(s, 0)),
                   unrealized_pl="0", unrealized_plpc="0") for s, q in self.pos.items()]

    def get_orders(self, req):
        self._guard()
        live = [NS(symbol=o.symbol, id=o.id, client_order_id=o.client_order_id)
                for o in self.orders.values() if o.status in OPEN]
        return live + [NS(symbol=s, id=f"manual-{s}", client_order_id="manual") for s in self.manual_open_orders]

    def get_asset(self, symbol):
        self._guard()
        ok = symbol not in self.not_shortable
        return NS(shortable=ok, easy_to_borrow=ok)

    def get_account(self):
        self._guard()
        if self.account_offline:
            raise ConnectionError("account endpoint down")
        return NS(equity=str(self.equity), buying_power=str(self.buying_power), shorting_enabled=True)

    def open_stops(self, symbol=None):
        return [o for o in self.orders.values()
                if o.type == "stop" and o.status in OPEN and (symbol is None or o.symbol == symbol)]


def make_bot():
    prices = {}
    alpaca = bot.AlpacaClient.__new__(bot.AlpacaClient)      # skip the real Alpaca connection
    alpaca.trading_client = FakeBroker(prices)
    alpaca.data_client, alpaca.connected, alpaca.equity, alpaca.sim_mode = None, True, 10000.0, False
    alpaca.shorting_enabled, alpaca._shortable = True, {}
    alpaca.get_current_price = lambda s: prices.get(s)
    alpaca.get_current_ema9 = lambda s: None
    state, log = bot.PositionStateManager(), bot.PaperTradeLog()
    state.positions, log.trades = {}, []
    sync = bot.BrokerSync(alpaca, state, log)
    monitor = bot.PositionMonitor(alpaca, state, log)
    return NS(alpaca=alpaca, broker=alpaca.trading_client, prices=prices, state=state, log=log,
              sync=sync, monitor=monitor)


def track(b, symbol, direction, shares, entry, stop, r1, r2, minutes_ago=5):
    b.state.add_position(symbol=symbol, entry_price=entry, signal_price=entry, stop_price=stop,
                         target_r1=r1, target_r2=r2, shares=shares, direction=direction, risk_dollars=50)
    old = (bot.now_et() - timedelta(minutes=minutes_ago)).isoformat()
    b.state.update_position(symbol, entry_time=old)


def run(fn):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn()
    return result, out.getvalue()


# Scanner helpers ---------------------------------------------------------------------------------
class StubStrategy:
    """Pretends each symbol in `setups` has an FPB setup. The signal candle is `age_min` minutes old."""
    def __init__(self, setups, age_min=0, entry=100.0, risk=1.0, shares=30):
        self.setups, self.age_min, self.entry, self.risk, self.shares = setups, age_min, entry, risk, shares
    def prepare_data(self, df): return df
    def get_previous_close(self, df, day): return 100.0
    def check_initial_spike(self, df, prev):
        d = self.setups.get(df.attrs["sym"])
        return (d is not None), (d or "NONE")
    def find_pullback_entry(self, df, direction, hi, lo):
        short = direction == "SHORT"
        r, e = self.risk, self.entry
        bar = pd.Timestamp(bot.now_et() - timedelta(minutes=self.age_min), tz="America/New_York").floor("5min")
        return {"entry_time": bar, "entry_price": e, "stop_price": e + r if short else e - r,
                "target_r1": e - 1.5 * r if short else e + 1.5 * r, "target_r2": e - 3 * r if short else e + 3 * r,
                "shares": self.shares, "risk_per_share": r, "risk_dollars": r * self.shares}


def fake_bars(symbol, days=5):
    start = datetime.combine(bot.now_et().date(), datetime.min.time()) + timedelta(hours=9, minutes=30)
    idx = [start - timedelta(days=1) + timedelta(minutes=5 * i) for i in range(8)] + \
          [start + timedelta(minutes=5 * i) for i in range(6)]
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
                      index=pd.DatetimeIndex(idx).tz_localize("America/New_York"))
    df.attrs["sym"] = symbol
    return df


bot.download_stock_data = fake_bars
bot.SCAN_START_TIME, bot.SCAN_END_TIME = "00:00", "23:59"


def scanner_for(b, setups, **kw):
    s = bot.EntryScanner(b.alpaca, b.state, b.log, b.sync)
    s.strategy, s.symbols = StubStrategy(setups, **kw), list(setups)
    for sym in setups:
        b.prices.setdefault(sym, kw.get("entry", 100.0))
    return s


# =================================================================================================
if section("BUG 1+2: exits, broker sync, shorts", "sync"):
    b = make_bot()
    b.prices["GOOGL"] = 322.05
    (price, filled), _ = run(lambda: b.alpaca.sell_short("GOOGL", 21))
    track(b, "GOOGL", "SHORT", filled, price, 327.02, 316.60, 310.34)
    b.prices["GOOGL"] = 316.30; run(lambda: b.monitor.check_position("GOOGL"))
    b.prices["GOOGL"] = 322.10; run(lambda: b.monitor.check_position("GOOGL"))
    check("GOOGL short replay ends flat", "GOOGL" not in b.broker.pos and b.state.position_count() == 0)

    b = make_bot()
    b.prices["AMD"] = 100.0
    run(lambda: b.alpaca.buy("AMD", 40))
    track(b, "AMD", "LONG", 40, 100.0, 98.0, 103.0, 106.0)
    b.broker.fail_close = 1
    b.prices["AMD"] = 97.5
    action, _ = run(lambda: b.monitor.check_position("AMD"))
    check("failed exit keeps position, no fake sale",
          action == "EXIT_FAILED" and b.state.has_position("AMD") and
          not [t for t in b.log.trades if t["type"].startswith("SELL")])
    action, _ = run(lambda: b.monitor.check_position("AMD"))
    check("retry closes it for real", action == "SELL_STOP" and "AMD" not in b.broker.pos)

    b = make_bot()
    track(b, "TSLA", "LONG", 10, 250.0, 245.0, 257.5, 265.0)
    run(b.sync.sync)
    check("closed outside the bot -> removed", not b.state.has_position("TSLA"))
    b = make_bot()
    track(b, "NIO", "LONG", 100, 5.0, 4.8, 5.3, 5.6, minutes_ago=0)
    run(b.sync.sync)
    check("brand-new entry kept during grace period", b.state.has_position("NIO"))
    b = make_bot()
    b.prices["SOFI"] = 22.0
    run(lambda: b.alpaca.buy("SOFI", 30))
    track(b, "SOFI", "LONG", 50, 22.0, 21.5, 22.75, 23.5)
    run(b.sync.sync)
    check("share count follows Alpaca", b.state.get_position("SOFI")["shares_remaining"] == 30)
    b = make_bot()
    b.prices["MVST"] = 0.58
    run(lambda: b.alpaca.buy("MVST", 805))
    _, o1 = run(b.sync.sync); _, o2 = run(b.sync.sync)
    check("leftover flagged once, blocks trading, uses a slot",
          o1.count("MVST") == 1 and "MVST" not in o2 and b.sync.is_busy("MVST") and b.sync.slots_used() == 1)
    b = make_bot()
    b.broker.offline = True
    held, _ = run(b.alpaca.get_positions)
    ok, _ = run(b.sync.sync)
    check("Alpaca offline -> unknown, not 'nothing'", held is None and ok is False)

    b = make_bot()
    s = scanner_for(b, {"LNG": "LONG", "SHRT": "SHORT"})
    run(s.scan_once)
    check("scanner takes LONG and SHORT", b.broker.pos.get("LNG") == 30 and b.broker.pos.get("SHRT") == -30)
    b = make_bot()
    b.broker.not_shortable.add("HTB")
    s = scanner_for(b, {"HTB": "SHORT"})
    run(s.scan_once)
    check("not-shortable stock skipped", "HTB" not in b.broker.pos)
    b = make_bot()
    b.prices["SOFI"] = 100.0
    run(lambda: b.alpaca.sell_short("SOFI", 52))
    b.broker.manual_open_orders.add("PEND")
    s = scanner_for(b, {"SOFI": "LONG", "PEND": "LONG", "OK": "LONG"})
    run(s.scan_once)
    check("no flips, no double orders",
          b.broker.pos.get("SOFI") == -52 and "PEND" not in b.broker.pos and b.broker.pos.get("OK") == 30)
    b = make_bot()
    b.broker.fill_ratio = 2 / 3
    s = scanner_for(b, {"PART": "LONG"})
    run(s.scan_once)
    check("partial entry fill recorded as filled", b.state.get_position("PART")["shares_remaining"] == 20)
    b = make_bot()
    b.broker.never_fill = True
    s = scanner_for(b, {"STUCK": "LONG"})
    run(s.scan_once)
    check("unfilled entry cancelled, not recorded", b.broker.cancelled and not b.state.has_position("STUCK"))
    b = make_bot()
    b.prices["EOD2"] = 20.0
    run(lambda: b.alpaca.buy("EOD2", 10))
    track(b, "EOD2", "LONG", 10, 20.0, 19.0, 21.5, 23.0)
    b.broker.fail_close = 99
    ok, out = run(lambda: bot.close_all_tracked(b.monitor, b.sync))
    check("end of day warns if still open", ok is False and "STILL OPEN" in out)

if section("BUG 3: order size fits the account", "size"):
    b = make_bot()
    b.broker.equity, b.broker.buying_power = 7600.0, 30400.0
    s = scanner_for(b, {"QS": "LONG"}, entry=7.10, risk=0.01, shares=1618)
    _, out = run(s.scan_once)
    check("QS: 1,618 shares (~$11.5k) capped to 50% of a $7.6k account",
          b.broker.pos.get("QS") == 535, f"got {b.broker.pos.get('QS')}")
    check("cap is explained", "capped from 1618 to 535" in out)
    check("logged risk matches the smaller size",
          abs(b.state.get_position("QS")["risk_dollars"] - 5.35) < 0.01)

    b = make_bot()
    b.broker.buying_power = 1500.0          # stuck positions using up the account
    s = scanner_for(b, {"LOWBP": "LONG"}, entry=10.0, risk=0.05, shares=600)
    run(s.scan_once)
    check("low buying power: uses its share of what's left (1500 / 3 slots = 50 shares)",
          b.broker.pos.get("LOWBP") == 50, f"got {b.broker.pos.get('LOWBP')}")

    b = make_bot()
    b.broker.account_offline = True
    s = scanner_for(b, {"NOBP": "LONG"})
    _, out = run(s.scan_once)
    check("buying power unknown -> no trade", "NOBP" not in b.broker.pos and "can't confirm buying power" in out)

    b = make_bot()
    b.broker.buying_power = 100.0
    s = scanner_for(b, {"PRICY": "LONG"}, entry=500.0, risk=2.0, shares=10)
    _, out = run(s.scan_once)
    check("can't afford even 1 share -> skipped", "PRICY" not in b.broker.pos and "doesn't fit" in out)

    b = make_bot()
    s = scanner_for(b, {"SMALL": "LONG"})
    _, out = run(s.scan_once)
    check("normal-size trade untouched", b.broker.pos.get("SMALL") == 30 and "capped" not in out)

if section("BUG 6 + 8: fresh signals only, one attempt per stock per day", "fresh"):
    b = make_bot()
    s = scanner_for(b, {"OLD": "LONG"}, age_min=30)
    _, o1 = run(s.scan_once); _, o2 = run(s.scan_once)
    check("30-minute-old signal is not traded", "OLD" not in b.broker.pos)
    check("explained once, not every scan", "Too late to enter" in o1 and "OLD" not in o2)

    b = make_bot()
    s = scanner_for(b, {"NEWSIG": "SHORT"}, age_min=3)
    run(s.scan_once)
    check("fresh signal (this candle or last) is traded", b.broker.pos.get("NEWSIG") == -30)

    b = make_bot()
    s = scanner_for(b, {"DEAD": "LONG"}, entry=100.0, risk=1.0)
    b.prices["DEAD"] = 98.5                      # stop is 99.00
    _, out = run(s.scan_once)
    check("price already past the stop -> skipped", "DEAD" not in b.broker.pos and "past the stop" in out)

    b = make_bot()
    b.broker.never_fill = True
    s = scanner_for(b, {"REJ": "LONG"})
    run(s.scan_once)
    b.broker.never_fill = False
    _, out = run(s.scan_once)
    check("entry that didn't fill is not retried later the same day", "REJ" not in b.broker.pos)
    check("logged as ENTRY_FAILED", any(t["type"] == "ENTRY_FAILED" for t in b.log.trades))

if section("BUG 5: stop-loss orders live at Alpaca", "stops"):
    def entered(b, sym, direction="LONG", entry=100.0, risk=1.0):
        s = scanner_for(b, {sym: direction}, entry=entry, risk=risk)
        run(s.scan_once)
        return b.state.get_position(sym)

    b = make_bot()
    pos = entered(b, "PROT")
    stops = b.broker.open_stops("PROT")
    check("entry places one stop order at Alpaca (30 shares @ $99)",
          len(stops) == 1 and stops[0].qty == 30 and stops[0].stop_price == 99.0 and stops[0].side == "sell")
    check("bot remembers the stop order", pos["stop_order_id"] == str(stops[0].id))

    print("   -- bot crashes; price drops through the stop --")
    b.broker.trigger("PROT", 98.7)
    check("Alpaca's stop closed the position with no bot running", "PROT" not in b.broker.pos)
    action, out = run(lambda: b.monitor.check_position("PROT"))
    stop_logs = [t for t in b.log.trades if t["type"] == "SELL_STOP"]
    check("bot records the real stop exit when it looks again",
          action == "SELL_STOP" and not b.state.has_position("PROT") and stop_logs
          and stop_logs[0]["fill_price"] == 98.7 and stop_logs[0]["via"] == "alpaca_stop_order")
    check("logged P&L is real: -1.30 x 30 = -$39.00", abs(stop_logs[0]["pnl"] + 39.0) < 0.01)

    b = make_bot()
    pos = entered(b, "SHSTOP", "SHORT")
    stops = b.broker.open_stops("SHSTOP")
    check("short gets a BUY stop above the entry", len(stops) == 1 and stops[0].side == "buy" and stops[0].stop_price == 101.0)
    b.broker.trigger("SHSTOP", 101.4)
    run(lambda: b.monitor.check_position("SHSTOP"))
    check("short stop fires and is recorded, broker flat", "SHSTOP" not in b.broker.pos and not b.state.has_position("SHSTOP"))

    b = make_bot()
    entered(b, "TGT")
    b.state.update_position("TGT", entry_time=(bot.now_et() - timedelta(minutes=5)).isoformat())
    b.prices["TGT"] = 101.6                              # R1 = 101.50
    action, _ = run(lambda: b.monitor.check_position("TGT"))
    stops = b.broker.open_stops("TGT")
    check("R1: half closed even though a stop was holding the shares",
          action == "SELL_R1" and b.broker.pos.get("TGT") == 15)
    check("R1: new stop for the 15 left, moved to breakeven ($100)",
          len(stops) == 1 and stops[0].qty == 15 and stops[0].stop_price == 100.0)

    b.alpaca.get_current_ema9 = lambda s: 102.0          # trail: 102 x 0.998 = 101.80
    b.prices["TGT"] = 102.5
    run(lambda: b.monitor.check_position("TGT"))
    stops = b.broker.open_stops("TGT")
    check("trailing stop moves the order at Alpaca too ($101.80)",
          len(stops) == 1 and stops[0].stop_price == 101.8 and stops[0].qty == 15)

    b.prices["TGT"] = 103.2                              # R2 = 103.00
    action, _ = run(lambda: b.monitor.check_position("TGT"))
    check("R2: rest closed, no stop order left behind",
          action == "SELL_R2" and "TGT" not in b.broker.pos and not b.broker.open_stops("TGT"))

    b = make_bot()
    entered(b, "EODX", "SHORT")
    ok, _ = run(lambda: bot.close_all_tracked(b.monitor, b.sync))
    check("end of day: stop cancelled, short bought back, nothing left",
          ok and "EODX" not in b.broker.pos and not b.broker.open_stops())

    b = make_bot()
    entered(b, "FAILX")
    b.broker.fail_close = 1
    b.prices["FAILX"] = 98.9
    action, _ = run(lambda: b.monitor.check_position("FAILX"))
    check("exit fails after cancelling the stop -> stop is put back",
          action == "EXIT_FAILED" and len(b.broker.open_stops("FAILX")) == 1 and b.broker.pos.get("FAILX") == 30)

    b = make_bot()
    entered(b, "GONE")
    b.state.update_position("GONE", entry_time=(bot.now_et() - timedelta(minutes=5)).isoformat())
    b.broker.held = lambda s: 0                          # let the "manual" close through
    b.broker._move("GONE", -30)                          # closed by hand in Alpaca, stop still sitting there
    del b.broker.held
    _, out = run(b.sync.sync)
    check("closed by hand: the leftover stop order is cancelled (it could open a short)",
          not b.broker.open_stops("GONE") and "leftover stop" in out and not b.state.has_position("GONE"))

    b = make_bot()
    b.prices["CRASH"] = 50.0
    run(lambda: b.alpaca.buy("CRASH", 10))
    run(lambda: b.alpaca.place_stop("CRASH", 10, "LONG", 48.0))   # yesterday's bot protected it, then crashed
    run(b.sync.sync)
    check("yesterday's position keeps its stop (protection isn't removed)", len(b.broker.open_stops("CRASH")) == 1)

    b = make_bot()
    b.broker.reject_stops = True
    entered(b, "NOSTOP")
    b.broker.reject_stops = False
    b.state.update_position("NOSTOP", entry_time=(bot.now_et() - timedelta(minutes=5)).isoformat())
    run(lambda: b.monitor.check_position("NOSTOP"))
    check("if the stop order was rejected at entry, the next check places it",
          len(b.broker.open_stops("NOSTOP")) == 1)

    b = make_bot()
    entered(b, "DUPE")
    run(lambda: b.alpaca.place_stop("DUPE", 30, "LONG", 99.0))    # a second stop for the same shares
    _, out = run(b.sync.sync)
    check("duplicate stop order is cancelled (two stops could flip the position)",
          len(b.broker.open_stops("DUPE")) == 1 and "duplicate" in out)

    b = make_bot()
    entered(b, "QTY")
    b.state.update_position("QTY", entry_time=(bot.now_et() - timedelta(minutes=5)).isoformat())
    b.broker.held = lambda s: 0
    b.broker._move("QTY", -10)                           # 10 shares sold by hand
    del b.broker.held
    run(b.sync.sync)
    b.prices["QTY"] = 100.2
    run(lambda: b.monitor.check_position("QTY"))
    stops = b.broker.open_stops("QTY")
    check("share count changed -> stop order resized to the 20 left", len(stops) == 1 and stops[0].qty == 20)

if section("BUG 11: market calendar, early closes, commands", "calendar"):
    today = bot.now_et().date()

    def with_calendar(b, days):
        b.broker.get_calendar = lambda req: days
        return b

    def day(open_t, close_t):
        return NS(date=today, open=datetime.combine(today, datetime.strptime(open_t, "%H:%M").time()),
                  close=datetime.combine(today, datetime.strptime(close_t, "%H:%M").time()))

    b = with_calendar(make_bot(), [day("09:30", "16:00")])
    check("normal day: close positions 15:55, market closes 16:00",
          bot.todays_close_times(b.alpaca) == ("15:55", "16:00"))
    b = with_calendar(make_bot(), [day("09:30", "13:00")])
    check("early close (day after Thanksgiving): close positions 12:55",
          bot.todays_close_times(b.alpaca) == ("12:55", "13:00"))
    b = with_calendar(make_bot(), [])
    check("holiday: market closed today", bot.todays_close_times(b.alpaca) is None)
    b = make_bot()
    b.broker.get_calendar = lambda req: (_ for _ in ()).throw(ConnectionError("down"))
    r, _ = run(lambda: bot.todays_close_times(b.alpaca))
    check("calendar unreachable: fall back to the normal 15:55 / 16:00", r == ("15:55", "16:00"))

    b = with_calendar(make_bot(), [])
    engine = bot.TradingEngine.__new__(bot.TradingEngine)
    engine.alpaca, engine.state, engine.log, engine.sync = b.alpaca, b.state, b.log, b.sync
    engine.scanner, engine.monitor, engine.running, engine.last_scan_time = None, b.monitor, False, None
    _, out = run(engine.run)
    check("engine on a holiday: says so and stops without trading", "market is closed today" in out
          and not b.broker.orders)

    def monitor_at(clock):
        b = with_calendar(make_bot(), [day("09:30", "16:00")])
        b.prices["MON"] = 50.0
        run(lambda: b.alpaca.buy("MON", 10))
        track(b, "MON", "LONG", 10, 50.0, 49.0, 51.5, 53.0)
        b.prices["MON"] = 48.5                     # below the $49 stop
        real = (bot.AlpacaClient, bot.PositionStateManager, bot.PaperTradeLog, bot.now_et)
        bot.AlpacaClient, bot.PositionStateManager, bot.PaperTradeLog = (lambda: b.alpaca), (lambda: b.state), (lambda: b.log)
        bot.now_et = lambda: datetime.combine(today, datetime.strptime(clock, "%H:%M").time())
        try:
            _, out = run(bot.cmd_monitor)
        finally:
            bot.AlpacaClient, bot.PositionStateManager, bot.PaperTradeLog, bot.now_et = real
        return b, out

    b, out = monitor_at("10:00")
    check("'monitor' at 10:00: exits the stopped-out trade, then stops",
          "HIT STOP LOSS" in out and "All positions closed" in out and "MON" not in b.broker.pos)
    b, out = monitor_at("15:57")
    check("'monitor' after 15:55: end-of-day close", "EOD - Closing all" in out and "MON" not in b.broker.pos)

if section("SCANNER: today's gaps (up and down), fresh files only", "scanner"):
    import json
    import os
    import premarket_scanner as pm
    import merge_watchlists as mw
    import numpy as np

    today = datetime.now(pm.ET).date()
    yday = today - timedelta(days=1)
    dby = today - timedelta(days=2)

    def tz(ts):
        return pd.DatetimeIndex(ts).tz_localize("America/New_York")

    class FakeTicker:
        """Yahoo before the open: daily bars end yesterday; 1-min bars include today's pre-market."""
        def __init__(self, sym, prev_close, premarket_price, with_today_daily=False):
            self.prev_close, self.pm, self.with_today = prev_close, premarket_price, with_today_daily
        def history(self, period=None, interval="1d", prepost=False):
            if interval == "1d":
                days = [dby, yday] + ([today] if self.with_today else [])
                closes = [self.prev_close * 0.9, self.prev_close] + ([self.pm * 1.1] if self.with_today else [])
                return pd.DataFrame({"Open": closes, "Close": closes, "Volume": [1e6] * len(days)},
                                    index=tz([datetime.combine(d, datetime.min.time()) for d in days]))
            stamps = [datetime.combine(yday, datetime.min.time()) + timedelta(hours=15, minutes=59),
                      datetime.combine(today, datetime.min.time()) + timedelta(hours=8),
                      datetime.combine(today, datetime.min.time()) + timedelta(hours=9, minutes=20)]
            return pd.DataFrame({"Close": [self.prev_close, self.pm * 0.99, self.pm], "Volume": [5e4, 1e4, 2e4]},
                                index=tz(stamps))

    real_ticker = pm.yf.Ticker
    scanner = pm.PreMarketScanner.__new__(pm.PreMarketScanner)
    try:
        pm.yf.Ticker = lambda s: FakeTicker(s, 50.0, 53.0)
        d = scanner.get_stock_data_yahoo("UP")
        check("gap = today's pre-market price vs yesterday's close (+6.0%)",
              d and d["prev_close"] == 50.0 and d["current_price"] == 53.0 and d["gap_pct"] == 6.0, str(d and d["gap_pct"]))
        pm.yf.Ticker = lambda s: FakeTicker(s, 50.0, 53.0, with_today_daily=True)
        d = scanner.get_stock_data_yahoo("UP")
        check("a half-formed daily bar for today is not used as 'yesterday'", d and d["prev_close"] == 50.0)
        pm.yf.Ticker = lambda s: FakeTicker(s, 40.0, 37.6)
        d = scanner.get_stock_data_yahoo("DOWN")
        check("gap-down measured too (-6.0%)", d and d["gap_pct"] == -6.0)
    finally:
        pm.yf.Ticker = real_ticker

    fake_rows = {"UP": 6.0, "DOWN": -6.0, "FLAT": 1.0}
    scanner = pm.PreMarketScanner.__new__(pm.PreMarketScanner)
    scanner.use_alpaca, scanner.min_gap_pct, scanner.min_price, scanner.max_price = False, 3.0, 5.0, 500.0
    scanner.min_avg_daily_volume = 500000
    scanner.get_universe = lambda: list(fake_rows)
    scanner.get_stock_data_yahoo = lambda s: {"symbol": s, "prev_close": 50.0, "current_price": 50.0,
                                              "gap_pct": fake_rows[s], "volume": 1, "avg_volume": 2e6,
                                              "relative_volume": 0.1}
    scanner.check_news = lambda s: {"has_news": False, "headline": "", "catalyst_type": "none"}
    found, _ = run(lambda: scanner.scan())
    check("gap-ups AND gap-downs make the list (shorts need them)", {s["symbol"] for s in found} == {"UP", "DOWN"})

    out_dir = tempfile.mkdtemp()
    pm.OUTPUT_DIR = out_dir
    old = {"scan_time": "2026-05-06T08:56:15", "count": 1, "stocks": [{"symbol": "MSTR", "gap_pct": 3.1}]}
    with open(os.path.join(out_dir, "watchlist_premarket.json"), "w") as f:
        json.dump(old, f)
    real_cls = pm.PreMarketScanner
    pm.PreMarketScanner = lambda: NS(scan=lambda require_news=False: [])
    try:
        run(lambda: pm.run_premarket_scan(save=True))
    finally:
        pm.PreMarketScanner = real_cls
    saved = json.load(open(os.path.join(out_dir, "watchlist_premarket.json")))
    check("a scan that finds nothing still overwrites the old file", saved["count"] == 0 and saved["stocks"] == [])

    def write(name, scan_time, stocks):
        with open(os.path.join(out_dir, name), "w") as f:
            json.dump({"scan_time": scan_time, "stocks": stocks}, f)

    stamp = lambda d: datetime.combine(d, datetime.min.time()).isoformat()
    write("watchlist_premarket.json", "2026-05-06T08:56:15", [{"symbol": "MSTR", "gap_pct": 3.1, "score": 60}])
    write("watchlist_eod.json", stamp(yday), [{"symbol": "ARM", "score": 40, "patterns": []}])
    merged, out = run(lambda: mw.merge_watchlists(os.path.join(out_dir, "watchlist_premarket.json"),
                                                  os.path.join(out_dir, "watchlist_eod.json"),
                                                  os.path.join(out_dir, "watchlist.json")))
    check("Oct 9 replay: a May pre-market file is ignored", [s["symbol"] for s in merged] == ["ARM"] and "not today" in out)
    write("watchlist_eod.json", stamp(today - timedelta(days=6)), [{"symbol": "ARM", "score": 40, "patterns": []}])
    write("watchlist_premarket.json", stamp(today), [{"symbol": "UP", "gap_pct": 6.0, "score": 70}])
    merged, out = run(lambda: mw.merge_watchlists(os.path.join(out_dir, "watchlist_premarket.json"),
                                                  os.path.join(out_dir, "watchlist_eod.json"),
                                                  os.path.join(out_dir, "watchlist.json")))
    check("today's pre-market used; a 6-day-old end-of-day file is ignored",
          [s["symbol"] for s in merged] == ["UP"] and "too old" in out)

    write("watchlist_premarket.json", stamp(today), [{"symbol": "MSTR", "gap_pct": -3.2, "score": 35},
                                                     {"symbol": "HOOD", "gap_pct": 4.0, "score": 40}])
    write("watchlist_eod.json", stamp(yday), [{"symbol": "MSTR", "score": 90, "pattern_names": ["bull_flag"]},
                                             {"symbol": "HOOD", "score": 70, "pattern_names": ["pullback_to_ma"]}])
    merged, _ = run(lambda: mw.merge_watchlists(os.path.join(out_dir, "watchlist_premarket.json"),
                                                os.path.join(out_dir, "watchlist_eod.json"),
                                                os.path.join(out_dir, "watchlist.json")))
    by = {s["symbol"]: s for s in merged}
    check("gap UP + bullish pattern gets the A+ bonus", by["HOOD"]["source"] == "both" and by["HOOD"]["score"] == 70)
    check("gap DOWN + bullish pattern: no bonus, still listed as a gap-down",
          by["MSTR"]["source"] == "premarket" and by["MSTR"]["score"] == 35 and by["MSTR"]["gap_pct"] == -3.2)

    print("   -- the bot reading the watchlist --")
    b = make_bot()
    bot_dir = tempfile.mkdtemp()
    os.makedirs(os.path.join(bot_dir, "output"))
    real_dir, bot.BOT_DIR = bot.BOT_DIR, bot_dir
    try:
        s = bot.EntryScanner(b.alpaca, b.state, b.log, b.sync)
        _, out = run(s.load_watchlist)
        check("no watchlist -> no stocks (no made-up NVDA/AMD/TSLA list)", s.symbols == [] and "No scanner watchlist" in out)
        with open(os.path.join(bot_dir, "output", "watchlist.json"), "w") as f:
            json.dump({"last_updated": "2026-10-09T10:52:34", "stocks": [{"symbol": "MSTR"}]}, f)
        _, out = run(s.load_watchlist)
        check("old watchlist -> no stocks, says why", s.symbols == [] and "not today" in out)
        with open(os.path.join(bot_dir, "output", "watchlist.json"), "w") as f:
            json.dump({"last_updated": bot.now_et().isoformat(), "stocks": [{"symbol": "UP"}, {"symbol": "DOWN"}]}, f)
        run(s.load_watchlist)
        check("today's watchlist -> its stocks", s.symbols == ["UP", "DOWN"])
    finally:
        bot.BOT_DIR = real_dir

if section("LIVE PRICES: one-sided quotes never become fake prices", "prices"):
    from datetime import timezone

    def price_with(bid, ask, trade_price, trade_age_min, yahoo_price=99.0):
        a = bot.AlpacaClient.__new__(bot.AlpacaClient)
        a.sim_mode = False
        now = datetime.now(timezone.utc)
        a.data_client = NS(
            get_stock_latest_quote=lambda req: {"X": NS(bid_price=bid, ask_price=ask)},
            get_stock_latest_trade=lambda req: {"X": NS(price=trade_price, timestamp=now - timedelta(minutes=trade_age_min))})
        real = bot.yf.Ticker
        bot.yf.Ticker = lambda s: NS(history=lambda **k: pd.DataFrame({"Close": [yahoo_price]}))
        try:
            return a.get_current_price("X")
        finally:
            bot.yf.Ticker = real

    check("normal two-sided quote -> midpoint", price_with(100.0, 100.10, 100.02, 0) == 100.05)
    check("AAPL case: bid $0.01 / ask $0 -> latest trade, not $0.01", price_with(0.01, 0.0, 341.05, 1) == 341.05)
    check("MSTR case: ask $0 -> latest trade, not half price", price_with(145.77, 0.0, 153.33, 1) == 153.33)
    check("very wide quote (5%) -> latest trade", price_with(95.0, 100.0, 97.5, 1) == 97.5)
    check("one-sided quote and an old trade -> Yahoo's last minute", price_with(0.0, 0.0, 120.0, 30) == 99.0)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
