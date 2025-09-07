# Project Brief: Opening Price Crossover Strategy

## 1. Project Overview
Creation of a new long-only backtesting strategy with defined filters. The project will leverage existing software libraries like TA-Lib or pandas-ta where applicable. The strategy will be developed in two versions, with V1 (MVP) being the focus of this brief.

## 2. Business Objectives & Success Metrics
*   **Objective:** Develop a profitable, low-drawdown positional trading strategy.
*   **Success Metric (KPI):** Achieve an average monthly return of approximately 10% during backtesting.
*   **Success Metric (KPI):** Maintain a maximum drawdown of less than 15% during backtesting.

## 3. Scope & Features (Version 1 - MVP)
*   **Strategy Implementation:**
    *   **Filter:** The strategy will only take long entries when the `9-period EMA` is greater than the `21-period EMA`.
    *   **Entry Signal:** A long entry is triggered when the `close` price of a candle crosses above its `open` price, provided the EMA filter is met.
    *   **Position Sizing & Exit:**
        *   **Target 1:** Exit 70% of the position at a 1:1 Risk/Reward ratio.
        *   **Target 2:** Exit the remaining 30% of the position at a 1:3 Risk/Reward ratio.
    *   **Stop-Loss:** The stop-loss will be set at the minimum value of either the current (entry) candle's low or the previous candle's low.
*   **Backtesting Parameters:**
    *   **Start Date:** April 1, 2024.
    *   **Timeframes:** The strategy will be tested on 15-minute, 30-minute, 1-hour, and Daily chart intervals.
    *   **Capital Allocation:** ₹1 lakh per symbol.
*   **Integration:** The new strategy will be integrated into the existing Python-based backtesting engine.
*   **Documentation:**
    *   This Project Brief.
    *   A task will be created in `docs/todo/backtesting-enhancements.md` to track the V2 feature.

## 4. Out of Scope (Version 1)
*   **Advanced Crossover Filter:** The "LTP Crossover Count" filter is deferred to V2, pending an upgrade to the backtesting engine.
*   **Backtesting Engine Refactoring:** The work to upgrade the engine to support multi-timeframe analysis is considered a separate, subsequent project.
*   **Short Selling:** The strategy is long-only. No short positions will be taken.
*   **Live Trading:** This project is strictly for backtesting and performance analysis.

## 5. Stakeholders
*   **Project Owner:** You (the user).
*   **Execution Team:** Specialist agents from the BMad method (Architect, Dev, QA) will be engaged as required.

## 6. Risks & Dependencies
*   **Risk:** The simplified V1 strategy may not meet the performance targets without the more advanced filter planned for V2.
*   **Dependency:** The backtest relies on the historical data stored locally. Future data integrity depends on the Fyers API.
