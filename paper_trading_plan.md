# Detailed Plan for a Paper Trading System

Here is a high-level plan that breaks down the development into logical components and phases.

#### **Phase 1: Refactor the Core for Extensibility**

The first step is to slightly modify the existing `tick_collector.py` so it can "publish" ticks to multiple listeners instead of just writing to the database directly.

1.  **Isolate Data Handling:** Create a "tick dispatcher" or "event bus." When `tick_collector.py` receives a tick, instead of immediately writing it to the database, it passes the tick to this dispatcher.
2.  **Create Subscribers:**
    *   The existing database-writing logic will be moved into its own function or class, which "subscribes" to the dispatcher.
    *   The new Paper Trading Engine will be the second subscriber.
3.  **The Flow:**
    `Fyers Socket -> tick_collector -> Tick Dispatcher -> [Database Writer, Paper Trading Engine]`

#### **Phase 2: Design the Paper Trading Engine Components**

This engine is the heart of the simulation. It needs several key parts to manage the "pretend" trading account.

1.  **Portfolio Manager:**
    *   **Purpose:** To track the state of your paper account.
    *   **Responsibilities:**
        *   Manage virtual cash.
        *   Hold current positions (e.g., "long 10 shares of RELIANCE").
        *   Calculate current portfolio value (holdings + cash).
        *   Calculate Profit and Loss (P&L), both realized (from closed trades) and unrealized (from open positions).

2.  **Strategy Executor:**
    *   **Purpose:** To host and run the trading logic.
    *   **Responsibilities:**
        *   Load a specific trading strategy (e.g., a simple Moving Average Crossover).
        *   On every new tick received from the dispatcher, pass the tick to the strategy.
        *   The strategy analyzes the tick and decides if it wants to generate a "signal" (e.g., `BUY`, `SELL`, `HOLD`).

3.  **Order Management System (OMS):**
    *   **Purpose:** To simulate order execution.
    *   **Responsibilities:**
        *   Receive trade signals (BUY/SELL) from the Strategy Executor.
        *   Create "paper" orders (e.g., "BUY 10 RELIANCE @ Market Price").
        *   Simulate order fills. For a simple start, you can assume an order fills instantly at the current tick's price (the Last Traded Price).
        *   When an order is "filled," it notifies the **Portfolio Manager** to update cash and positions.

#### **Phase 3: Define the Strategy Interface**

To make the system flexible, strategies should be plug-and-play. We'll define a standard structure (an interface) that every strategy must follow.

1.  **Base Strategy Class:** Create a Python class `BaseStrategy` that has a method like `on_tick(self, tick_data)`.
2.  **Concrete Strategy:** To start, you'll implement a simple strategy, like `SMACrossoverStrategy`, which inherits from `BaseStrategy`. It will keep a history of recent prices to calculate moving averages and will implement the `on_tick` logic to check for a crossover.
