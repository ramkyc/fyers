# run_backtest.py

import argparse
import datetime
import config

from src.backtesting.engine import BacktestingEngine
from src.strategies.simple_ma_crossover import SMACrossoverStrategy
from src.strategies.opening_price_crossover import OpeningPriceCrossoverStrategy

# Map strategy names to their classes
AVAILABLE_STRATEGIES = {
    "sma_crossover": SMACrossoverStrategy,
    "opening_price_crossover": OpeningPriceCrossoverStrategy
}

def main():
    parser = argparse.ArgumentParser(description="Run a trading strategy backtest.")
    parser.add_argument("-s", "--strategy", type=str, required=True, choices=AVAILABLE_STRATEGIES.keys(),
                        help="The name of the strategy to run.")
    parser.add_argument("--symbols", type=str, required=True,
                        help="Comma-separated list of symbols to trade (e.g., 'NSE:SBIN-EQ,NSE:RELIANCE-EQ').")
    parser.add_argument("--start", type=str, required=True,
                        help="Start date for the backtest in YYYY-MM-DD format.")
    parser.add_argument("--end", type=str, required=True,
                        help="End date for the backtest in YYYY-MM-DD format.")
    parser.add_argument("--resolutions", nargs='+', type=str, default=["D"],
                        help="Data resolutions (e.g., 'D', '60', '15'). Defaults to 'D'.")
    parser.add_argument("--cash", type=float, default=100000.0,
                        help="Initial cash for the portfolio.")

    args = parser.parse_args()

    # --- Parameter Parsing ---
    symbols = [s.strip() for s in args.symbols.split(',')]
    start_dt = datetime.datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.datetime.strptime(args.end, "%Y-%m-%d")
    strategy_class = AVAILABLE_STRATEGIES[args.strategy]

    # --- Engine Initialization ---
    engine = BacktestingEngine(
        start_datetime=start_dt,
        end_datetime=end_dt,
        db_file=config.HISTORICAL_MARKET_DB_FILE,
        resolutions=args.resolutions
    )

    # --- Strategy Execution ---
    # For now, we use default strategy params. This can be extended.
    strategy_params = {}
    engine.run(
        strategy_class=strategy_class,
        symbols=symbols,
        params=strategy_params,
        initial_cash=args.cash
    )

if __name__ == "__main__":
    main()
