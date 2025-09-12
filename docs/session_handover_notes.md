# Session Handover Notes

**Date:** 2025-09-11
**Objective:** Capture the current state of the project after an intensive debugging session on the live paper trading engine, before pivoting to fix the backtesting engine.

---

## 1. Current Status

*   **Live Paper Trading Engine:** The primary focus of the last session. A critical architectural flaw was identified and fixed. The system is now believed to be stable, but requires verification in a live market session.
*   **Backtesting Engine:** Known to be non-functional. This is the next major work item after the live engine is confirmed to be stable.

---

## 2. Key Problem & Resolution

The most significant issue was a cascade of failures originating from a single architectural flaw: **the use of multiple subprocesses during startup.**

### The Problem: Race Conditions & Process Control Failure

1.  **`0 option mappings` Bug:** The main `trading_scheduler.py` was launching `fetch_symbol_master.py` (a slow download) and `prepare_live_data.py` (a fast script) as separate, parallel processes. This created a race condition where `prepare_live_data.py` would try to read the `symbol_master` database table *before* the download process had finished writing to it. This resulted in the `SymbolManager` loading an empty or incomplete table, causing the persistent `0 option mappings` error.

2.  **Unstoppable Process Bug:** When `Ctrl+C` was pressed, the signal was only sent to the main `trading_scheduler.py` process. It did not propagate to the child processes it had launched. The main process would wait indefinitely for its "zombie" children to terminate, causing it to hang and requiring a manual `kill` command.

### The Definitive Solution

The entire startup sequence was re-architected to be **sequential and single-process**.

*   **File Modified:** `src/trading_scheduler.py`
*   **Change:** All `subprocess.run()` calls were removed. The scheduler now directly imports and calls the necessary preparation functions (`fetch_and_store_symbol_masters`, `prepare_live_strategy_data`) in a strict, guaranteed order.

**This single change is expected to fix both the `0 option mappings` bug and the process control failures.**

---

## 3. Plan for Next Session (Tomorrow)

### Step 1: Verify Live Engine Stability

1.  Launch the dashboard: `streamlit run web_ui/dashboard.py`.
2.  Navigate to the "Live Paper Trading Monitor" and click "Start Live Engine".
3.  **CRITICAL VERIFICATION:** Watch the terminal output for the following success indicators:
    *   The `SymbolManager loaded...` message should appear **only once** during the main engine startup.
    *   The message must show a **non-zero number of option mappings** (e.g., `... and 8 option mappings.`).
    *   The "DEBUG FOR OPTION" messages should start appearing in the log every minute.
4.  **FINAL VERIFICATION:** Press `Ctrl+C` in the terminal where the dashboard is running. The `trading_scheduler.py` process should shut down gracefully and exit on its own within a few seconds.

### Step 2: Address Pending UI/UX Feedback

Once the core engine is confirmed to be stable, we will proceed with the user's original list of feedback items:

*   **Item 3:** Fix the screen refresh issue where the page repositions itself.
*   **Item 4:** Clear all existing Live Session logs except the current one.
*   **Item 5:** Ensure the new `run_id` appears immediately in the dropdown.
*   **Item 6:** Add a "Total MTM" column/metric to the positions table.
*   **Item 7:** Investigate and fix the "Performance Summary" showing all zeros.

### Step 3: Begin Backtesting Engine Fixes

After the live trading system is fully stable and all UI feedback has been addressed, we will pivot to fixing the backtesting engine.