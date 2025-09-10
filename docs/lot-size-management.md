# Project Brief: Lot Size Management

**Document Date:** 2025-09-10
**Author:** ramakrishna
**Facilitator:** Gemini Code Assist

## 1. Overview & Goals

This document outlines the plan to integrate instrument-specific lot size management into the trading platform. The current system calculates trade quantity based on a fixed monetary value, which is not compatible with Futures & Options (F&O) trading, where order quantities must be a multiple of the instrument's lot size.

The goal is to make the system "lot size aware" to enable valid and realistic trading of F&O instruments.

---

## 2. Core Requirements

### 2.1. Data Component: Symbol Master

*   **New Script (`src/fetch_symbol_master.py`):** A new script will be created to download the official Symbol Master CSV files from Fyers for all relevant segments. This includes equity and F&O for both NSE and BSE (e.g., `NSE_CM`, `NSE_FO`, `BSE_CM`, `BSE_FO`).
*   **New Database Table (`symbol_master`):** The downloaded data, specifically the `symbol` and `lot_size` columns, will be stored in a new table within the `historical_market_data.sqlite` database. This will provide a fast, local lookup for lot sizes.
*   **Scheduling:** The new script should be run periodically (e.g., weekly) to keep the local master data up-to-date with any changes from the exchange.

### 2.2. Strategy & Order Management Enhancements

*   **Position Sizing Logic:** The position sizing logic within the strategies needs to be updated. When calculating the desired quantity, it must round the result down to the nearest valid multiple of the symbol's lot size.
    *   **Example:** If the lot size for NIFTY is 50 and the calculated desired quantity is 120, the actual order quantity should be adjusted to 100 (2 lots).
*   **Order Manager Validation:** The `OrderManager` should perform a final validation check before placing an order. It will look up the symbol's lot size and ensure the order quantity is a valid multiple. If not, it should reject the order and log a clear error message.

### 2.3. UI & Configuration

*   **No Immediate UI Changes:** Initially, no UI changes are required. The system will automatically handle the lot size adjustments in the background.
*   **Future Enhancement:** A future version could display the lot size information on the dashboard for user reference.

---

## 3. Implementation Plan

1.  Create the `fetch_symbol_master.py` script and integrate it into the data setup process.
2.  Modify the `db_setup.py` script to create the new `symbol_master` table.
3.  Update the `_update_position` or quantity calculation logic in the relevant strategies to respect lot sizes.
4.  Enhance the `OrderManager` with the new validation logic.