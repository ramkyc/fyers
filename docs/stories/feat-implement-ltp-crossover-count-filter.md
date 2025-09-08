---
story:
  title: "feat: Implement LTP Crossover Count Filter"
  epic: "Backtesting Strategy Framework"
  status: "Ready for Review"
  version: 1.0
  creationDate: "2025-09-07"
  updateDate: "2025-09-07"
  author: "po-Sarah"
  owner: "dev-James"
  prd: "docs/prd-opening-price-crossover.md"
  dependsOn: "feat-enhance-backtesting-engine-multi-timeframe.md"

acceptanceCriteria:
  - "The `OpeningPriceCrossoverStrategy` MUST correctly calculate the 'implied crossover count' for a higher timeframe candle (e.g., 15-min) by analyzing 1-minute data within that candle's period."
  - "The strategy MUST correctly calculate the 'average implied crossover count' over the last 10 higher-timeframe candles."
  - "The strategy MUST correctly apply the 'average crossover count' filter: an entry is taken only when the current candle's implied crossover count crosses *above* the average implied crossover count."
  - "Unit tests MUST be added to verify the 'implied crossover count' calculation and the filter logic."

tasks:
  - task: "Task 1: Modify OpeningPriceCrossoverStrategy.on_data"
    subtasks:
      - "[x] Update `on_data` to accept and utilize the multi-timeframe data provided by the enhanced engine."
  - task: "Task 2: Implement Implied Crossover Count Calculation"
    subtasks:
      - "[x] Develop logic to calculate the 'implied crossover count' for the current higher-timeframe candle using lower-timeframe data."
  - task: "Task 3: Implement Average Crossover Count Calculation"
    subtasks:
      - "[x] Develop logic to calculate the 'average implied crossover count' over the last 10 higher-timeframe candles."
  - task: "Task 4: Integrate Filter into Entry Logic"
    subtasks:
      - "[x] Integrate the 'average crossover count' filter into the entry conditions of the `OpeningPriceCrossoverStrategy`."
  - task: "Task 5: Write Unit Tests for New Filter"
    subtasks:
      - "[x] Create new unit tests to verify the 'implied crossover count' calculation."
      - "[x] Create new unit tests to verify the 'average crossover count' filter logic, including edge cases."

devNotes: |
  - This story is dependent on the completion of 'feat-enhance-backtesting-engine-multi-timeframe.md'.
  - The implementation should be robust to handle cases where lower-timeframe data might be missing or incomplete.

testing:
  - "Unit tests are crucial for validating the complex calculation and filter logic."
  - "Integration testing with the enhanced backtesting engine will be required."

qaResults:
  status: "Pass"
  notes: |
    - The implementation of the LTP Crossover Count Filter is excellent. All requirements are met, and the code is well-tested. The developer has done a thorough job.

devAgentRecord:
  agentModelUsed: "Gemini"
  debugLogReferences:
    - "Resolved `NameError` for `defaultdict` and `deque` by adding missing imports."
    - "Fixed `AttributeError` for `_calculate_implied_crossover_count` method call typo."
    - "Corrected test setup for existing tests to account for new filter, including mocking `_calculate_implied_crossover_count`."
  completionNotes:
    - "The LTP Crossover Count filter is implemented and unit tested."
    - "The strategy now uses multi-timeframe data to calculate implied and average crossover counts."
  fileList:
    - "src/strategies/opening_price_crossover.py"
    - "tests/strategies/test_opening_price_crossover.py"
  changeLog:
    - "Added implied crossover count calculation."
    - "Implemented average implied crossover count history and calculation."
    - "Integrated average crossover count filter into entry logic."
    - "Added unit tests for new filter logic."
---
