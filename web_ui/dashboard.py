import sys
sys.dont_write_bytecode = True # Prevent __pycache__ creation

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import datetime
import duckdb
import plotly.graph_objects as go
import plotly.express as px
import concurrent.futures

from src.paper_trading.portfolio import Portfolio
from src.reporting.performance_analyzer import PerformanceAnalyzer
from src.backtesting.engine import BacktestingEngine
import config # config.py is now in the project root
from src.strategies.simple_ma_crossover import SMACrossoverStrategy
# Add other strategies here as they are created
# from src.strategies.rsi_strategy import RSIStrategy

STRATEGY_MAPPING = {
    "Simple MA Crossover": SMACrossoverStrategy,
}

# --- Configuration ---
HISTORICAL_TABLE = "historical_data"

# --- Helper Functions ---
@st.cache_resource
def get_db_connection(db_file):
    """Establishes and returns a DuckDB connection."""
    return duckdb.connect(database=db_file, read_only=True)

@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_historical_data(symbols, resolution, start_date, end_date):
    """
    Loads historical data from the database for display purposes.
    """
    # This function specifically reads from the market data DB
    if not os.path.exists(config.MARKET_DB_FILE):
        st.warning(f"Market data file not found at {config.MARKET_DB_FILE}")
        return pd.DataFrame()
        
    con = get_db_connection(config.MARKET_DB_FILE)
    symbols_tuple = tuple(symbols)
    query = f"""
        SELECT timestamp, symbol, close
        FROM {HISTORICAL_TABLE}
        WHERE symbol IN {symbols_tuple}
        AND resolution = '{resolution}'
        AND timestamp BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY timestamp ASC;
        """
    df = con.execute(query).fetchdf()
    return df

@st.cache_data(ttl=60) # Cache for 1 minute
def load_log_data(query):
    """Loads log data from the database."""
    # This function specifically reads from the trading log DB
    if not os.path.exists(config.TRADING_DB_FILE):
        # It's not an error if this file doesn't exist yet
        return pd.DataFrame()

    con = get_db_connection(config.TRADING_DB_FILE)
    df = con.execute(query).fetchdf()
    return df

@st.cache_data(ttl=600) # Cache for 10 minutes
def get_all_symbols():
    """Fetches all unique symbols from the historical data table."""
    if not os.path.exists(config.MARKET_DB_FILE):
        st.warning(f"Market data file not found at {config.MARKET_DB_FILE}. Please run `python src/fetch_symbols.py` to generate it.")
        return []
    con = get_db_connection(config.MARKET_DB_FILE)
    query = "SELECT DISTINCT symbol FROM historical_data ORDER BY symbol;"
    df = con.execute(query).fetchdf()
    return df['symbol'].tolist() if not df.empty else []

def run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash):
    """Runs a backtest and captures its stdout log."""
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    with redirect_stdout(f):
        portfolio_result, last_prices = engine.run(
            strategy_class=strategy_class,
            symbols=symbols,
            params=params,
            initial_cash=initial_cash
        )
    backtest_log = f.getvalue()
    return portfolio_result, last_prices, backtest_log

# This function must be defined at the top level to be pickleable by multiprocessing
def run_backtest_for_worker(args):
    """
    A self-contained function to run a single backtest.
    Designed to be executed in a separate process to enable parallelization.
    """
    start_date_str, end_date_str, db_file, resolution, symbols, params, initial_cash, strategy_name = args

    # These imports are necessary inside the worker process
    from src.backtesting.engine import BacktestingEngine
    from src.reporting.performance_analyzer import PerformanceAnalyzer
    strategy_class = STRATEGY_MAPPING[strategy_name]

    engine = BacktestingEngine(
        start_date=start_date_str,
        end_date=end_date_str,
        db_file=db_file,
        resolution=resolution
    )
    
    portfolio_result, last_prices, _ = run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash)
    
    if portfolio_result and last_prices:
        analyzer = PerformanceAnalyzer(portfolio_result)
        metrics = analyzer.calculate_metrics(last_prices)
        metrics.update(params) # Add all params to the result for later joining
        return metrics
    return None

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
    col1.metric("Total P&L", f"₹{metrics['total_pnl']:,.2f}", f"{metrics['total_pnl'] / (metrics['initial_cash'] or 1):.2%}")
    col2.metric("Max Drawdown", f"{metrics['max_drawdown'] * 100:.2f}%")
    col3.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")
    col4.metric("Win Rate", f"{metrics['win_rate']:.2%}")
    col5.metric("Profit Factor", f"{metrics['profit_factor']:.2f}")

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

def main():
    """Main function to run the Streamlit dashboard."""
    st.set_page_config(layout="wide")
    st.title("TraderBuddy Dashboard")

    # --- Sidebar for Configuration ---
    st.sidebar.header("Backtest Configuration")

    # Symbols selection
    all_symbols = get_all_symbols()
    default_symbols = ["NSE:SBIN-EQ", "NSE:RELIANCE-EQ", "NSE:HDFCBANK-EQ"]
    pre_selected_symbols = [s for s in default_symbols if s in all_symbols]

    symbols_to_test = st.sidebar.multiselect(
        "Select Symbols",
        options=all_symbols,
        default=pre_selected_symbols
    )

    # Resolution selection
    resolutions = ["D", "60", "15", "5", "1"]
    resolution = st.sidebar.selectbox("Select Resolution", options=resolutions, index=2) # Default to 15 min

    # Date Range selection
    end_date = st.sidebar.date_input("End Date", value=datetime.date.today())
    start_date = st.sidebar.date_input("Start Date", value=end_date - datetime.timedelta(days=90)) # Default to 3 months prior

    # --- Strategy Selection ---
    st.sidebar.header("Strategy Selection")
    selected_strategy_name = st.sidebar.selectbox(
        "Select Strategy",
        options=list(STRATEGY_MAPPING.keys())
    )
    strategy_class = STRATEGY_MAPPING[selected_strategy_name]

    # --- Backtest Mode Selection ---
    run_optimization = st.sidebar.checkbox("Enable Parameter Optimization")

    strategy_params = {}
    if run_optimization:
        st.sidebar.subheader("Optimization Ranges")
        if selected_strategy_name == "Simple MA Crossover":
            short_window_range = st.sidebar.slider("Short Window Range", 1, 50, (5, 15))
            short_window_step = st.sidebar.number_input("Short Window Step", 1, 10, 2)
            long_window_range = st.sidebar.slider("Long Window Range", 10, 200, (20, 50))
            long_window_step = st.sidebar.number_input("Long Window Step", 1, 10, 5)
        run_button_label = "Run Optimization"
    else:
        st.sidebar.subheader(f"Parameters for {selected_strategy_name}")
        if selected_strategy_name == "Simple MA Crossover":
            strategy_params['short_window'] = st.sidebar.slider("Short Window", min_value=1, max_value=50, value=9)
            strategy_params['long_window'] = st.sidebar.slider("Long Window", min_value=10, max_value=200, value=21)
        run_button_label = "Run Backtest"

    st.sidebar.subheader("Common Parameters")
    trade_quantity = st.sidebar.slider("Trade Quantity", min_value=1, max_value=1000, value=100, key="common_trade_quantity")
    initial_cash = st.sidebar.number_input("Initial Cash", min_value=1000.0, value=100000.0, step=1000.0)

    # --- Main Content Area ---
    if run_optimization:
        st.header("Parameter Optimization")
    else:
        st.header("Backtest Results")

    if st.sidebar.button(run_button_label):
        if not symbols_to_test:
            st.warning("Please select at least one symbol to run the backtest.")
        else:
            with st.spinner(f"Running backtest for {len(symbols_to_test)} symbols..."):
                start_date_str = start_date.strftime("%Y-%m-%d")
                end_date_str = end_date.strftime("%Y-%m-%d")

                if run_optimization:
                    param_combinations = []
                    if selected_strategy_name == "Simple MA Crossover":
                        short_windows = range(short_window_range[0], short_window_range[1] + 1, short_window_step)
                        long_windows = range(long_window_range[0], long_window_range[1] + 1, long_window_step)
                        param_combinations = [{'short_window': sw, 'long_window': lw} for sw in short_windows for lw in long_windows if sw < lw]

                    if not param_combinations:
                        st.warning("No valid parameter combinations found. Ensure short window is smaller than long window.")
                    else:
                        for p in param_combinations:
                            p['trade_quantity'] = trade_quantity
                        worker_args = [(start_date_str, end_date_str, MARKET_DB_FILE, resolution, symbols_to_test, params, initial_cash, selected_strategy_name) for params in param_combinations]
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
                    engine = BacktestingEngine(start_date=start_date_str, end_date=end_date_str, db_file=config.MARKET_DB_FILE, resolution=resolution)
                    
                    portfolio_result, last_prices, backtest_log = run_and_capture_backtest(
                        engine, strategy_class, symbols_to_test, strategy_params, initial_cash
                    )

                    if portfolio_result:
                        display_single_backtest_results(portfolio_result, last_prices, backtest_log)
                    else:
                        st.error("Backtest did not return any results.")
                        st.subheader("Backtest Log")
                        st.code(backtest_log)

    # --- Live Data Logs ---
    st.header("Live Data Logs")
    log_tab1, log_tab2 = st.tabs(["Portfolio Log", "Trade Log"])

    with log_tab1:
        st.subheader("Live Portfolio Log")
        portfolio_log_query = "SELECT * FROM portfolio_log ORDER BY timestamp DESC LIMIT 100;"
        portfolio_log_df = load_log_data(portfolio_log_query)
        if not portfolio_log_df.empty:
            st.dataframe(portfolio_log_df)
            st.line_chart(portfolio_log_df.set_index('timestamp')[['total_portfolio_value', 'cash', 'holdings_value']])
        else:
            st.info("No portfolio log data available.")

    with log_tab2:
        st.subheader("Trade Log")
        trade_log_query = "SELECT * FROM paper_trades ORDER BY timestamp DESC LIMIT 100;"
        trade_log_df = load_log_data(trade_log_query)
        if not trade_log_df.empty:
            st.dataframe(trade_log_df)
        else:
            st.info("No trade log data available.")

if __name__ == "__main__":
    main()
