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

# Auto-generated default configuration files in the project root
STOCKS_CONFIG_FILE = os.path.join(project_root, 'pt_config_stocks.yaml')
PID_FILE = os.path.join(config.DATA_DIR, 'live_engine.pid')

def save_config(config_data):
    """This function is now disabled as configuration is managed by pt_config_stocks.yaml."""
    return False, "Configuration from the dashboard is disabled."

def load_config():
    """
    Loads the live trading configuration directly from the single source of truth:
    pt_config_stocks.yaml.
    """
    if os.path.exists(STOCKS_CONFIG_FILE):
        with open(STOCKS_CONFIG_FILE, 'r') as f:
            try:
                config_data = yaml.safe_load(f) or {}
                return config_data, "Configuration loaded successfully from pt_config_stocks.yaml."
            except Exception as e:
                return None, f"Error loading pt_config_stocks.yaml: {e}"
    else:
        return None, "Configuration file pt_config_stocks.yaml not found."

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
            # The process is now responsible for its own cleanup, including the PID file.
            # We just need to wait until the PID no longer exists.
            if not psutil.pid_exists(pid): 
                return True, f"Engine (PID: {pid}) stopped successfully."
        
        # If the process is still alive after the timeout, it's a hard failure.
        return False, f"Engine (PID: {pid}) did not stop within the 10-second time limit. It may need to be stopped manually."
    except Exception as e:
        # If an error occurs (e.g., PID not found), clean up the stale PID file.
        if os.path.exists(PID_FILE): os.remove(PID_FILE)
        return False, f"Failed to stop engine: {e}"