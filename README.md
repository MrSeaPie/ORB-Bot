# ORB Trading Bot Framework

## Quick Start

1. Run the backtest:
```bash
python run_framework.py
```

2. Check results in `logs/trades/` folder (CSV files)

3. Tune parameters in `run_framework.py` and run again!

## What's New

- **TradeLogger**: Records every trade with full context
- **PerformanceAnalyzer**: Shows what works and what doesn't
- **Modular Design**: Easy to test different configs

## How To Tune

Open `run_framework.py` and change the numbers:
```python
cfg = ORBConfig(
    trade_start="09:40",        # Enter earlier
    base_tight_frac=0.8,        # Tighter base
    base_near_vwap_atr=0.3,     # Closer to VWAP
    vwap_stop_buffer_atr=0.20,  # Wider stop
)
```

## Files

- `framework.py` - Core engine (TradeLogger, Analyzer, Strategy)
- `run_framework.py` - How to run backtests
- `logs/trades/` - Your trade results (CSV files)

## Next Steps

1. Run default config
2. Check CSV in Excel
3. Find patterns
4. Adjust parameters
5. Run again and compare!