---
story:
  title: "feat: Implement LTP Crossover Count Filter"
  epic: "Backtesting Strategy Framework"
  status: "Ready for Development"
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
      - "[ ] Update `on_data` to accept and utilize the multi-timeframe data provided by the enhanced engine."
  - task: "Task 2: Implement Implied Crossover Count Calculation"
    subtasks:
      - "[ ] Develop logic to calculate the 'implied crossover count' for the current higher-timeframe candle using lower-timeframe data."
  - task: "Task 3: Implement Average Crossover Count Calculation"
    subtasks:
      - "[ ] Develop logic to calculate the 'average implied crossover count' over the last 10 higher-timeframe candles."
  - task: "Task 4: Integrate Filter into Entry Logic"
    subtasks:
      - "[ ] Integrate the 'average crossover count' filter into the entry conditions of the `OpeningPriceCrossoverStrategy`."
  - task: "Task 5: Write Unit Tests for New Filter"
    subtasks:
      - "[ ] Create new unit tests to verify the 'implied crossover count' calculation."
      - "[ ] Create new unit tests to verify the 'average crossover count' filter logic, including edge cases."

devNotes: |
  - This story is dependent on the completion of 'feat-enhance-backtesting-engine-multi-timeframe.md'.
  - The implementation should be robust to handle cases where lower-timeframe data might be missing or incomplete.

testing:
  - "Unit tests are crucial for validating the complex calculation and filter logic."
  - "Integration testing with the enhanced backtesting engine will be required."

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
