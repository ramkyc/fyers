# Detailed Task List

Here is that plan broken down into a concrete, actionable task list.

**✅ Task: Implement Paper Trading Module**

*   **Sub-task 1: Refactor `tick_collector.py`**
    *   [ ] Create a new file `src/event_dispatcher.py` that will manage a list of subscriber functions.
    *   [ ] Modify `tick_collector.py` to import the dispatcher. When a tick is received, call `dispatcher.dispatch(tick)`.
    *   [ ] Move the DuckDB writing logic into a new function/class `DatabaseSubscriber` in a new file `src/database_subscriber.py`.
    *   [ ] Register `DatabaseSubscriber` with the `event_dispatcher`.

*   **Sub-task 2: Create the Portfolio Manager**
    *   [ ] Create `src/paper_trading/portfolio.py`.
    *   [ ] Implement a `Portfolio` class with attributes for `initial_cash`, `current_cash`, and `positions` (a dictionary).
    *   [ ] Add methods: `update_position(symbol, quantity, price)`, `update_cash(amount)`, and `calculate_pnl()`.

*   **Sub-task 3: Create the Order Management System (OMS)**
    *   [ ] Create `src/paper_trading/oms.py`.
    *   [ ] Implement an `OrderManager` class.
    *   [ ] Add a method `execute_order(signal)` that takes a buy/sell signal.
    *   [ ] In `execute_order`, on receiving a signal, it should immediately "fill" the order at the tick's price and call the appropriate methods on the `Portfolio` instance to update the account state.

*   **Sub-task 4: Define and Implement a Strategy**
    *   [ ] Create `src/strategies/base_strategy.py` with an abstract `BaseStrategy` class defining an `on_tick(self, tick)` method.
    *   [ ] Create `src/strategies/simple_ma_crossover.py`.
    *   [ ] Implement the `SMACrossover` class, inheriting from `BaseStrategy`. It will need to maintain a small history of prices to calculate two moving averages.
    *   [ ] The `on_tick` method will check if the short-term MA crosses above/below the long-term MA and return a `BUY` or `SELL` signal.

*   **Sub-task 5: Build the Main Paper Trading Engine**
    *   [ ] Create `src/paper_trading/engine.py`.
    *   [ ] Implement the `PaperTradingEngine` class.
    *   [ ] The engine's `__init__` will initialize the `Portfolio`, `OrderManager`, and load a specific `Strategy`.
    *   [ ] It will have an `on_tick(self, tick)` method that it will register as a subscriber with the `event_dispatcher`.
    *   [ ] When the engine's `on_tick` is called, it passes the tick to the strategy, gets a signal back, and if there's a signal, passes it to the `OrderManager`.

*   **Sub-task 6: Logging and Reporting**
    *   [ ] The `OrderManager` should log every executed trade (symbol, price, quantity, time) to a new file or a new database table (`trades.log` or `paper_trades` table).
    *   [ ] The `Portfolio` should log the portfolio value periodically (e.g., every 100 ticks) to track performance over time.
