# src/strategies/__init__.py

from .simple_ma_crossover import SMACrossoverStrategy
from .opening_price_crossover import OpeningPriceCrossoverStrategy
# Add other strategies here as they are created
# from .rsi_strategy import RSIStrategy

STRATEGY_MAPPING = {
    "Simple MA Crossover": SMACrossoverStrategy,
    "Opening Price Crossover": OpeningPriceCrossoverStrategy,
}
