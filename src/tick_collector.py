import schedule
import time
import subprocess
import datetime
import os
import sys # Add the project root to the Python path to allow absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.auth import get_access_token, get_fyers_model
from src.fetch_historical_data import get_top_nifty_stocks, get_atm_option_symbols
from src.market_calendar import is_market_working_day

# --- Paper Trading Imports ---
from src.paper_trading.engine import LiveTradingEngine
from src.strategies.simple_ma_crossover import SMACrossoverStrategy

import config # config.py is now in the project root
# --- Global Variables ---
paper_trading_engine = None # Global instance for the engine
should_exit = False # Flag to signal script termination

# --- Scheduling Functions ---
def start_trading_engine():
    """
    Initializes and starts the LiveTradingEngine.
    """
    global paper_trading_engine
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] Attempting to start Live Trading Engine...")

    if not is_market_working_day(datetime.date.today()):
        print(f"[{current_time}] Not a market day. Skipping.")
        return

    try:
        raw_access_token = get_access_token()
        fyers_model = get_fyers_model(raw_access_token)
        
        # Define symbols and strategy
        tradeable_symbols = get_top_nifty_stocks(top_n=10)
        atm_options = get_atm_option_symbols(fyers_model)
        symbols_to_subscribe = tradeable_symbols + atm_options
        
        # 1. First, create the strategy with its parameters
        strategy_params = {
            'short_window': 9,
            'long_window': 21,
            'trade_quantity': 1
        }
        strategy = SMACrossoverStrategy(
            symbols=tradeable_symbols,
            portfolio=None, # Portfolio will be set by the engine
            order_manager=None, # OrderManager will be set by the engine
            params=strategy_params
        )

        # 2. Then, create the engine with the fully initialized strategy
        paper_trading_engine = LiveTradingEngine(
            fyers_model=fyers_model,
            app_id=config.APP_ID,
            strategy=strategy, # Pass the created strategy instance
            initial_cash=200000.0
        )

        # Start the engine, which will connect to WebSocket internally
        paper_trading_engine.start(raw_access_token, symbols_to_subscribe)
        print(f"[{current_time}] Live Trading Engine started.")

    except Exception as e:
        print(f"Error starting the Live Trading Engine: {e}")
        paper_trading_engine = None

def stop_trading_engine():
    """
    Stops the LiveTradingEngine and signals the script to exit.
    """
    global paper_trading_engine, should_exit
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] Attempting to stop the trading engine...")

    if paper_trading_engine:
        paper_trading_engine.stop()
        paper_trading_engine = None

    should_exit = True

def run_archiving_script():
    """
    Executes the live data archiving script as a separate process.
    """
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] Triggering live tick data archiving...")
    script_path = os.path.join(project_root, 'src', 'archive_live_data.py')
    subprocess.run([sys.executable, script_path])
    print(f"[{current_time}] Archiving script finished.")

# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Trading Engine Scheduler...")

    # --- Schedule Setup ---
    # Note: Times are in the server's local timezone.
    now = datetime.datetime.now()
    market_close_time = datetime.time(15, 30)
    
    # Exit if the market is already closed for the day
    if is_market_working_day(now.date()) and now.time() > market_close_time:
        print(f"[{now.strftime('%H:%M:%S')}] Market is already closed. Exiting.")
        sys.exit(0)

    # --- Schedule Setup ---
    schedule.every().day.at("09:14").do(start_trading_engine)
    schedule.every().day.at("15:31").do(stop_trading_engine)
    schedule.every().day.at("16:00").do(run_archiving_script)

    # --- Initial Start-up ---
    # If script is started during market hours, run collection immediately
    market_open_time = datetime.time(9, 14)
    if is_market_working_day(now.date()) and market_open_time <= now.time() <= market_close_time:
        print(f"[{now.strftime('%H:%M:%S')}] Within market hours. Starting engine now.")
        start_trading_engine()

    # --- Main Loop ---
    print("Scheduler running. Waiting for scheduled jobs or exit signal...")
    try:
        while not should_exit:
            schedule.run_pending()
            # Use a longer, more passive sleep to allow background threads
            # (like the WebSocket) to run without being starved for processing time.
            # The scheduler will still wake up and run jobs at their precise time.
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nScheduler stopped by user. Shutting down engine...")
        stop_trading_engine()
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}. Shutting down engine...")
        stop_trading_engine()
    
    print("Script finished.")
