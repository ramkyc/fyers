---
story:
  title: "feat: Enhance Backtesting Engine for Multi-Timeframe Data"
  epic: "Backtesting Strategy Framework"
  status: "Ready for Review"
  version: 1.0
  creationDate: "2025-09-07"
  updateDate: "2025-09-07"
  author: "po-Sarah"
  owner: "dev-James"
  prd: "docs/prd-opening-price-crossover.md"

acceptanceCriteria:
  - "The `BacktestingEngine` MUST be able to load and provide data for multiple specified resolutions to the `on_data` method of a strategy."
  - "Strategies MUST be able to request and access historical data for any loaded resolution within the `on_data` method (e.g., a 15-min strategy can access 1-min data)."
  - "The `on_data` method MUST receive a data structure that includes OHLCV for all relevant timeframes for the current timestamp."
  - "The engine's performance MUST NOT be significantly degraded by multi-timeframe data loading."

tasks:
  - task: "Task 1: Modify BacktestingEngine._load_data"
    subtasks:
      - "[x] Update `_load_data` to accept a list of resolutions and load data for all of them."
      - "[x] Store loaded data in a way that allows easy access by resolution (e.g., `self.data[resolution][symbol]`)."
  - task: "Task 2: Modify BacktestingEngine.run"
    subtasks:
      - "[x] Update the event loop to iterate through the primary resolution's timestamps."
      - "[x] For each timestamp, prepare `current_market_data` to include OHLCV from all loaded resolutions for all symbols."
      - "[x] Pass this enhanced `current_market_data` to `strategy.on_data`."
  - task: "Task 3: Update BaseStrategy.on_data Signature"
    subtasks:
      - "[x] Modify `BaseStrategy.on_data` to accept the new multi-timeframe data structure."
      - "[x] Update existing strategies (e.g., `SMACrossoverStrategy`) to be compatible with the new signature (even if they don't use multi-timeframe data)."
  - task: "Task 4: Write Unit Tests for Engine Enhancement"
    subtasks:
      - "[x] Create a new test file for the engine's multi-timeframe capabilities."
      - "[x] Write tests to verify correct loading and access of data from multiple resolutions."
  - task: "Task 5: Update run_backtest.py"
    subtasks:
      - "[x] Modify `run_backtest.py` to allow specifying multiple resolutions for the backtest engine."

devNotes: |
  - This is a foundational change. Ensure backward compatibility for existing single-resolution strategies if possible.
  - Consider how to efficiently query and provide lower-timeframe data within the `on_data` loop without excessive database hits.

testing:
  - "Unit tests are required for the engine's multi-timeframe data handling."
  - "Existing backtests should still function correctly after this change."

qaResults:
  status: "Pass with Concerns"
  notes: |
    - The implementation of the multi-timeframe engine enhancement is robust and meets the functional requirements. The unit tests are comprehensive for the functional aspects.
    - Concern 1 (Minor): Performance degradation (AC4) is not unit tested. This would require dedicated performance tests.
    - Concern 2 (Minor): The `sys.path` modification in the test file (`tests/backtesting/test_engine_multi_timeframe.py`) is a code smell and should be replaced with a proper `pytest` configuration in `pyproject.toml` to improve project robustness.

devAgentRecord:
  agentModelUsed: "Gemini"
  debugLogReferences:
    - "Resolved `ModuleNotFoundError` by adding `sys.path` modification to test files."
    - "Fixed `AttributeError` in `BacktestingEngine.run` print statement."
    - "Corrected `MockStrategy` usage in tests to properly capture `on_data` calls."
    - "Refined test assertions for multi-resolution data to account for timestamp alignment."
  completionNotes:
    - "The backtesting engine now supports loading and passing multi-timeframe OHLCV data to strategies."
    - "All unit tests for the engine enhancement are passing."
    - "Existing strategies (`SMACrossoverStrategy`, `OpeningPriceCrossoverStrategy`) have been updated to be compatible with the new `on_data` signature."
  fileList:
    - "src/backtesting/engine.py"
    - "src/strategies/base_strategy.py"
    - "src/strategies/simple_ma_crossover.py"
    - "src/strategies/opening_price_crossover.py"
    - "tests/backtesting/test_engine_multi_timeframe.py"
    - "run_backtest.py"
  changeLog:
    - "Modified BacktestingEngine to load and pass multi-resolution data."
    - "Updated BaseStrategy and existing strategies for new on_data signature."
    - "Added unit tests for engine multi-timeframe capabilities."
    - "Updated run_backtest.py to accept multiple resolutions."
---
