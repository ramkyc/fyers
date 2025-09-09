# Feature Requests & Ideas Backlog

This document serves as a central backlog for all new features, enhancements, and major ideas for the TraderBuddy platform. When we decide to work on a feature from this list, the first step will be to create a formal Project Brief for it.

---

## Planned Features (Not Started)

### 1. Advanced Capital Management Module

*   **Goal:** To move beyond fixed-quantity trades and implement a dynamic capital allocation system.
*   **Core Requirements:**
    *   The system should be able to fetch real-time funds and margin information from the Fyers API.
    *   Strategies should be able to define position sizes based on a percentage of available capital or a fixed risk amount.
    *   The `OrderManager` needs to be enhanced to support different product types (`CNC`, `INTRADAY`, `MARGIN`).
    *   The dashboard should display a summary of available funds.
*   **Status:** Awaiting Project Brief.

### 2. New Personal Strategy: [Your Strategy Name Here]

*   **Goal:** To implement and test a new, proprietary trading strategy.
*   **Core Requirements:**
    *   The exact logic (entry signals, exit signals, stop-loss, targets) needs to be defined.
    *   We need to determine if the strategy requires any new data points or indicators that are not currently available in the system.
    *   This will likely require creating a new strategy file in `src/strategies/` and integrating it into the platform.
*   **Status:** Awaiting Project Brief.
*   
### 3. Investigate Live Trade Execution for SMA Strategy

*   **Goal:** To diagnose and understand why the `SMACrossoverStrategy` is not generating trades during live paper trading sessions, even though the engine is processing ticks and creating bars.
*   **Core Requirements:**
    *   Implement enhanced, detailed logging within the `LiveTradingEngine` and/or the `SMACrossoverStrategy`.
    *   The logs should capture the state of key variables at the exact moment the strategy's `on_data` method is called for a specific symbol.
    *   This includes: the short and long EMA values, the previous EMA values, the current LTP, and the reason a trade was or was not generated (e.g., "crossover condition not met", "position already exists").
    *   Perform a code walkthrough or use the enhanced logs to trace the decision-making process for a live symbol over several bars to pinpoint the issue.
*   **Status:** Awaiting Analysis.

---

## Completed Features

*(This section can be used to track major features as they are completed and merged into the main branch.)*