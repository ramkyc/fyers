# src/run_atr_rr_optimization.py

import os
import sys
import datetime
import pandas as pd
import concurrent.futures
from itertools import product

# --- Add project root to sys.path ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config
from src.backtesting.bt_engine import BT_Engine
from src.strategies.bt_opening_price_crossover import OpeningPriceCrossoverStrategy
from src.fetch_historical_data import get_top_nifty_stocks
from src.reporting.performance_analyzer import PerformanceAnalyzer
from src.symbol_manager import SymbolManager

def run_backtest_for_worker(args):
    """
    A wrapper function to be executed by each parallel process.
    It unpacks arguments, runs a backtest, and returns a dictionary of results.
    """
    start_dt, end_dt, db_path, resolutions, symbols, params, initial_cash, strategy_name, backtest_type, primary_resolution = args

    try:
        # --- FIX: Explicitly initialize the SymbolManager in each worker process ---
        # This ensures that lot size data is loaded correctly for the backtest.
        SymbolManager().reload_master_data()

        # Select the correct strategy class
        strategy_class = {"Opening Price Crossover": OpeningPriceCrossoverStrategy}.get(strategy_name)
        if not strategy_class:
            return None

        # --- CORRECTED: Instantiate the engine with its required arguments ---
        engine = BT_Engine(
            start_datetime=start_dt,
            end_datetime=end_dt,
            resolutions=resolutions,
        )
        # --- CORRECTED: Call the run method with its required arguments ---
        portfolio_result, last_prices, _, _ = engine.run(
            strategy_class=strategy_class,
            symbols=symbols,
            params=params,
            initial_cash=initial_cash,
            backtest_type=backtest_type
        )

        if portfolio_result and portfolio_result.trades:
            analyzer = PerformanceAnalyzer(portfolio_result)
            metrics = analyzer.calculate_metrics(last_prices)
            
            # Combine parameters and metrics for the final result row
            result_row = params.copy()
            result_row['Timeframe'] = primary_resolution
            result_row['Trading Method'] = backtest_type
            result_row.update({
                'Total P&L': metrics['total_pnl'],
                'Sharpe Ratio': metrics['sharpe_ratio'],
                'Max Drawdown': metrics['max_drawdown'],
                'Win Rate': metrics['win_rate'],
                'Profit Factor': metrics['profit_factor'],
                'Total Trades': metrics['total_trades']
            })
            return result_row
        return None
    except Exception as e:
        print(f"Worker failed for params {params}. Error: {e}")
        return None

def main():
    """
    Main function to configure and run the optimization.
    """
    print("--- Starting ATR & R:R Parameter Optimization ---")

    # --- 1. Define Fixed Parameters ---
    start_datetime = datetime.datetime(2024, 4, 1, 9, 15, 0) # As requested
    end_datetime = datetime.datetime(2025, 3, 31, 15, 30, 0) # As requested
    initial_cash = 100000000.0 # As requested: 10 Crore
    symbols_to_test = get_top_nifty_stocks(top_n=50)

    # --- 2. Define Parameter Ranges ---
    atr_multipliers = [1.0, 1.25, 1.5, 1.75, 2.0]
    rr1_values = [0.5, 1.0, 1.5, 2.0]
    timeframes = ["5", "15", "30", "60", "D"]
    trading_methods = ["Positional", "Intraday"]

    # --- 3. Generate Parameter Combinations ---
    # Use itertools.product to get all combinations of the optimization parameters
    optimization_space = product(atr_multipliers, rr1_values, timeframes, trading_methods)

    param_combinations = []
    worker_args = []

    for atr_mult, rr1, timeframe, trade_method in optimization_space:
        rr2 = rr1 + 0.5
        rr3 = rr2 + 0.5
        param_combinations.append({
            'atr_multiplier': atr_mult,
            'rr1': rr1,
            'rr2': rr2,
            'rr3': rr3,
            # Keep other params fixed at their defaults
            'ema_fast': 9,
            'ema_slow': 21,
            'atr_period': 14,
            'exit_pct1': 0.5,
            'exit_pct2': 0.2,
            'trade_value': 100000.0
        })
        
        # The strategy needs 'D' and '1' for its logic, in addition to the primary resolution
        required_resolutions = sorted(list({timeframe, "D", "1"}))
        
        # Prepare arguments for the worker process
        args_tuple = (start_datetime, end_datetime, config.HISTORICAL_MARKET_DB_FILE, required_resolutions, symbols_to_test, param_combinations[-1], initial_cash, "Opening Price Crossover", trade_method, timeframe)
        worker_args.append(args_tuple)

    print(f"Generated {len(param_combinations)} parameter combinations to test against {len(symbols_to_test)} symbols.")
    
    results = []
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # Use executor.map to process the jobs and get an iterator for the results
        map_results = executor.map(run_backtest_for_worker, worker_args)
        
        for i, result in enumerate(map_results):
            if result:
                results.append(result)
            print(f"  -> Completed {i + 1} of {len(param_combinations)} backtests...")

    # --- 5. Analyze and Save Results ---
    if results:
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values(by='Sharpe Ratio', ascending=False)
        
        print("\n--- Top 20 Optimization Results (Sorted by Sharpe Ratio) ---")
        print(results_df.head(20).to_string())
        
        output_path = os.path.join(project_root, 'atr_rr_optimization_results.csv')
        results_df.to_csv(output_path, index=False)
        print(f"\nFull results saved to: {output_path}")
    else:
        print("\nOptimization run completed, but no valid results were generated.")

if __name__ == "__main__":
    main()
