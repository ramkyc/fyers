# run_backtest.py

import yaml
import os

from src.backtesting.engine import BacktestingEngine
from src.strategies.simple_ma_crossover import SMACrossoverStrategy

# A mapping from strategy names in the config to their actual classes
STRATEGY_MAPPING = {
    "SMACrossoverStrategy": SMACrossoverStrategy,
    # Add other strategies here as they are created
}

def load_config(config_path='config.yaml'):
    """Loads the backtest configuration from a YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

if __name__ == "__main__":
    # --- Configuration ---
    config = load_config()
    backtest_config = config['backtest']

    db_file = os.path.join(os.path.dirname(__file__), 'data', 'ticks.duckdb')
    
    start_date = backtest_config['start_date']
    end_date = backtest_config['end_date']
    symbols_to_test = backtest_config['symbols']
    
    strategy_name = backtest_config['strategy']['name']
    strategy_class = STRATEGY_MAPPING.get(strategy_name)
    if not strategy_class:
        raise ValueError(f"Strategy '{strategy_name}' not found in STRATEGY_MAPPING.")

    strategy_params = backtest_config['strategy']['params']
    initial_cash = backtest_config['initial_cash']
    resolution = backtest_config['strategy'].get('resolution', 'D') # Get resolution from config, default to Daily

    # --- Execution ---
    
    # Initialize the backtesting engine
    engine = BacktestingEngine(
        start_date=start_date,
        end_date=end_date,
        db_file=db_file,
        resolution=resolution # Pass resolution to the engine
    )

    # Run the backtest
    engine.run(
        strategy_class=strategy_class,
        symbols=symbols_to_test,
        params=strategy_params,
        initial_cash=initial_cash
    )
