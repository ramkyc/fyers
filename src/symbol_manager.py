# src/symbol_manager.py

import sqlite3
import pandas as pd
import os

import config

class SymbolManager:
    """
    A singleton class to manage and provide quick access to symbol master data,
    such as lot sizes.
    """
    _instance = None
    _lot_sizes = {}
    _option_to_underlying = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SymbolManager, cls).__new__(cls)
            cls._instance._load_master_data()
        return cls._instance

    def _load_master_data(self):
        """
        Loads the symbol master data from the database into a dictionary for fast lookups.
        """
        if not os.path.exists(config.HISTORICAL_MARKET_DB_FILE):
            print("WARNING: Symbol master could not be loaded. Historical database not found.")
            return

        try:
            with sqlite3.connect(f'file:{config.HISTORICAL_MARKET_DB_FILE}?mode=ro', uri=True) as con:
                df = pd.read_sql_query("SELECT symbol_ticker, lot_size, underlying_id, instrument_type FROM symbol_master;", con)
                # 1. Load lot sizes
                self._lot_sizes = df.set_index('symbol_ticker')['lot_size'].to_dict()
                
                # 2. Build the option -> underlying mapping
                options_df = df[df['instrument_type'].isin(['FUTIDX', 'FUTSTK', 'OPTIDX', 'OPTSTK'])]
                # Create a mapping from underlying_id to its symbol_ticker
                id_to_ticker = df.set_index('symbol_ticker')['symbol_ticker'].to_dict() # A bit redundant but works
                self._option_to_underlying = options_df.set_index('symbol_ticker')['underlying_id'].map(id_to_ticker).to_dict()
                print(f"SymbolManager loaded {len(self._lot_sizes)} symbols and {len(self._option_to_underlying)} option mappings.")
        except Exception as e:
            print(f"ERROR: Failed to load symbol master data: {e}")

    def get_lot_size(self, symbol: str) -> int:
        """Returns the lot size for a given symbol, defaulting to 1 if not found."""
        return self._lot_sizes.get(symbol, 1)

    def get_underlying_for_option(self, option_symbol: str) -> str:
        """
        Returns the underlying stock/index symbol for a given option symbol.
        Example: get_underlying_for_option('NSE:NIFTY25SEP25000CE') -> 'NSE:NIFTY50-INDEX'
        Returns None if the symbol is not an option or not found.
        """
        return self._option_to_underlying.get(option_symbol)