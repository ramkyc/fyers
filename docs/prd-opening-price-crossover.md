# Product Requirements Document: Opening Price Crossover Strategy (V1)

## 1. Introduction & Goals

*   **Introduction:** This document outlines the requirements for creating a new long-only positional trading strategy, "Opening Price Crossover Strategy (V1)," for backtesting. The strategy aims to achieve consistent returns with low drawdown.
*   **Goals:**
    *   Primary: Develop and backtest a profitable strategy achieving ~10% monthly returns with a maximum drawdown below 15%.
    *   Secondary: Establish a baseline (V1) of the strategy to enable future iteration and the development of more complex filters (V2).

## 2. User Stories

*   **As a strategy analyst, I want to backtest the 'Opening Price Crossover' strategy (V1) so that I can evaluate its performance and viability against my target metrics.**

## 3. Features & Technical Requirements

### 3.1. Strategy Logic (V1)

The strategy will be implemented as a new Python class, likely in `src/strategies/opening_price_crossover.py`.

*   **Filter:** A long entry is only considered if the `9-period Exponential Moving Average (EMA)` is greater than the `21-period EMA`.
*   **Entry Signal:** A long position is initiated when the `close` price of a candle crosses above its `open` price, and the EMA filter is satisfied.
*   **Stop-Loss:** The initial stop-loss is placed at the minimum value of either the entry candle's `low` or the previous candle's `low`.
*   **Risk/Reward Exits:**
    *   The initial risk ("R") is defined as the difference between the entry price and the stop-loss price.
    *   **Target 1:** 70% of the position is exited when the price reaches a 1R profit target (Entry Price + 1*R).
    *   **Target 2:** The remaining 30% of the position is exited when the price reaches a 3R profit target (Entry Price + 3*R).
*   **Position Management:** Once a position is open for a specific symbol, no new long entries will be taken for that same symbol until the current position is fully closed.

### 3.2. Technical Implementation

*   **Libraries:** The use of established technical analysis libraries such as `pandas-ta` or `TA-Lib` is encouraged for calculating indicators like EMA.
*   **Integration:** The strategy must be compatible with the existing backtesting engine located at `src/backtesting/engine.py`.
*   **Configuration:** The strategy should be runnable from `run_backtest.py`, accepting parameters like symbols and initial cash.

### 3.3. Backtesting Configuration

*   **Start Date:** The backtest period will begin on **April 1, 2024**.
*   **Timeframes:** The strategy will be run and evaluated on **15-minute, 30-minute, 1-hour, and Daily** timeframes.
*   **Asset Universe:** The backtest will run on the top 10 NIFTY 50 stocks for which historical data is available.
*   **Capital:** The simulation will use an initial capital of **₹100,000 per symbol**.

## 4. Out of Scope

*   **Advanced Crossover Filter:** The "LTP Crossover Count" filter is explicitly deferred to a future version (V2).
*   **Engine Refactoring:** Any modifications to the backtesting engine to support multi-timeframe analysis are out of scope for this project.
*   **Short Selling & Other Asset Classes:** The strategy is long-only and will only be tested on the specified equity symbols.
*   **Live Trading:** This project is for backtesting purposes only.

## 5. Success Metrics

The success of the V1 strategy will be judged based on the following metrics from the backtest report:

*   **Primary KPI:** Average Monthly Return ≥ 10%.
*   **Primary KPI:** Maximum Drawdown < 15%.
*   **Secondary KPI:** A Sharpe Ratio > 1.5 would be considered favorable.

## 6. Assumptions

*   The historical 1-minute, 15-minute, 30-minute, 1-hour, and Daily OHLCV data stored in `historical_market_data.sqlite` is accurate and sufficient for this backtest.
*   The existing backtesting engine is capable of handling the logic defined for V1 without modification.
