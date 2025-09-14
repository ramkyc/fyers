# src/strategies/__init__.py

from .simple_ma_crossover import SMACrossoverStrategy
from .opening_price_crossover import OpeningPriceCrossoverStrategy
from .bt_opening_price_crossover import OpeningPriceCrossoverStrategy as BT_OpeningPriceCrossoverStrategy
# Add other strategies here as they are created
# from .rsi_strategy import RSIStrategy

# This mapping is used by the LIVE TRADING engine.
STRATEGY_MAPPING = {
    "Simple MA Crossover": SMACrossoverStrategy,
    "Opening Price Crossover": OpeningPriceCrossoverStrategy,
}

# This separate mapping is used by the BACKTESTING UI.
# This allows us to test changes to a strategy in backtesting without
# affecting the live trading version.
STRATEGY_MAPPING_BT = {
    "Simple MA Crossover": SMACrossoverStrategy,
    "Opening Price Crossover": BT_OpeningPriceCrossoverStrategy,
}
