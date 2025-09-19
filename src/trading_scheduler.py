import schedule
import time
import subprocess
import datetime
import time # Import the time module
import os
import sys
import signal
import yaml
import psutil
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from auth import get_access_token, get_fyers_model # get_access_token is now the smart function
from market_calendar import is_market_working_day
from fetch_symbol_master import fetch_and_store_symbol_masters # Direct import
from prepare_live_data import prepare_live_strategy_data # Direct import
from db_setup import setup_databases
from live_config_manager import load_config

# --- Paper Trading Imports ---
from paper_trading.pt_engine import PT_Engine
from strategies import STRATEGY_MAPPING

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
        Initializes and starts the PT_Engine.
        """
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Attempting to start Live Paper Trading Engine...")

        # --- Sequential, In-Process Preparation ---
        # All preparation steps are now run directly within this process to
        # eliminate race conditions and process management issues.

        # --- Intelligent Symbol Master Download ---
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        stamp_file_path = os.path.join(config.DATA_DIR, f'symbol_master_{today_str}.stamp')
        if os.path.exists(stamp_file_path):
            print(f"[{current_time}] Step 1: Symbol master is already up-to-date for today. Skipping download.")
        else:
            print(f"[{current_time}] Step 1: Ensuring symbol master is up-to-date...")
            fetch_and_store_symbol_masters()
        
        # This function now handles its own configuration loading internally.
        prepare_live_strategy_data()

        try:
            # --- Step 3: Load the configuration that was just generated ---
            live_config, msg = load_config()
            if not live_config:
                print(f"ERROR: Could not start engine. {msg}")
                return

            paper_trade_type = live_config.get('paper_trade_type', 'Intraday')
            print(f"Loaded live configuration: Strategy={live_config['strategy']}, Symbols={len(live_config['symbols'])}")

            raw_access_token = get_access_token()
            fyers_model = get_fyers_model(raw_access_token)
            
            # Dynamically get the strategy class from the mapping
            strategy_class = STRATEGY_MAPPING.get(live_config['strategy'])
            if not strategy_class:
                print(f"ERROR: Strategy '{live_config['strategy']}' not found in STRATEGY_MAPPING.")
                return

            # --- Multi-Timeframe Strategy Instantiation ---
            # Create a separate, independent strategy instance for each target timeframe.
            # This allows each timeframe to manage its own state and positions.
            # Use the timeframes from the config, or fall back to the hardcoded list for backward compatibility.
            target_timeframes = live_config.get('timeframes', ['1', '5', '15', '30', '60'])

            strategies_to_run = []
            for tf in target_timeframes:
                # --- ARCHITECTURAL FIX: Instantiate the strategy to ask it what it needs ---
                # 1. Create a temporary instance just to get its required resolutions.
                temp_strategy = strategy_class(symbols=[], primary_resolution=tf)
                all_required_resolutions = temp_strategy.get_required_resolutions()

                # 2. Create the real, final instance with all the correct information.
                strategy_instance = strategy_class(
                    symbols=live_config['symbols'],
                    portfolio=None, # Will be set by the engine
                    order_manager=None, # Will be set by the engine
                    params={**live_config.get('params', {}), 'trade_value': 100000},
                    resolutions=all_required_resolutions, # Pass all resolutions
                    primary_resolution=tf # Explicitly set the primary resolution for this instance
                )
                strategies_to_run.append(strategy_instance)

            # 2. Then, create the engine with the fully initialized strategy
            self.paper_trading_engine = PT_Engine(
                fyers_model=fyers_model,
                app_id=config.APP_ID,
                access_token=raw_access_token,
                strategies=strategies_to_run,
                paper_trade_type=paper_trade_type,
                initial_cash=10000000.0 # 1 Crore, to cover 90 slots (18 symbols * 5 TFs) @ 1L each
            )

            # --- PID File Management ---
            # The engine is now responsible for creating the PID file with its run_id.
            with open(self.pid_file, 'w') as f:
                f.write(f"{os.getpid()},{self.paper_trading_engine.run_id}")

            # Start the engine, which will connect to WebSocket internally
            self.paper_trading_engine.start(live_config['symbols'])
            print(f"[{current_time}] Live Paper Trading Engine started.")

        except Exception as e:
            print(f"Error starting the Live Paper Trading Engine: {e}")
            self.paper_trading_engine = None

    def stop_trading_engine(self):
        """
        Stops the PT_Engine and signals the script to exit.
        """
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Attempting to stop the trading engine...")

        if self.paper_trading_engine:
            self.paper_trading_engine.stop()
            self.paper_trading_engine = None

        # --- ARCHITECTURAL FIX: Ensure immediate and graceful shutdown ---
        # Instead of just setting a flag and waiting for the loop to check it,
        # we send a SIGTERM signal to our own process. This is caught by the
        # signal_handler, which guarantees a clean exit and PID file removal.
        print(f"[{current_time}] Sending SIGTERM to self (PID: {os.getpid()}) to trigger graceful shutdown.")
        os.kill(os.getpid(), signal.SIGTERM)

    def run(self):
        """
        The main loop for the scheduler.
        """

        # --- Singleton Check: Ensure only one instance is running ---
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f:
                    content = f.read().strip()
                    pid_str, run_id = content.split(',')
                    pid = int(pid_str)
                
                if psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    # Check if the running process is another instance of this script
                    if 'trading_scheduler.py' in ' '.join(process.cmdline()):
                        print(f"ERROR: Another instance of TradingScheduler is already running with PID {pid} (Run ID: {run_id}). Exiting.")
                        return # Exit the new instance

                # If we reach here, the PID does not exist or is not our script, so the PID file is stale.
                print("Stale PID file found. Removing it.")
                os.remove(self.pid_file)

            except (IOError, ValueError, psutil.NoSuchProcess) as e:
                print(f"Error checking existing PID file: {e}. Removing it and proceeding.")
                os.remove(self.pid_file)

        # --- Self-Healing: Ensure DB schema is up-to-date on startup ---
        setup_databases()

        print("Starting Trading Engine Scheduler...")
        now = datetime.datetime.now()
        market_open_time = datetime.time(9, 14)
        market_close_time = datetime.time(15, 30)

        # The daily setup now runs inside start_trading_engine to ensure sequence.
        # We only schedule the start and stop of the engine itself.
        schedule.every().day.at("09:14").do(self.start_trading_engine)
        schedule.every().day.at("15:31").do(self.stop_trading_engine)
        
        # Archiving is also now a direct function call.
        def run_archiving():
            from src.archive_live_data import archive_live_ticks
            archive_live_ticks()
        schedule.every().day.at("16:00").do(run_archiving)

        if is_market_working_day(now.date()) and market_open_time <= now.time() <= market_close_time:
            print(f"[{now.strftime('%H:%M:%S')}] Within market hours. Starting engine now.")
            self.start_trading_engine()

        print("Scheduler running. Waiting for scheduled jobs or exit signal...")
        while not self.should_exit:
            # Non-blocking check for scheduled jobs
            schedule.run_pending()
            # Sleep for a short duration to prevent a busy-wait loop.
            # This is CRITICAL for allowing the process to receive and handle
            # signals like SIGINT (Ctrl+C) or SIGTERM from the stop_engine function.
            time.sleep(1)

# --- Main Execution ---
if __name__ == "__main__":
    scheduler = TradingScheduler()

    def signal_handler(sig, frame):
        print(f"\nGraceful shutdown signal received ({signal.Signals(sig).name}). Stopping engine...")
        # --- DEFINITIVE FIX for Shutdown ---
        # The signal handler must be the single point of control for shutdown.
        # It performs the cleanup and then immediately exits the process.
        # This prevents the main loop's `time.sleep()` from interfering with a timely exit.
        scheduler.stop_trading_engine()
        sys.exit(0) # Exit gracefully

    signal.signal(signal.SIGINT, signal_handler) # Handle Ctrl+C
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
        # Ensure the engine is stopped on any exit, but only if it's still running.
        if scheduler.paper_trading_engine is not None:
            scheduler.stop_trading_engine()
        if os.path.exists(scheduler.pid_file):
            os.remove(scheduler.pid_file)
        print("PID file cleaned up.")
    print("Script finished.")