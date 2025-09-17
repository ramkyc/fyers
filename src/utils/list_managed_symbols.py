# scripts/list_managed_symbols.py

import os
import sys

# Add project root to path to allow importing project modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.symbol_manager import SymbolManager

def list_symbols():
    """
    Initializes the SymbolManager and prints the list of symbols it manages.
    """
    print("--- Initializing SymbolManager to list managed symbols ---")
    
    # 1. Create an instance of the singleton
    sm = SymbolManager()
    
    # 2. Explicitly load/reload the data from the database
    sm.reload_master_data()
    
    # 3. Access the internal dictionary and print the symbols
    managed_symbols = sorted(list(sm._lot_sizes.keys()))
    
    print(f"\nSymbolManager is managing a total of {len(managed_symbols)} symbols:")
    print("-" * 50)
    for symbol in managed_symbols:
        print(symbol)
    print("-" * 50)

if __name__ == "__main__":
    list_symbols()