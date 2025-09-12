# config.py (This file must be in the project root: /Users/ramakrishna/Developer/fyers/)

import os
from dotenv import load_dotenv

# The project root is the directory where this config.py file resides.
# os.path.abspath(__file__) gets the full path to this file.
# os.path.dirname(...) gets the directory containing this file.
project_root = os.path.dirname(os.path.abspath(__file__))

# Construct the full path to the .env file
dotenv_path = os.path.join(project_root, '.env')

# Load the .env file if it exists
if os.path.exists(dotenv_path):
    print(f"INFO: Loading environment variables from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(f"WARNING: .env file not found at {dotenv_path}. Relying on system environment variables.")

# --- Environment Detection ---
# We'll use the presence of an 'ENV' variable to distinguish.
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# --- Fyers API Credentials ---
APP_ID = os.getenv("FYERS_APP_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")
USERNAME = os.getenv("FYERS_USERNAME")
PASSWORD = os.getenv("FYERS_PASSWORD")
PIN = os.getenv("FYERS_PIN")
TOTP_KEY = os.getenv("FYERS_TOTP_KEY")

# --- Database Paths ---
DATA_DIR = os.path.join(project_root, 'data')
HISTORICAL_MARKET_DB_FILE = os.path.join(DATA_DIR, 'historical_market_data.sqlite')
LIVE_MARKET_DB_FILE = os.path.join(DATA_DIR, 'live_market_data.sqlite')
TRADING_DB_FILE = os.path.join(DATA_DIR, 'trading_log.sqlite')

# --- Log Path ---
LOG_PATH = os.path.join(project_root, 'logs')

# --- Master Safety Switch for Live Trading ---
# Set this to True ONLY when you are ready to place real orders.
ENABLE_LIVE_TRADING = False

print(f"--- Configuration loaded for ENVIRONMENT: {ENVIRONMENT} ---")

# --- Data Fetching Configuration ---
DEFAULT_START_DATE_DAILY = "2024-04-01"
DEFAULT_START_DATE_INTRADAY = "2024-04-01"

# --- Default Strategy for Live Paper Trading ---
DEFAULT_LIVE_STRATEGY = "Opening Price Crossover"
