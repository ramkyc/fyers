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

LIVE_CONFIG_FILE = os.path.join(config.DATA_DIR, 'live_config.yaml')
PID_FILE = os.path.join(config.DATA_DIR, 'live_engine.pid')

def save_config(config_data):
    """Saves the live trading configuration to a YAML file."""
    try:
        with open(LIVE_CONFIG_FILE, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
        return True, "Configuration saved successfully."
    except Exception as e:
        return False, f"Error saving configuration: {e}"

def load_config():
    """Loads the live trading configuration from the YAML file."""
    if not os.path.exists(LIVE_CONFIG_FILE):
        return None, "Configuration file not found. Please save a configuration from the dashboard."
    try:
        with open(LIVE_CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f), "Configuration loaded successfully."
    except Exception as e:
        return None, f"Error loading configuration: {e}"

def get_engine_status():
    """Checks the status of the live engine."""
    if not os.path.exists(PID_FILE):
        return "Stopped", False
    
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        if psutil.pid_exists(pid):
            process = psutil.Process(pid)
            if 'python' in process.name() and any('tick_collector.py' in part for part in process.cmdline()):
                 return f"Running (PID: {pid})", True
        
        os.remove(PID_FILE)
        return "Stopped (stale PID file found and removed)", False
            
    except (IOError, ValueError, psutil.NoSuchProcess):
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return "Stopped (error checking status)", False

def start_engine():
    """Starts the tick_collector.py script as a background process."""
    status, is_running = get_engine_status()
    if is_running:
        return False, "Engine is already running."

    try:
        script_path = os.path.join(project_root, 'src', 'tick_collector.py')
        command = [sys.executable, script_path]
        process = subprocess.Popen(command, cwd=project_root)
        
        # The dashboard process (which calls this function) is now responsible
        # for creating the PID file immediately.
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))

        return True, f"Engine started successfully with PID: {process.pid}"
    except Exception as e:
        return False, f"Failed to start engine: {e}"

def stop_engine():
    """Stops the running tick_collector.py script gracefully."""
    status, is_running = get_engine_status()
    if not is_running:
        return False, "Engine is not running."

    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        return True, f"Stop signal sent to engine (PID: {pid})."
    except Exception as e:
        return False, f"Failed to stop engine: {e}"