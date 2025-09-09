# web_ui/pages/backtesting_ui.py

import streamlit as st
import pandas as pd
import datetime
import plotly.graph_objects as go
import concurrent.futures

from src.reporting.performance_analyzer import PerformanceAnalyzer
from src.backtesting.engine import BacktestingEngine
from src.strategies import STRATEGY_MAPPING
from web_ui.utils import get_all_symbols, get_market_time_options, load_log_data, get_all_run_ids, run_backtest_for_worker, run_and_capture_backtest
import config

def display_optimization_results(results_df):
    """Renders the UI for displaying optimization results."""
    st.subheader("Optimization Results")
    vis_metric = st.selectbox(
        "Select metric to visualize:",
        options=['Total P&L', 'Sharpe Ratio', 'Max Drawdown', 'Profit Factor']
    )
    param_cols = [col for col in results_df.columns if col not in ['Total P&L', 'Sharpe Ratio', 'Max Drawdown', 'Win Rate', 'Profit Factor', 'initial_cash', 'trade_quantity']]
    
    tab1, tab2, tab3 = st.tabs(["Summary Table", "2D Heatmap", "3D Surface Plot"])
    with tab1:
        st.dataframe(results_df.style.format({
            'Total P&L': "₹{:,.2f}", 'Sharpe Ratio': "{:.2f}", 'Max Drawdown': "{:.2f}%",
            'Win Rate': "{:.2%}", 'Profit Factor': "{:.2f}"
        }).background_gradient(cmap='viridis', subset=['Total P&L', 'Sharpe Ratio']))

    try:
        if len(param_cols) >= 2:
            pivot_df = results_df.pivot(index=param_cols[0], columns=param_cols[1], values=vis_metric)
            with tab2:
                st.subheader(f"{vis_metric} 2D Heatmap")
                fig_heatmap = go.Figure(data=go.Contour(
                    z=pivot_df.values, x=pivot_df.columns, y=pivot_df.index, colorscale='viridis',
                    contours=dict(coloring='heatmap', showlabels=True, labelfont=dict(size=10, color='white')),
                    colorbar=dict(title=vis_metric, titleside='right')
                ))
                fig_heatmap.update_layout(title=f'Strategy Performance Landscape ({vis_metric})', xaxis_title=param_cols[1], yaxis_title=param_cols[0])
                st.plotly_chart(fig_heatmap, use_container_width=True)
            with tab3:
                st.subheader(f"{vis_metric} 3D Surface Plot")
                fig_3d = go.Figure(data=[go.Surface(z=pivot_df.values, x=pivot_df.columns, y=pivot_df.index)])
                fig_3d.update_layout(title=f'Strategy Performance Landscape ({vis_metric})', scene=dict(xaxis_title=param_cols[1], yaxis_title=param_cols[0], zaxis_title=vis_metric))
                st.plotly_chart(fig_3d, use_container_width=True)
    except Exception as e:
        st.error(f"Could not generate visualizations. This can happen if there are not enough data points for a grid. Error: {e}")

def display_single_backtest_results(portfolio_result, last_prices, backtest_log):
    """Renders the UI for displaying single backtest results."""
    st.subheader("Performance Summary")
    analyzer = PerformanceAnalyzer(portfolio_result)
    metrics = analyzer.calculate_metrics(last_prices)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total P&L", f"₹{metrics['total_pnl']:,.2f}", f"{metrics['total_pnl'] / (metrics['initial_cash'] or 1):.2%}", help="Total Profit and Loss. The percentage shows the return on the initial cash.")
    col2.metric("Max Drawdown", f"{metrics['max_drawdown'] * 100:.2f}%", help="The largest peak-to-trough decline in portfolio value. A lower value is better.")
    col3.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}", help="Measures risk-adjusted return. A higher value indicates better performance for the amount of risk taken. Calculated using a 6% annual risk-free rate for Indian markets.")
    col4.metric("Win Rate", f"{metrics['win_rate']:.2%}", help="The percentage of trades that were profitable.")
    col5.metric("Profit Factor", f"{metrics['profit_factor']:.2f}", help="The ratio of gross profits to gross losses. A value greater than 1 indicates a profitable system.")

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

def render_page():
    """Renders the entire Backtesting page UI."""
    # --- Sidebar Configuration ---
    st.sidebar.header("Backtest Configuration")
    with st.sidebar.form(key='backtest_form'):
        all_symbols = get_all_symbols()
        default_symbols = ["NSE:SBIN-EQ", "NSE:RELIANCE-EQ", "NSE:HDFCBANK-EQ"]
        pre_selected_symbols = [s for s in default_symbols if s in all_symbols]
        symbols_to_test = st.multiselect("Select Symbols", options=all_symbols, default=pre_selected_symbols)
        backtest_type = st.radio("Backtest Type", ('Positional', 'Intraday'), index=0, help="**Positional**: Holds trades across multiple days. **Intraday**: All open positions are force-closed at the end of each day.")
        resolutions = ["D", "60", "30", "15", "5", "1"]
        resolution = st.selectbox("Select Resolution", options=resolutions, index=2)
        time_options = get_market_time_options()
        
        st.markdown("---")
        st.markdown("##### End Date & Time")
        end_date = st.date_input("End Date", value=datetime.date.today(), key="end_date")
        end_time = st.selectbox("End Time", options=time_options, index=len(time_options) - 1, key="end_time")
        end_datetime = datetime.datetime.combine(end_date, end_time)

        st.markdown("##### Start Date & Time")
        start_date = st.date_input("Start Date", value=end_datetime.date() - datetime.timedelta(days=90), key="start_date")
        start_time = st.selectbox("Start Time", options=time_options, index=0, key="start_time")
        start_datetime = datetime.datetime.combine(start_date, start_time)

        st.markdown("---")
        selected_strategy_name = st.selectbox("Select Strategy", options=list(STRATEGY_MAPPING.keys()))
        strategy_class = STRATEGY_MAPPING[selected_strategy_name]

        run_optimization = st.checkbox("Enable Parameter Optimization")
        strategy_params, optimization_params = {}, {}

        if run_optimization:
            st.subheader("Optimization Ranges")
            optimizable_params = strategy_class.get_optimizable_params()
            for param in optimizable_params:
                if param['type'] == 'slider':
                    optimization_params[param['name']] = st.slider(param['label'], param['min'], param['max'], param['default'], key=f"opt_{param['name']}")
                    optimization_params[f"{param['name']}_step"] = st.number_input(f"{param['name'].replace('_', ' ').title()} Step", 1, 10, param.get('step', 1), key=f"opt_step_{param['name']}")
            run_button_label = "Run Optimization"
        else:
            st.subheader(f"Parameters for {selected_strategy_name}")
            if selected_strategy_name == "Simple MA Crossover":
                strategy_params['short_window'] = st.slider("Short Window", 1, 50, 9, key="bt_sma_sw")
                strategy_params['long_window'] = st.slider("Long Window", 10, 200, 21, key="bt_sma_lw")
            elif selected_strategy_name == "Opening Price Crossover":
                strategy_params['ema_fast'] = st.slider("EMA Fast Period", 2, 20, 9, key="bt_opc_ef")
                strategy_params['ema_slow'] = st.slider("EMA Slow Period", 10, 50, 21, key="bt_opc_es")
                st.markdown("###### Stop-Loss Settings")
                strategy_params['atr_period'] = st.slider("ATR Period", 5, 50, 14, key="bt_opc_atr_p")
                strategy_params['atr_multiplier'] = st.number_input("ATR Multiplier", 1.0, 5.0, 1.5, 0.1, key="bt_opc_atr_m")
                st.markdown("###### Profit Target Settings")
                strategy_params['rr1'] = st.number_input("R:R Target 1", 0.1, 5.0, 0.5, 0.1, key="bt_opc_rr1")
                strategy_params['exit_pct1'] = st.slider("Exit % at T1", 10, 100, 50, 5, key="bt_opc_pct1")
                strategy_params['rr2'] = st.number_input("R:R Target 2", 0.5, 10.0, 1.5, 0.1, key="bt_opc_rr2")
                strategy_params['exit_pct2'] = st.slider("Exit % at T2", 10, 100, 20, 5, key="bt_opc_pct2")
                strategy_params['rr3'] = st.number_input("R:R Target 3", 1.0, 20.0, 3.0, 0.1, key="bt_opc_rr3")
                st.info("The remaining position will be sold at Target 3.")
            run_button_label = "Run Backtest"

        st.subheader("Common Parameters")
        strategy_params['trade_value'] = st.number_input("Trade Value (INR)", min_value=1000.0, value=25000.0, step=1000.0, key="bt_common_trade_value")
        initial_cash = st.number_input("Initial Cash", min_value=1000.0, value=200000.0, step=1000.0)
        
        run_button_clicked = st.form_submit_button(run_button_label, use_container_width=True)
        if run_button_clicked:
            st.session_state.run_button_clicked = True

    # --- Main Panel Rendering ---
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
                    param_combinations = strategy_class._generate_param_combinations(optimization_params)
                    if not param_combinations:
                        st.warning("No valid parameter combinations found. Ensure short window is smaller than long window.")
                    else:
                        for p in param_combinations:
                            p['trade_value'] = strategy_params['trade_value']
                        
                        worker_args = [(start_date_str, end_date_str, config.HISTORICAL_MARKET_DB_FILE, [resolution], symbols_to_test, params, initial_cash, selected_strategy_name, backtest_type) for params in param_combinations]
                        results = []
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
                    other_resolutions = set()
                    if resolution != "D": other_resolutions.add("D")
                    if selected_strategy_name == "Opening Price Crossover": other_resolutions.add("1")
                    final_resolutions = [resolution] + list(other_resolutions)

                    engine = BacktestingEngine(start_datetime=start_datetime, end_datetime=end_datetime, db_file=config.HISTORICAL_MARKET_DB_FILE, resolutions=final_resolutions)
                    portfolio_result, last_prices, backtest_log = run_and_capture_backtest(engine, strategy_class, symbols_to_test, strategy_params, initial_cash, backtest_type)

                    if portfolio_result:
                        display_single_backtest_results(portfolio_result, last_prices, backtest_log)
                    else:
                        st.error("Backtest did not return any results.")
                        st.subheader("Backtest Log")
                        st.code(backtest_log)

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