---
story:
  title: "feat: Enhance Backtesting Engine for Multi-Timeframe Data"
  epic: "Backtesting Strategy Framework"
  status: "Ready for Development"
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
      - "[ ] Update `_load_data` to accept a list of resolutions and load data for all of them."
      - "[ ] Store loaded data in a way that allows easy access by resolution (e.g., `self.data[resolution][symbol]`)."
  - task: "Task 2: Modify BacktestingEngine.run"
    subtasks:
      - "[ ] Update the event loop to iterate through the primary resolution's timestamps."
      - "[ ] For each timestamp, prepare `current_market_data` to include OHLCV from all loaded resolutions for all symbols."
      - "[ ] Pass this enhanced `current_market_data` to `strategy.on_data`."
  - task: "Task 3: Update BaseStrategy.on_data Signature"
    subtasks:
      - "[ ] Modify `BaseStrategy.on_data` to accept the new multi-timeframe data structure."
      - "[ ] Update existing strategies (e.g., `SMACrossoverStrategy`) to be compatible with the new signature (even if they don't use multi-timeframe data)."
  - task: "Task 4: Write Unit Tests for Engine Enhancement"
    subtasks:
      - "[ ] Create a new test file for the engine's multi-timeframe capabilities."
      - "[ ] Write tests to verify correct loading and access of data from multiple resolutions."
  - task: "Task 5: Update run_backtest.py"
    subtasks:
      - "[ ] Modify `run_backtest.py` to allow specifying multiple resolutions for the backtest engine."

devNotes: |
  - This is a foundational change. Ensure backward compatibility for existing single-resolution strategies if possible.
  - Consider how to efficiently query and provide lower-timeframe data within the `on_data` loop without excessive database hits.

testing:
  - "Unit tests are required for the engine's multi-timeframe data handling."
  - "Existing backtests should still function correctly after this change."

qaResults:
  status: "Pending"
  notes: ""

devAgentRecord:
  agentModelUsed: ""
  debugLogReferences: []
  completionNotes: []
  fileList: []
  changeLog: []
---
