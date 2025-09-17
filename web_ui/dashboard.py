import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
sys.dont_write_bytecode = True # Prevent __pycache__ creation

import streamlit as st
import datetime
from streamlit_option_menu import option_menu

# Import the new page modules
from web_ui import backtesting_ui, papertrader_ui

@st.cache_resource # Use cache_resource for singleton-like objects that should persist
def initialize_symbol_manager():
    """
    Initializes the SymbolManager once per session and caches the instance.
    This prevents it from being reloaded on every UI refresh.
    """
    try:
        from src.symbol_manager import SymbolManager
        sm = SymbolManager()
        sm.reload_master_data() # This is now safe to call as it's inside a cached function
        print("SymbolManager initialized once at dashboard startup.")
    except Exception as e:
        print(f"[Startup] Failed to initialize SymbolManager: {e}")

def main():
    """Main function to run the Streamlit dashboard."""
    st.set_page_config(layout="wide")
    st.title("TraderBuddy Dashboard")

    with st.sidebar:
        app_mode = option_menu(
            menu_title="Main Menu",
            options=["Backtesting", "Live Paper Trading Monitor"],
            icons=['graph-up-arrow', 'broadcast-pin'],
            default_index=0,
        )

    # --- Initialize shared resources once ---
    initialize_symbol_manager()

    if app_mode == "Backtesting":
        backtesting_ui.render_page()
    elif app_mode == "Live Paper Trading Monitor":
        papertrader_ui.render_page()

if __name__ == "__main__":
    main()
