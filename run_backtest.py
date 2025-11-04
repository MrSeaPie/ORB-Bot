# File: run_backtest.py  (FULL FILE REPLACEMENT)

from engine.backtest import run_batch, load_cfg
from collections.abc import Mapping

WATCHLIST = ["AAPL", "NVDA", "TSLA", "AMD", "META", "MSFT"]

def coerce_total_pnl(x) -> float:
    """Return a float PnL from whatever shape run_batch gave us."""
    if x is None:
        return 0.0
    # dict-like: expect a 'total_pnl' key
    if isinstance(x, Mapping):
        val = x.get("total_pnl", 0.0)
        try:
            return float(val)
        except Exception:
            return 0.0
    # tuple/list: try the last element as PnL
    if isinstance(x, (list, tuple)):
        if not x:
            return 0.0
        try:
            return float(x[-1])
        except Exception:
            return 0.0
    # already a number?
    try:
        return float(x)
    except Exception:
        return 0.0

def iter_stats_values(results):
    """Yield the values to sum over, regardless of structure."""
    if isinstance(results, Mapping):
        # could be {"AAPL": {...}, ..., "TOTAL": 61.8} or just symbol->dict
        for k, v in results.items():
            # ignore keys that look like headers if needed; otherwise just yield
            yield v
    elif isinstance(results, (list, tuple)):
        for v in results:
            yield v
    else:
        # single scalar or odd return — just yield it
        yield results

def main():
    cfg = load_cfg("config/paper.yaml")
    results = run_batch(WATCHLIST, cfg)  # prints per-symbol lines internally

    # robustly sum any mixture of dicts/tuples/floats
    total = sum(coerce_total_pnl(v) for v in iter_stats_values(results))
    print(f"\nTOTAL PnL across {len(WATCHLIST)} symbols: ${total:.2f}")

if __name__ == "__main__":
    main()
