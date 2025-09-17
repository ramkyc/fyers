# src/symbol_manager.py

import threading
import sqlite3
import pandas as pd
import datetime
import time
import os

import config

class SymbolManager:
    """
    A singleton class to manage and provide quick access to symbol master data,
    such as lot sizes.
    """
    # --- Singleton and Thread-Safety Implementation ---
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                # Another thread could have created the instance
                # while the first thread was waiting for the lock.
                if not cls._instance:
                    cls._instance = super(SymbolManager, cls).__new__(cls)
                    # --- Initialization is now handled by _initialize() ---
                    # Set a flag to indicate data has not been loaded yet.
                    cls._instance._initialized = False
        return cls._instance

    def _initialize(self):
        """
        Loads the symbol master data from the database into a dictionary for fast lookups.
        This is now the private initialization method.
        """
        if not os.path.exists(config.HISTORICAL_MARKET_DB_FILE):
            print("WARNING: Symbol master could not be loaded. Historical database not found.")
            return

        # --- Self-Healing Retry Logic ---
        # This loop handles the race condition where this method is called immediately after
        # the database file is created, but before the OS has flushed all writes to disk.
        for attempt in range(5): # Retry up to 5 times for more robustness
            df = pd.DataFrame() # Initialize an empty DataFrame
            try:
                with sqlite3.connect(f'file:{config.HISTORICAL_MARKET_DB_FILE}?mode=ro', uri=True) as con:
                    df = pd.read_sql_query("SELECT fy_token, symbol_ticker, lot_size, underlying_id, instrument_type FROM symbol_master;", con)
            except Exception as e:
                print(f"ERROR: Failed to load symbol master data on attempt {attempt + 1}: {e}")
                time.sleep(0.5) # Shorter sleep between retries
                continue # Retry on database connection/read error

            # --- Sanity Check (now outside the 'try' but inside the 'for' loop) ---
            # If we read a suspiciously low number of symbols, the file is likely not fully written.
            if len(df) < 50000: # A high threshold to ensure we get the full master list
                print(f"WARNING: SymbolManager read only {len(df)} symbols (Attempt {attempt + 1}). Retrying in 1 second...")
                time.sleep(1)
                continue # Go to the next attempt

            # --- Data Processing (only if sanity check passes) ---
            else: # If the sanity check passes, process the data and exit the loop
                df['fy_token'] = df['fy_token'].astype(str)
                numeric_underlying = pd.to_numeric(df['underlying_id'], errors='coerce')
                df['underlying_id'] = numeric_underlying.round().astype('Int64').astype(str).replace('<NA>', '')

                self._lot_sizes = df.set_index('symbol_ticker')['lot_size'].to_dict()
                self._all_symbols_df = df # Store the full DataFrame
                self._option_to_underlying = {}
                
                print(f"SymbolManager loaded {len(self._lot_sizes)} symbols. (Option trading disabled)")
                self._initialized = True
                return # Success, exit the loop and the method

        # If all retries fail
        print("CRITICAL: SymbolManager failed to load a complete symbol list after multiple attempts.")
        self._initialized = False
        # Initialize with empty dicts to prevent downstream errors
        self._lot_sizes = {}
        self._all_symbols_df = pd.DataFrame()
        self._option_to_underlying = {}


    def reload_master_data(self):
        """
        Explicitly re-loads the master data from the database.
        This is crucial for scenarios where the database is populated after the
        singleton has already been initialized.
        """
        self._initialize() # This call is now correct

    def get_lot_size(self, symbol: str) -> int:
        """
        Returns the lot size for a given symbol, defaulting to 1 if not found.
        This method will trigger data loading on its first call if not already loaded.
        """
        if not getattr(self, '_initialized', False):
            # This should not happen in the live engine flow. It indicates a logic error.
            # By preventing auto-initialization, we enforce a strict startup sequence.
            print("CRITICAL WARNING: get_lot_size called on an uninitialized SymbolManager!")
            return 1 # Return a safe default
        return self._lot_sizes.get(symbol, 1)

    def get_all_symbols(self, include_indices: bool = True, include_options: bool = False) -> list[str]:
        """
        Returns a sorted list of all available symbol tickers based on the loaded master data.

        Args:
            include_indices (bool): Whether to include index symbols (e.g., 'NSE:NIFTY50-INDEX').
            include_options (bool): Whether to include option symbols.

        Returns:
            list[str]: A sorted list of symbol tickers.
        """
        if not getattr(self, '_initialized', False) or self._all_symbols_df.empty:
            print("CRITICAL WARNING: get_all_symbols called on an uninitialized or empty SymbolManager!")
            return []

        df = self._all_symbols_df.copy()

        # Filter out indices if not requested
        if not include_indices:
            df = df[~df['symbol_ticker'].str.contains("-INDEX")]

        # Filter out options if not requested
        if not include_options:
            df = df[df['instrument_type'] != 7] # Instrument type 7 is for options

        return sorted(df['symbol_ticker'].unique().tolist())