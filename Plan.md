# Plan: Automated Tick Data Collector for Fyers (NIFTY/Others) on Oracle Cloud

## Objectives
- Authenticate with Fyers API using OAuth2 workflow.
- Fetch real-time tick data for:
  - Top 10 NIFTY50 stocks.
  - ATM CE & PE options for NIFTY, BANKNIFTY, SENSEX, and BANKEX indices.
- Store tick data efficiently (CSV or SQLite DB) on the Oracle instance.

## Steps

1. **Fyers API App & OAuth Setup**
   - Register an app in [Fyers API Dashboard](https://myapi.fyers.in) to get App ID, Secret, and set up Redirect URI.
   - Generate daily access token by completing OAuth login.

2. **Environment Setup**
   - Install Python 3.x and required libraries (fyers-apiv3, pandas, schedule, python-dotenv).
   - Securely store API keys and tokens using `.env` files.

3. **Instrument List & Option Logic**
   - Get top 10 NIFTY50 stocks.
   - Fetch underlying index LTP, determine ATM strike, and generate dynamic option symbols for each index.

4. **Data Collector**
   - Connect to Fyers WebSocket for tick data (using official v3 client).
   - Subscribe to required symbols (stocks, ATM calls, ATM puts).
   - Store tick data with timestamps to CSV or database.

5. **Automation & Ongoing Access**
   - Automate token refresh or manual daily login (as needed).
   - Run as a scheduled job during market hours.

6. **Testing & Documentation**
   - Test with small symbol sets before scaling.
   - Document setup, API, token refresh, and fallback workflows.
