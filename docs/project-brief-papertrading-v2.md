# Project Brief: Paper Trading System V2

**Document Date:** 2025-09-10
**Author:** ramakrishna
**Facilitator:** Gemini Code Assist

## 1. Overview & Goals

This document outlines the next generation of enhancements for the TraderBuddy live paper trading system. The core goal is to evolve the paper trading module from a simple strategy simulator into a sophisticated, multi-asset, multi-timeframe research tool that more closely mirrors the complexities of real-world trading.

The key themes are **dynamic configuration**, **realistic position management**, and **enhanced user interface**.

---

## 2. Core Features & Requirements

### Epic 1: Dynamic & Segregated Configuration

The configuration system will be refactored to be more automated, robust, and logically separated.

*   **Segregated Configuration Files:** The single `live_config.yaml` will be replaced by two new files in the project's **root directory**:
    *   `pt_config_stocks.yaml`: This file will be automatically populated at the start of each trading day with the top 10 NIFTY 50 stocks by market capitalization, fetched live from the NSE website.
    *   `pt_config_options.yaml`: This file will be automatically populated at the start of each trading day with the At-The-Money (ATM) Call and Put option symbols for the NIFTY, BANKNIFTY, SENSEX, and BANKEX indices.
*   **Dynamic ATM Calculation:** The system will determine the ATM strike for each index based on the closing price of the previous 1-minute candle or the 09:15 AM candle, whichever is later.
*   **Default Trading Universe:** By default, the paper trading engine will trade all instruments listed in both new configuration files. The user will retain the ability to override this selection from the dashboard.

### Epic 2: Advanced Position & Capital Management

The core logic for managing capital and positions will be made significantly more granular and realistic.

*   **Position Definition:** A "position" will now be uniquely identified by the combination of `Symbol` + `Timeframe`. This is a critical change that allows the system to hold multiple, independent positions in the same underlying instrument on different timeframes.
    *   **Example:** A BUY signal for `RELIANCE` on the `1-min` timeframe will create a position that is managed independently from a separate BUY signal for `RELIANCE` on the `5-min` timeframe. An exit signal on the 1-min chart will only close the 1-min position.
*   **Capital Deployment:**
    *   The initial cash for the paper trading portfolio will be set to **₹50,00,000**.
    *   The "Capital per trade" parameter (e.g., ₹100,000) will be applied to each unique `Symbol` + `Timeframe` combination.
*   **Compounding at Position Level:** The capital available for subsequent trades within the *same* `Symbol` + `Timeframe` combination will be based on the grown or diminished capital *of that specific position*. This simulates a compounding effect at the micro-level.
*   **Strictly Long-Only:** The system will be enhanced to ensure that a "SELL" signal from a strategy is only ever used to exit an existing long position. It will never be used to initiate a new short position for any instrument.

### Epic 3: UI/UX Overhaul

The "Live Paper Trading Monitor" tab will be redesigned for clarity and utility.

*   **Main Menu Icon:** The monitor icon before the "Main Menu" label in the sidebar will be removed.
*   **Removal of Auto-Refreshing Chart:** The "Live Portfolio Performance" chart, which auto-refreshes, will be removed to reduce distraction.
*   **New Positions Table:** The chart will be replaced with a detailed table of all currently open positions. This table will display, at a minimum:
    *   Symbol
    *   Timeframe
    *   Quantity
    *   Average Entry Price
    *   Current Market Price (LTP)
    *   Live Mark-to-Market (MTM) P&L
*   **Live Charts Tab:**
    *   A new primary tab, "Live Charts," will be added to the main dashboard.
    *   This tab will contain sub-tabs for each symbol currently configured for paper trading.
    *   Each sub-tab will display a live, updating OHLC chart for that symbol.
*   **Positional vs. Intraday Toggle:** A new radio button will be added to the sidebar, allowing the user to set the paper trading mode:
    *   **Positional:** Trades are carried overnight until an exit signal is generated.
    *   **Intraday:** All open positions are automatically squared off by the engine at 15:14 IST.

### Epic 4: Documentation Restructuring

*   The single `user_guide.md` will be split into three distinct, focused guides to improve clarity for different user workflows:
    1.  `docs/guides/backtesting_guide.md`
    2.  `docs/guides/papertrading_guide.md`
    3.  `docs/guides/realtrading_guide.md` (as a placeholder for future development)

---

## 3. Analysis & Clarifications

### Live Charts: Feasibility, Performance, and Advisability

*   **Question:** Is it possible to display live OHLC charts for all configured symbols? What is the performance overhead, and is it advisable?
*   **Analysis:**
    *   **Possibility:** Yes, this is entirely possible. The `LiveTradingEngine` already resamples live ticks into 1-minute bars. The dashboard can be configured to read this data from the `live_strategy_data` table and plot it using a library like Plotly.
    *   **Performance Overhead:** The overhead would be moderate. The primary impact would be on the **browser/client-side**, as it would need to render and update multiple charts. The server-side impact would be minimal, as it only involves reading from the database, which is a fast operation. To manage performance, we could make the chart refresh interval configurable (e.g., every 15 or 30 seconds) instead of on every tick.
    *   **Advisability:** This is a highly advisable feature. It provides immediate visual confirmation that the system is receiving and processing data correctly for all symbols. It also transforms the dashboard from a simple monitor into a lightweight, real-time market analysis tool, significantly increasing its value.

---

## 4. High-Level Implementation Sketch

*   **`src/prepare_live_data.py`**: Will be heavily modified to handle the new dual-config file creation and the dynamic fetching of top Nifty stocks.
*   **`src/paper_trading/portfolio.py`**: The `positions` dictionary will need to be restructured to use a composite key like `(symbol, timeframe)` to track positions independently.
*   **`src/strategies/*.py`**: Strategies will need to be updated to pass the `timeframe` context when interacting with the portfolio.
*   **`web_ui/papertrader_ui.py`**: Will be updated to remove the equity curve and add the new positions table and the Intraday/Positional toggle.
*   **`web_ui/dashboard.py`**: Will be updated to include the new "Live Charts" tab.
*   **New UI Module (`web_ui/charts_ui.py`):** A new file will be created to contain the logic for rendering the live charts.