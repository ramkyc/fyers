# Backtesting Engine Enhancements Plan

This document outlines the phased implementation plan for enhancing the backtesting engine with intraday/positional capabilities and time-based controls. We will use this as a checklist to track our progress.

## Phase 1: User Interface Enhancements (Complete)

*   [x] **Task 1.1: Add Backtest Type Toggle**
    *   **File**: `web_ui/dashboard.py`
    *   **Action**: Add a `st.radio` button in the sidebar for `Backtest Type` with options: "Positional" and "Intraday".

*   [x] **Task 1.2: Upgrade to Datetime Pickers**
    *   **File**: `web_ui/dashboard.py`
    *   **Action**: Replace the `st.date_input` widgets for "Start Date" and "End Date" with `st.datetime_input` to allow users to select specific times.

## Phase 2: Core Engine Refactoring

*   [x] **Task 2.1: Convert `BacktestingEngine` to Event-Driven**
    *   **File**: `src/backtesting/engine.py`
    *   **Action**: Rewrite the `run()` method. Instead of generating all signals at once (vectorized), it will now loop through each timestamp in the historical dataset. In each iteration, it will pass the current candle's data to the strategy's `on_data` method. This is the most significant change.

*   [x] **Task 2.2: Adapt Strategies for Event-Driven Backtesting**
    *   **File**: `src/strategies/simple_ma_crossover.py`
    *   **Action**: The `on_data` method, previously used only for live trading, will now be the primary logic for backtesting as well. The `generate_signals` method will be deprecated or removed.

## Phase 3: Implement New Trading Rules

*   [x] **Task 3.1: Implement Time-Windowed Entries**
    *   **File**: `src/backtesting/engine.py`
    *   **Action**: Inside the new `run()` loop, add a condition to only call the strategy for signal generation if the current candle's timestamp falls within the user-specified time window (e.g., between 09:30 and 14:40).

*   [x] **Task 3.2: Implement Intraday Forced Exits**
    *   **File**: `src/backtesting/engine.py`
    *   **Action**: Add logic to the `run()` loop. If the backtest type is "Intraday" and the current candle's time is 15:14 or later, the engine will automatically iterate through all open positions taken that day and execute orders to close them.

*   [x] **Task 3.3: Prevent Position Pyramiding**
    *   **File**: `src/strategies/simple_ma_crossover.py` (and `base_strategy.py`)
    *   **Action**: Modify the `on_data` method in the strategy to check if a position for a given symbol already exists (`self.portfolio.get_position(symbol)`) before issuing a new 'BUY' signal. This enforces the "no adding to an open position" rule.

## Phase 4: Final Integration & Testing

*   [x] **Task 4.1: Connect UI to Engine**
    *   **File**: `web_ui/dashboard.py`
    *   **Action**: Ensure the new UI controls (Backtest Type, Start/End Datetime) are correctly passed to the `BacktestingEngine`.

*   [x] **Task 4.2: Write New Unit & Integration Tests**
    *   **Files**: `tests/backtesting/test_engine.py`, `tests/strategies/test_simple_ma_crossover.py`
    *   **Action**: Create new tests to validate:
        *   Intraday positions are closed correctly.
        *   Positional trades are held overnight.
        *   Entry time windows are respected.
        *   Pyramiding is prevented.

*   [x] **Task 4.3: Update Documentation**
    *   **Files**: `docs/user_guide.md`, `docs/brownfield-architecture.md`
    *   **Action**: Update the documentation to reflect the new, more powerful backtesting capabilities.

*   [x] **Task 4.4: Update Changelog**
    *   **File**: `CHANGELOG.md`
    *   **Action**: Add an entry for the new backtesting features.