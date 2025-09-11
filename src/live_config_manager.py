# src/live_config_manager.py

import os
import yaml
import subprocess
import signal
import psutil
import sys
import time

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

# The user's main configuration file
USER_CONFIG_FILE = os.path.join(config.DATA_DIR, 'live_config.yaml')
# Auto-generated default configuration files in the project root
STOCKS_CONFIG_FILE = os.path.join(project_root, 'pt_config_stocks.yaml')
OPTIONS_CONFIG_FILE = os.path.join(project_root, 'pt_config_options.yaml')
PID_FILE = os.path.join(config.DATA_DIR, 'live_engine.pid')

def save_config(config_data):
    """Saves the live trading configuration to a YAML file."""
    try:
        with open(USER_CONFIG_FILE, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
        return True, "Configuration saved successfully."
    except Exception as e:
        return False, f"Error saving configuration: {e}"

def load_config():
    """Loads the live trading configuration from the YAML file."""
    # This function now merges the auto-generated configs with the user's saved config.
    
    # 1. Load user's saved configuration (if it exists)
    user_config = {}
    if os.path.exists(USER_CONFIG_FILE):
        try:
            with open(USER_CONFIG_FILE, 'r') as f:
                user_config = yaml.safe_load(f) or {}
        except Exception as e:
            return None, f"Error loading user configuration: {e}"

    # 2. Load auto-generated stock configuration
    stocks_config = {}
    if os.path.exists(STOCKS_CONFIG_FILE):
        with open(STOCKS_CONFIG_FILE, 'r') as f:
            stocks_config = yaml.safe_load(f) or {}

    # 3. Load auto-generated options configuration
    options_config = {}
    if os.path.exists(OPTIONS_CONFIG_FILE):
        with open(OPTIONS_CONFIG_FILE, 'r') as f:
            options_config = yaml.safe_load(f) or {}

    # 4. Merge them. The user's config takes precedence.
    try:
        # If the user has saved symbols, use them. Otherwise, use the combined default list.
        # This logic now correctly handles the case where `symbols` is explicitly set to `None` in the user config.
        user_symbols = user_config.get('symbols')
        if user_symbols is not None:
            final_symbols = user_symbols
        else:
            final_symbols = stocks_config.get('symbols', []) + options_config.get('symbols', [])
        
        final_config = {**stocks_config, **options_config, **user_config, 'symbols': final_symbols}
        return final_config, "Configuration loaded successfully."
    except Exception as e:
        return None, f"Error merging configurations: {e}"

def get_engine_status():
    """Checks the status of the live engine."""
    try:
        if not os.path.exists(PID_FILE):
            return "Stopped", False, None

        with open(PID_FILE, 'r') as f:
            content = f.read().strip()
            # The file now contains PID,run_id
            pid_str, run_id = content.split(',')
            pid = int(pid_str)
        
        if psutil.pid_exists(pid):
            process = psutil.Process(pid)
            if 'python' in process.name() and any('trading_scheduler.py' in part for part in process.cmdline()):
                 return f"Running (PID: {pid})", True, run_id
        
        os.remove(PID_FILE)
        return "Stopped (stale PID file found and removed)", False, None
            
    except (IOError, ValueError, psutil.NoSuchProcess):
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return "Stopped (error checking status)", False, None

def start_engine():
    """Starts the trading_scheduler.py script as a background process."""
    status, is_running, _ = get_engine_status() # Unpack all 3, ignore the run_id
    if is_running:
        return False, "Engine is already running."

    try:
        script_path = os.path.join(project_root, 'src', 'trading_scheduler.py')
        command = [sys.executable, script_path]
        # CRITICAL FIX: Launch the engine in a new process session.
        # This makes it a daemon process, fully detached from the Streamlit dashboard's process group.
        # It will no longer receive stray signals (like SIGCHLD) meant for the parent, which was causing it to terminate immediately after a restart.
        process = subprocess.Popen(command, cwd=project_root, start_new_session=True)
        
        return True, f"Engine start signal sent (PID: {process.pid})."
    except Exception as e:
        return False, f"Failed to start engine: {e}"

def stop_engine():
    """Stops the running trading_scheduler.py script gracefully."""
    status, is_running, _ = get_engine_status() # Unpack all 3, ignore the run_id
    if not is_running:
        return False, "Engine is not running."

    try:
        with open(PID_FILE, 'r') as f:
            content = f.read().strip()
            pid_str, _ = content.split(',') # Correctly parse "pid,run_id"
            pid = int(pid_str)
        os.kill(pid, signal.SIGTERM)

        # --- Robust Shutdown: Wait for the process to terminate ---
        # Poll for up to 10 seconds for the process to die and the PID file to be removed.
        for _ in range(10):
            time.sleep(1)
            if not psutil.pid_exists(pid):
                # The process is gone, now check if the PID file was cleaned up.
                if not os.path.exists(PID_FILE):
                    return True, f"Engine (PID: {pid}) stopped successfully."
                # If process is gone but PID file remains, it's a stale file. Clean it.
                os.remove(PID_FILE)
                return True, f"Engine (PID: {pid}) stopped. Stale PID file removed."
        return False, f"Engine (PID: {pid}) did not stop within the time limit."
    except Exception as e:
        return False, f"Failed to stop engine: {e}"