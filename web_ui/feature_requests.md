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
---

## Completed Features

### 1. Stabilize Live Trading and Backtesting
*   **Goal:** To diagnose and fix issues preventing the live paper trading engine from executing trades and to resolve regressions in the backtesting engine.
*   **Outcome:** Implemented detailed logging to debug the live engine, fixed several data contract and UI state bugs, and stabilized the backtesting engine for all timeframes. The system is now in a reliable working state.
*   **Status:** Completed.