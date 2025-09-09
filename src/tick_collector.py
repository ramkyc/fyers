import schedule
import time
import subprocess
import datetime
import os
import sys
import signal
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.auth import get_access_token, get_fyers_model
from src.fetch_historical_data import get_top_nifty_stocks, get_atm_option_symbols
from src.market_calendar import is_market_working_day
from src.live_config_manager import load_config

# --- Paper Trading Imports ---
from src.paper_trading.engine import LiveTradingEngine
from src.strategies import STRATEGY_MAPPING

import config # config.py is now in the project root

class TradingScheduler:
    """
    Manages the scheduled execution of the trading engine and related tasks.
    """
    def __init__(self):
        self.paper_trading_engine = None
        self.should_exit = False
        self.pid_file = os.path.join(config.DATA_DIR, 'live_engine.pid')

    def start_trading_engine(self):
        """
        Initializes and starts the LiveTradingEngine.
        """
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Attempting to start Live Trading Engine...")

        if not is_market_working_day(datetime.date.today()):
            print(f"[{current_time}] Not a market day. Skipping.")
            return

        # --- Robustness Check: Ensure live data is prepared ---
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        marker_file = os.path.join(config.DATA_DIR, f"live_data_prepared_for_{today_str}.txt")
        if not os.path.exists(marker_file):
            print(f"[{current_time}] Live strategy data not prepared for today. Running preparation now...")
            self.prepare_live_data()

        try:
            # --- Load Configuration from File ---
            live_config, msg = load_config()
            if not live_config:
                print(f"ERROR: Could not start engine. {msg}")
                return

            print(f"Loaded live configuration: Strategy={live_config['strategy']}, Symbols={len(live_config['symbols'])}")

            raw_access_token = get_access_token()
            fyers_model = get_fyers_model(raw_access_token)
            
            # Dynamically get the strategy class from the mapping
            strategy_class = STRATEGY_MAPPING.get(live_config['strategy'])
            if not strategy_class:
                print(f"ERROR: Strategy '{live_config['strategy']}' not found in STRATEGY_MAPPING.")
                return
            
            strategy = strategy_class(
                symbols=live_config['symbols'],
                portfolio=None, # Portfolio will be set by the engine
                order_manager=None, # OrderManager will be set by the engine
                params=live_config['params']
            )

            # 2. Then, create the engine with the fully initialized strategy
            self.paper_trading_engine = LiveTradingEngine(
                fyers_model=fyers_model,
                app_id=config.APP_ID,
                access_token=raw_access_token,
                strategy=strategy,
                initial_cash=200000.0
            )

            # Start the engine, which will connect to WebSocket internally
            self.paper_trading_engine.start(live_config['symbols'])
            print(f"[{current_time}] Live Trading Engine started.")

        except Exception as e:
            print(f"Error starting the Live Trading Engine: {e}")
            self.paper_trading_engine = None

    def stop_trading_engine(self):
        """
        Stops the LiveTradingEngine and signals the script to exit.
        """
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Attempting to stop the trading engine...")

        if self.paper_trading_engine:
            self.paper_trading_engine.stop()
            self.paper_trading_engine = None

        self.should_exit = True

    def run_archiving_script(self):
        """
        Executes the live data archiving script as a separate process.
        """
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Triggering live tick data archiving...")
        script_path = os.path.join(project_root, 'src', 'archive_live_data.py')
        subprocess.run([sys.executable, script_path])
        print(f"[{current_time}] Archiving script finished.")

    def prepare_live_data(self):
        """
        Executes the live data preparation script as a separate process.
        """
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Triggering live strategy data preparation...")
        script_path = os.path.join(project_root, 'src', 'prepare_live_data.py')
        subprocess.run([sys.executable, script_path])
        print(f"[{current_time}] Live data preparation finished.")

    def run(self):
        """
        The main loop for the scheduler.
        """
        # --- PID File Management ---
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))
        print(f"Scheduler started with PID {os.getpid()}. PID file created at {self.pid_file}")

        print("Starting Trading Engine Scheduler...")
        now = datetime.datetime.now()
        market_open_time = datetime.time(9, 14)
        market_close_time = datetime.time(15, 30)

        if is_market_working_day(now.date()) and now.time() > market_close_time:
            print(f"[{now.strftime('%H:%M:%S')}] Market is already closed. Exiting.")
            return

        schedule.every().day.at("09:10").do(self.prepare_live_data)
        schedule.every().day.at("09:14").do(self.start_trading_engine)
        schedule.every().day.at("15:31").do(self.stop_trading_engine)
        schedule.every().day.at("16:00").do(self.run_archiving_script)

        if is_market_working_day(now.date()) and market_open_time <= now.time() <= market_close_time:
            print(f"[{now.strftime('%H:%M:%S')}] Within market hours. Starting engine now.")
            self.start_trading_engine()

        print("Scheduler running. Waiting for scheduled jobs or exit signal...")
        while not self.should_exit:
            schedule.run_pending()
            time.sleep(5)

# --- Main Execution ---
if __name__ == "__main__":
    scheduler = TradingScheduler()

    def signal_handler(sig, frame):
        print("\nGraceful shutdown signal received. Stopping engine...")
        scheduler.stop_trading_engine()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)

    try:
        scheduler.run()
    except KeyboardInterrupt:
        print("\nScheduler stopped by user. Shutting down engine...")
        scheduler.stop_trading_engine()
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}. Shutting down engine...")
        scheduler.stop_trading_engine()
    finally:
        if os.path.exists(scheduler.pid_file):
            os.remove(scheduler.pid_file)
        print("PID file cleaned up.")
    print("Script finished.")
