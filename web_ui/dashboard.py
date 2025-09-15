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

def main():
    """Main function to run the Streamlit dashboard."""

    # --- Ensure SymbolManager is initialized at startup ---
    try:
        from src.symbol_manager import SymbolManager
        SymbolManager().reload_master_data()
        print("SymbolManager initialized at dashboard startup.")
    except Exception as e:
        print(f"[Startup] Failed to initialize SymbolManager: {e}")

    st.set_page_config(layout="wide")
    st.title("TraderBuddy Dashboard")

    with st.sidebar:
        app_mode = option_menu(
            menu_title="Main Menu",
            options=["Backtesting", "Live Paper Trading Monitor"],
            icons=['graph-up-arrow', 'broadcast-pin'],
            default_index=0,
        )

    if app_mode == "Backtesting":
        backtesting_ui.render_page()
    elif app_mode == "Live Paper Trading Monitor":
        papertrader_ui.render_page()

if __name__ == "__main__":
    main()
