# Backtesting Engine Enhancements

## Task: Enable Multi-Timeframe Analysis

**Date Added:** 2025-09-07

**Project:** Opening Price Crossover Strategy (V2)

**Description:**
The current backtesting engine (`src/backtesting/engine.py`) is designed to load and operate on a single data resolution (timeframe) at a time. To support more advanced strategies, the engine needs to be upgraded.

**Requirements:**
1.  Modify the `BacktestingEngine` to allow a strategy to access more than one data resolution simultaneously.
2.  For example, a strategy running on a 15-minute primary timeframe should be able to request and process 1-minute data for the same period.
3.  This will enable the implementation of the "LTP Crossover Count" filter for the "Opening Price Crossover Strategy".
