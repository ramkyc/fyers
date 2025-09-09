import sys
# Add the project root to the Python path to allow absolute imports
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
sys.dont_write_bytecode = True # Prevent __pycache__ creation

import os
import streamlit as st
import pandas as pd
import datetime
import sqlite3
import plotly.graph_objects as go
import plotly.express as px
import concurrent.futures
import time
from streamlit_option_menu import option_menu
from streamlit_autorefresh import st_autorefresh

from src.paper_trading.portfolio import Portfolio
from src.reporting.performance_analyzer import PerformanceAnalyzer
from src.backtesting.engine import BacktestingEngine
import config # config.py is now in the project root
from src.market_calendar import is_market_working_day, NSE_MARKET_OPEN_TIME, NSE_MARKET_CLOSE_TIME
from src.live_config_manager import save_config, load_config, get_engine_status, start_engine, stop_engine
from src.strategies import STRATEGY_MAPPING # Import from the new central location

# --- Configuration ---
HISTORICAL_TABLE = "historical_data"

# --- Helper Functions ---
@st.cache_resource
def get_db_connection(db_file):
    """Establishes and returns a SQLite connection."""
    return sqlite3.connect(f'file:{db_file}?mode=ro', uri=True)

@st.cache_data(ttl=3600) # Cache for 1 hour
def get_market_time_options(interval_minutes=15):
    """Generates a list of time options within market hours."""
    times = []
    start = datetime.datetime.strptime("09:15", "%H:%M")
    end = datetime.datetime.strptime("15:30", "%H:%M")
    while start <= end:
        times.append(start.time())
        start += datetime.timedelta(minutes=interval_minutes)
    return times

@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_historical_data(symbols, resolution, start_date, end_date):
    """
    Loads historical data from the database for display purposes.
    """
    # This function specifically reads from the market data DB
    if not os.path.exists(config.HISTORICAL_MARKET_DB_FILE):
        st.warning(f"Market data file not found at {config.HISTORICAL_MARKET_DB_FILE}")
        return pd.DataFrame()
        
    with sqlite3.connect(f'file:{config.HISTORICAL_MARKET_DB_FILE}?mode=ro', uri=True) as con:
        symbols_tuple = tuple(symbols)
        query = f"""
            SELECT timestamp, symbol, close
            FROM {HISTORICAL_TABLE}
            WHERE symbol IN ({','.join(['?']*len(symbols_tuple))})
            AND resolution = '{resolution}'
            AND timestamp BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY timestamp ASC;
            """
        df = pd.read_sql_query(query, con, params=symbols_tuple)
    return df

@st.cache_data(ttl=60) # Cache for 1 minute
def load_log_data(query, params=()):
    """Loads log data from the database."""
    # This function specifically reads from the trading log DB
    if not os.path.exists(config.TRADING_DB_FILE):
        # It's not an error if this file doesn't exist yet
        return pd.DataFrame()

    try:
        con = sqlite3.connect(f'file:{config.TRADING_DB_FILE}?mode=ro', uri=True)
        df = pd.read_sql_query(query, con, params=params)
        return df
    except (sqlite3.OperationalError, pd.io.sql.DatabaseError) as e:
        # This can happen if the table doesn't exist yet (e.g., no live trades made)
        st.info("Could not load log data. The database table may not exist yet. Please run a live trade to generate logs.")
        return pd.DataFrame()

@st.cache_data(ttl=600) # Cache for 10 minutes
def get_all_symbols():
    """Fetches all unique symbols from the historical data table."""
    if not os.path.exists(config.HISTORICAL_MARKET_DB_FILE):
        st.warning(f"Historical market data file not found at {config.HISTORICAL_MARKET_DB_FILE}. Please run `python src/fetch_historical_data.py` to generate it.")
        return []
    con = get_db_connection(config.HISTORICAL_MARKET_DB_FILE)
    query = "SELECT DISTINCT symbol FROM historical_data ORDER BY symbol;"
    df = pd.read_sql_query(query, con)
    return df['symbol'].tolist() if not df.empty else []

@st.cache_data(ttl=60)
def get_all_run_ids():
    """Fetches all unique run_ids from the trading log database."""
    if not os.path.exists(config.TRADING_DB_FILE):
        return []
    query = "SELECT DISTINCT run_id FROM paper_trades WHERE run_id IS NOT NULL ORDER BY timestamp DESC;"
    df = load_log_data(query)
    live_runs = [r for r in df['run_id'].tolist() if r.startswith('live_')]
    backtest_runs = [r for r in df['run_id'].tolist() if not r.startswith('live_')]
    return live_runs + backtest_runs # Prioritize live runs

@st.cache_data(ttl=10) # Cache for 10 seconds
def load_live_portfolio_log(run_id: str):
    """
    Loads the portfolio log for a specific live run ID.
    """
    if not run_id:
        return pd.DataFrame()
    
    query = """
        SELECT timestamp, value FROM portfolio_log
        WHERE run_id = ? ORDER BY timestamp ASC;
    """
    df = load_log_data(query, params=(run_id,))
    return df

@st.cache_data(ttl=10) # Cache for 10 seconds for live data
def load_live_ticks():
    """Loads the last few ticks from the live market data database."""
    if not os.path.exists(config.LIVE_MARKET_DB_FILE):
        return pd.DataFrame()
    try:
        with sqlite3.connect(f'file:{config.LIVE_MARKET_DB_FILE}?mode=ro', uri=True) as con:
            query = "SELECT * FROM live_ticks ORDER BY timestamp DESC LIMIT 10;"
            df = pd.read_sql_query(query, con)
            return df
    except Exception as e:
        # Table might not exist if engine hasn't run yet
        st.info(f"Could not load live tick data. The table might not exist yet. Error: {e}")
        return pd.DataFrame()

# This function must be defined at the top level to be pickleable by multiprocessing
def run_backtest_for_worker(args):
    """
    A self-contained function to run a single backtest.
    Designed to be executed in a separate process to enable parallelization.
    """
    start_date_str, end_date_str, db_file, resolution, symbols, params, initial_cash, strategy_name, backtest_type = args

    # These imports are necessary inside the worker process
    from src.backtesting.engine import BacktestingEngine
    from src.reporting.performance_analyzer import PerformanceAnalyzer
    strategy_class = STRATEGY_MAPPING[strategy_name]
    start_datetime = datetime.datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")

    engine = BacktestingEngine(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        db_file=db_file,
        resolution=resolution
    )
    
    portfolio_result, last_prices, _ = run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash, backtest_type)
    
    if portfolio_result and last_prices:
        analyzer = PerformanceAnalyzer(portfolio_result)
        metrics = analyzer.calculate_metrics(last_prices)
        metrics.update(params) # Add all params to the result for later joining
        return metrics
    return None

def run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash, backtest_type):
    """Runs a backtest and captures its stdout log."""
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    with redirect_stdout(f):
        portfolio_result, last_prices, run_id = engine.run(
            strategy_class=strategy_class,
            symbols=symbols,
            params=params,
            initial_cash=initial_cash,
            backtest_type=backtest_type
        )
    backtest_log = f.getvalue()
    return portfolio_result, last_prices, backtest_log

def display_optimization_results(results_df):
    """Renders the UI for displaying optimization results."""
    st.subheader("Optimization Results")

    # --- Visualization Section ---
    vis_metric = st.selectbox(
        "Select metric to visualize:",
        options=['Total P&L', 'Sharpe Ratio', 'Max Drawdown', 'Profit Factor']
    )

    # Identify parameter columns for visualization, excluding non-numeric ones
    param_cols = [col for col in results_df.columns if col not in ['Total P&L', 'Sharpe Ratio', 'Max Drawdown', 'Win Rate', 'Profit Factor', 'initial_cash', 'trade_quantity']]
    
    tab1, tab2, tab3 = st.tabs(["Summary Table", "2D Heatmap", "3D Surface Plot"])

    with tab1:
        st.dataframe(results_df.style.format({
            'Total P&L': "₹{:,.2f}",
            'Sharpe Ratio': "{:.2f}",
            'Max Drawdown': "{:.2f}%",
            'Win Rate': "{:.2%}",
            'Profit Factor': "{:.2f}"
        }).background_gradient(cmap='viridis', subset=['Total P&L', 'Sharpe Ratio']))

    # Pivot data for visualization
    try:
        pivot_df = results_df.pivot(
            index=param_cols[0],
            columns=param_cols[1],
            values=vis_metric
        )

        with tab2:
            st.subheader(f"{vis_metric} 2D Heatmap")
            fig_heatmap = go.Figure(data=go.Contour(
                z=pivot_df.values,
                x=pivot_df.columns,
                y=pivot_df.index,
                colorscale='viridis',
                contours=dict(coloring='heatmap', showlabels=True, labelfont=dict(size=10, color='white')),
                colorbar=dict(title=vis_metric, titleside='right')
            ))
            fig_heatmap.update_layout(title=f'Strategy Performance Landscape ({vis_metric})',
                                      xaxis_title=param_cols[1], yaxis_title=param_cols[0])
            st.plotly_chart(fig_heatmap, use_container_width=True)

        with tab3:
            st.subheader(f"{vis_metric} 3D Surface Plot")
            fig_3d = go.Figure(data=[go.Surface(z=pivot_df.values, x=pivot_df.columns, y=pivot_df.index)])
            fig_3d.update_layout(title=f'Strategy Performance Landscape ({vis_metric})',
                                 scene=dict(xaxis_title=param_cols[1], 
                                            yaxis_title=param_cols[0], 
                                            zaxis_title=vis_metric))
            st.plotly_chart(fig_3d, use_container_width=True)
    except Exception as e:
        st.error(f"Could not generate visualizations. This can happen if there are not enough data points for a grid. Error: {e}")

def display_single_backtest_results(portfolio_result, last_prices, backtest_log):
    """Renders the UI for displaying single backtest results."""
    st.subheader("Performance Summary")
    analyzer = PerformanceAnalyzer(portfolio_result)
    metrics = analyzer.calculate_metrics(last_prices)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(
        "Total P&L", 
        f"₹{metrics['total_pnl']:,.2f}", 
        f"{metrics['total_pnl'] / (metrics['initial_cash'] or 1):.2%}",
        help="Total Profit and Loss. The percentage shows the return on the initial cash."
    )
    col2.metric(
        "Max Drawdown", 
        f"{metrics['max_drawdown'] * 100:.2f}%",
        help="The largest peak-to-trough decline in portfolio value. A lower value is better."
    )
    col3.metric(
        "Sharpe Ratio", 
        f"{metrics['sharpe_ratio']:.2f}",
        help="Measures risk-adjusted return. A higher value indicates better performance for the amount of risk taken. Calculated using a 6% annual risk-free rate for Indian markets."
    )
    col4.metric(
        "Win Rate", f"{metrics['win_rate']:.2%}",
        help="The percentage of trades that were profitable."
    )
    col5.metric(
        "Profit Factor", f"{metrics['profit_factor']:.2f}",
        help="The ratio of gross profits to gross losses. A value greater than 1 indicates a profitable system."
    )

    st.subheader("Equity Curve")
    if portfolio_result.equity_curve:
        equity_df = pd.DataFrame(portfolio_result.equity_curve)
        st.line_chart(equity_df.set_index('timestamp'))
    else:
        st.info("No equity curve data was generated during the backtest.")

    tab1, tab2 = st.tabs(["Trade Log", "Raw Backtest Log"])
    with tab1:
        st.dataframe(pd.DataFrame(portfolio_result.trades))
    with tab2:
        st.code(backtest_log)

def render_backtesting_ui(symbols_to_test, backtest_type, resolution, start_datetime, end_datetime, selected_strategy_name, run_optimization, strategy_params, optimization_params, trade_quantity, initial_cash):
    """Renders the main panel UI for the backtesting dashboard."""
    strategy_class = STRATEGY_MAPPING[selected_strategy_name]
    
    # --- Main Content Area ---
    if run_optimization:
        st.header("Parameter Optimization")
    else:
        st.header("Backtest Results")

    if st.session_state.get('run_button_clicked', False):
        if not symbols_to_test:
            st.warning("Please select at least one symbol to run the backtest.")
        else:
            with st.spinner(f"Running backtest for {len(symbols_to_test)} symbols..."):
                start_date_str = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
                end_date_str = end_datetime.strftime("%Y-%m-%d %H:%M:%S")

                if run_optimization:
                    param_combinations = []
                    param_combinations = strategy_class._generate_param_combinations(optimization_params)
                    if not param_combinations:
                        st.warning("No valid parameter combinations found. Ensure short window is smaller than long window.")
                    else:
                        for p in param_combinations:
                            p['trade_quantity'] = trade_quantity
                        worker_args = [(start_date_str, end_date_str, config.HISTORICAL_MARKET_DB_FILE, resolution, symbols_to_test, params, initial_cash, selected_strategy_name, backtest_type) for params in param_combinations]
                        results = [] # This was already here, but for clarity in the diff
                        progress_text = st.empty()
                        progress_bar = st.progress(0)

                        with concurrent.futures.ProcessPoolExecutor() as executor:
                            map_results = executor.map(run_backtest_for_worker, worker_args)
                            for i, result in enumerate(map_results):
                                if result:
                                    results.append(result)
                                progress_text.text(f"Completed {i + 1} of {len(param_combinations)} backtests...")
                                progress_bar.progress((i + 1) / len(param_combinations))

                        if results:
                            results_df = pd.DataFrame(results)
                            display_optimization_results(results_df)
                        else:
                            st.error("Optimization run completed, but no results were generated.")

                else: # Run a single backtest
                    strategy_params['trade_quantity'] = trade_quantity
                    
                    # Ensure that for any intraday resolution, we also load daily data
                    # which is required for strategies like OpeningPriceCrossover.
                    other_resolutions = set()
                    if resolution != "D":
                        other_resolutions.add("D")

                    # The OpeningPriceCrossoverStrategy specifically requires 1-minute data
                    # for its implied crossover count calculation.
                    if selected_strategy_name == "Opening Price Crossover":
                        other_resolutions.add("1")

                    # Construct the final list, ensuring the user-selected resolution is first.
                    final_resolutions = [resolution] + list(other_resolutions)

                    engine = BacktestingEngine(
                        start_datetime=start_datetime, 
                        end_datetime=end_datetime, 
                        db_file=config.HISTORICAL_MARKET_DB_FILE, 
                        resolutions=final_resolutions
                    )
                    
                    portfolio_result, last_prices, backtest_log = run_and_capture_backtest(
                        engine, strategy_class, symbols_to_test, strategy_params, initial_cash, backtest_type
                    )

                    if portfolio_result:
                        display_single_backtest_results(portfolio_result, last_prices, backtest_log)
                    else:
                        st.error("Backtest did not return any results.")
                        st.subheader("Backtest Log")
                        st.code(backtest_log)

def render_live_monitor_ui():
    """Renders the UI for monitoring live paper trading sessions."""
    st.header("Live Paper Trading Monitor")
    st.markdown("Configure, start, stop, and monitor the live paper trading engine.")

    # --- Engine Status & Control ---
    # These controls should NOT be part of the auto-refreshing block.
    st.subheader("Engine Control")
    
    # We use session state to track if the engine is running to avoid re-checking on every interaction.
    if 'is_engine_running' not in st.session_state:
        _, st.session_state.is_engine_running = get_engine_status()

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Start Live Engine", disabled=st.session_state.is_engine_running, use_container_width=True):
            with st.spinner("Attempting to start the live engine..."):
                success, message = start_engine()
                if success:
                    st.success(message)
                    st.session_state.is_engine_running = True
                else:
                    st.error(message)
                time.sleep(1)
                st.rerun()

    with col2:
        if st.button("Stop Live Engine", disabled=not st.session_state.is_engine_running, use_container_width=True):
            with st.spinner("Sending stop signal to the live engine..."):
                success, message = stop_engine()
                if success:
                    st.success(message)
                    st.session_state.is_engine_running = False
                else:
                    st.error(message)
                time.sleep(1)
                st.rerun()

    with col3:
        if st.button("Stop and Restart", disabled=not st.session_state.is_engine_running, use_container_width=True, type="primary"):
            with st.spinner("Restarting the live engine..."):
                stop_success, _ = stop_engine()
                if stop_success:
                    st.info("Engine stopped. Waiting a moment before restarting...")
                    time.sleep(3)
                    start_engine()
                    st.success("Engine restart signal sent.")
                time.sleep(1)
                st.rerun()

    st.subheader("Engine Status & Control")
    
    status_placeholder = st.empty()

    def update_status():
        status, is_running = get_engine_status()
        if is_running:
            status_placeholder.success(f"**Status:** {status}")
        else:
            status_placeholder.info(f"**Status:** {status}")
        return is_running

    is_engine_running = update_status()

    st.markdown("---")

    # --- Live Equity Curve ---
    st.subheader("Live Portfolio Performance")
    # Create a container that will be updated by the auto-refresh loop
    live_chart_container = st.container()

    st.markdown("---")
    # --- Live Tick Data Health Check ---
    st.subheader("Live Tick Data Health Check")
    st.markdown("Shows the last 10 ticks received by the live engine. This is the most direct way to confirm the system is collecting data.")
    live_ticks_container = st.container()

    # --- Live Session Logs ---
    st.subheader("Live Session Logs")
    live_runs = [r for r in get_all_run_ids() if r.startswith('live_')]

    if not live_runs:
        st.info("No live trading sessions have been logged yet. Run `src/tick_collector.py` on your server to start a session.")
        return

    selected_run_id = st.selectbox("Select a Live Run ID to inspect:", options=live_runs, key="live_run_selector")

    st.subheader(f"Trade Log for Live Run: `{selected_run_id}`")
    trade_log_query = "SELECT * FROM paper_trades WHERE run_id = ? ORDER BY timestamp DESC;"
    trade_log_df = load_log_data(trade_log_query, params=(selected_run_id,))
    if not trade_log_df.empty:
        st.dataframe(trade_log_df)
    else:
        st.info("No trades were executed in this live session.")

    # --- Auto-refreshing logic ---
    # This block will now only re-render the content inside the containers above.
    is_market_open_now = is_market_working_day(datetime.date.today()) and \
                         NSE_MARKET_OPEN_TIME <= datetime.datetime.now().time() <= NSE_MARKET_CLOSE_TIME

    if is_market_open_now and st.session_state.is_engine_running:
        refresh_interval = st.sidebar.slider("Auto-Refresh Interval (seconds)", min_value=5, max_value=60, value=5, key="refresh_interval")
        
        while True:
            # Update status
            status, _ = get_engine_status()
            status_placeholder.info(f"**Status:** {status}")

            # Update equity curve
            live_runs = [r for r in get_all_run_ids() if r.startswith('live_')]
            if live_runs:
                latest_run_id = live_runs[0]
                portfolio_log_df = load_live_portfolio_log(latest_run_id)
                with live_chart_container:
                    st.markdown(f"Displaying equity curve for run: `{latest_run_id}`")
                    if not portfolio_log_df.empty:
                        st.line_chart(portfolio_log_df.set_index('timestamp'))
            
            # Update live ticks
            live_ticks_df = load_live_ticks()
            live_ticks_container.dataframe(live_ticks_df)

            time.sleep(refresh_interval)

def main():
    """Main function to run the Streamlit dashboard."""
    st.set_page_config(layout="wide")
    st.title("TraderBuddy Dashboard")

    # --- Primary Mode Selector using a visually appealing option menu ---
    with st.sidebar:
        app_mode = option_menu(
            menu_title="Main Menu",
            options=["Backtesting", "Live Paper Trading Monitor"],
            icons=['graph-up-arrow', 'broadcast-pin'], # Icons from https://icons.getbootstrap.com/
            menu_icon="none", # Set to "none" to disable the menu icon
            default_index=0,
        )

    # --- Conditional UI Rendering based on Mode ---
    if app_mode == "Backtesting":
        st.sidebar.header("Backtest Configuration")
        # --- Backtesting Sidebar Controls ---
        with st.sidebar.form(key='backtest_form'):
            # Symbols selection
            all_symbols = get_all_symbols()
            default_symbols = ["NSE:SBIN-EQ", "NSE:RELIANCE-EQ", "NSE:HDFCBANK-EQ"]
            pre_selected_symbols = [s for s in default_symbols if s in all_symbols]

            symbols_to_test = st.multiselect(
                "Select Symbols",
                options=all_symbols,
                default=pre_selected_symbols
            )

            # Backtest Type selection
            backtest_type = st.radio(
                "Backtest Type",
                ('Positional', 'Intraday'),
                index=0, # Default to Positional
                help="**Positional**: Holds trades across multiple days until an exit signal. **Intraday**: All open positions are force-closed at the end of each day (15:14)."
            )

            # Resolution selection
            resolutions = ["D", "60", "30", "15", "5", "1"]
            resolution = st.selectbox("Select Resolution", options=resolutions, index=2) # Default to 15 min

            # Generate time options for select boxes
            time_options = get_market_time_options()

            # Date Range selection
            st.markdown("---")
            st.markdown("##### End Date & Time")
            end_date = st.date_input("End Date", value=datetime.date.today(), key="end_date")
            end_time = st.selectbox("End Time", options=time_options, index=len(time_options) - 1, key="end_time")
            end_datetime = datetime.datetime.combine(end_date, end_time)

            st.markdown("##### Start Date & Time")
            start_date = st.date_input("Start Date", value=end_datetime.date() - datetime.timedelta(days=90), key="start_date")
            start_time = st.selectbox("Start Time", options=time_options, index=0, key="start_time")
            start_datetime = datetime.datetime.combine(start_date, start_time)

            # --- Strategy Selection ---
            st.markdown("---")
            selected_strategy_name = st.selectbox(
                "Select Strategy",
                options=list(STRATEGY_MAPPING.keys())
            )
            strategy_class = STRATEGY_MAPPING[selected_strategy_name]

            # --- Backtest Mode Selection ---
            run_optimization = st.checkbox("Enable Parameter Optimization")

            strategy_params: dict[str, object] = {}
            optimization_params: dict[str, object] = {}

            if run_optimization:
                st.subheader("Optimization Ranges")
                optimizable_params = strategy_class.get_optimizable_params()
                for param in optimizable_params:
                    if param['type'] == 'slider':
                        optimization_params[param['name']] = st.slider(param['label'], param['min'], param['max'], param['default'])
                        optimization_params[f"{param['name']}_step"] = st.number_input(f"{param['name'].replace('_', ' ').title()} Step", 1, 10, param['step'])
                run_button_label = "Run Optimization"
            else:
                st.subheader(f"Parameters for {selected_strategy_name}")
                strategy_params['short_window'] = st.slider("Short Window", min_value=1, max_value=50, value=9)
                strategy_params['long_window'] = st.slider("Long Window", min_value=10, max_value=200, value=21)
                run_button_label = "Run Backtest"

            st.subheader("Common Parameters")
            trade_quantity = st.slider("Trade Quantity", min_value=1, max_value=1000, value=100, key="common_trade_quantity")
            initial_cash = st.number_input("Initial Cash", min_value=1000.0, value=100000.0, step=1000.0)
            
            # The button that submits the form
            run_button_clicked = st.form_submit_button(run_button_label, use_container_width=True)
            if run_button_clicked:
                st.session_state.run_button_clicked = True

        # --- Main Panel Rendering ---
        render_backtesting_ui(symbols_to_test, backtest_type, resolution, start_datetime, end_datetime, selected_strategy_name, run_optimization, strategy_params, optimization_params, trade_quantity, initial_cash)
        
        # --- Backtest Run Logs ---
        st.header("Backtest Activity Logs")
        st.markdown("View logs from specific backtest runs.")
        backtest_runs = [r for r in get_all_run_ids() if not r.startswith('live_')]
        if not backtest_runs:
            st.info("No backtest activity has been logged yet. Run a backtest to see logs here.")
        else:
            selected_run_id = st.selectbox("Select a Backtest Run ID to inspect:", options=backtest_runs, key="backtest_run_selector")
            st.subheader(f"Trade Log for Run: `{selected_run_id}`")
            trade_log_query = "SELECT * FROM paper_trades WHERE run_id = ? ORDER BY timestamp DESC;"
            trade_log_df = load_log_data(trade_log_query, params=(selected_run_id,))
            if not trade_log_df.empty:
                st.dataframe(trade_log_df)
            else:
                st.info("No trades were executed in this backtest run.")

    elif app_mode == "Live Paper Trading Monitor":
        st.sidebar.header("Live Trading Configuration")
        
        # Load current config to pre-populate fields
        current_config, _ = load_config()
        if current_config is None:
            current_config = {} # Default to empty dict if no config exists

        with st.sidebar.form("live_config_form"):
            st.subheader("Strategy & Symbols")
            
            selected_strategy = st.selectbox(
                "Select Strategy", 
                options=list(STRATEGY_MAPPING.keys()),
                index=list(STRATEGY_MAPPING.keys()).index(current_config.get('strategy', 'Simple MA Crossover'))
            )

            all_symbols = get_all_symbols()
            selected_symbols = st.multiselect(
                "Select Symbols to Trade",
                options=all_symbols,
                default=current_config.get('symbols', [])
            )

            st.subheader("Strategy Parameters")
            # For now, we'll hardcode params for SMA Crossover. A more dynamic system could be built.
            param_short_window = st.slider("Short Window", 1, 50, current_config.get('params', {}).get('short_window', 9))
            param_long_window = st.slider("Long Window", 10, 200, current_config.get('params', {}).get('long_window', 21))
            param_trade_quantity = st.number_input("Trade Quantity", 1, 1000, current_config.get('params', {}).get('trade_quantity', 100))

            submitted = st.form_submit_button("Save Live Configuration", use_container_width=True)
            if submitted:
                new_config = {
                    'strategy': selected_strategy,
                    'symbols': selected_symbols,
                    'params': {'short_window': param_short_window, 'long_window': param_long_window, 'trade_quantity': param_trade_quantity}
                }
                success, message = save_config(new_config)
                if success:
                    st.sidebar.success(message)
                else:
                    st.sidebar.error(message)
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Monitor Controls")
        # --- Main Panel Rendering ---
        render_live_monitor_ui()

if __name__ == "__main__":
    main()
