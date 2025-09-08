# tests/backtesting/test_engine_multi_timeframe.py

import sys
import os
import pytest
import pandas as pd
import datetime
import sqlite3
from unittest.mock import MagicMock, patch

# Add the project root to the Python path to allow absolute imports from src
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.backtesting.engine import BacktestingEngine
from src.strategies.base_strategy import BaseStrategy

# Mock database file for testing
@pytest.fixture
def mock_db_file(tmp_path):
    db_path = tmp_path / "test_historical_data.sqlite"
    con = sqlite3.connect(db_path)
    cursor = con.cursor()
    cursor.execute("CREATE TABLE historical_data (timestamp TEXT, symbol TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, resolution TEXT);")
    
    # Insert sample data for multiple resolutions
    data = [
        # Daily data
        ('2024-01-01 00:00:00', 'SYM1', 100, 105, 99, 104, 1000, 'D'),
        ('2024-01-01 00:00:00', 'SYM2', 200, 205, 199, 204, 2000, 'D'),
        ('2024-01-02 00:00:00', 'SYM1', 104, 106, 103, 105, 1100, 'D'),
        ('2024-01-02 00:00:00', 'SYM2', 204, 206, 203, 205, 2100, 'D'),
        # 60-min data
        ('2024-01-01 09:15:00', 'SYM1', 100, 101, 99, 100.5, 100, '60'),
        ('2024-01-01 10:15:00', 'SYM1', 100.5, 102, 100, 101.5, 110, '60'),
        ('2024-01-01 09:15:00', 'SYM2', 200, 201, 199, 200.5, 200, '60'),
        ('2024-01-01 10:15:00', 'SYM2', 200.5, 202, 200, 201.5, 210, '60'),
        # 1-min data (for a specific 60-min bar)
        ('2024-01-01 09:15:00', 'SYM1', 100, 100.2, 99.8, 100.1, 10, '1'),
        ('2024-01-01 09:16:00', 'SYM1', 100.1, 100.3, 100, 100.2, 11, '1'),
        # Data for 2024-01-03 for missing data test
        ('2024-01-03 00:00:00', 'SYM1', 100, 105, 99, 104, 1000, 'D'),
    ]
    cursor.executemany("INSERT INTO historical_data VALUES (?,?,?,?,?,?,?,?)", data)
    con.commit()
    con.close()
    return db_path

# Mock strategy to capture on_data calls
class MockStrategy(BaseStrategy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_data_calls = []

    def on_data(self, timestamp: datetime.datetime, market_data_all_resolutions: dict, **kwargs):
        self.on_data_calls.append({
            'timestamp': timestamp,
            'market_data': market_data_all_resolutions,
            'kwargs': kwargs
        })

    @staticmethod
    def get_optimizable_params():
        return []

def test_engine_loads_multiple_resolutions(mock_db_file):
    engine = BacktestingEngine(
        start_datetime=datetime.datetime(2024, 1, 1),
        end_datetime=datetime.datetime(2024, 1, 2),
        db_file=mock_db_file,
        resolutions=['D', '60', '1']
    )
    engine.run(MockStrategy, ['SYM1', 'SYM2'], {})
    loaded_data = engine.all_loaded_data # Access the stored data

    assert isinstance(loaded_data, dict)
    assert 'D' in loaded_data
    assert '60' in loaded_data
    assert '1' in loaded_data
    assert isinstance(loaded_data['D'], pd.DataFrame)
    assert isinstance(loaded_data['60'], pd.DataFrame)
    assert isinstance(loaded_data['1'], pd.DataFrame)
    assert not loaded_data['D'].empty
    assert not loaded_data['60'].empty
    assert not loaded_data['1'].empty

def test_engine_passes_multi_resolution_data_to_strategy(mock_db_file):
    engine = BacktestingEngine(
        start_datetime=datetime.datetime(2024, 1, 1),
        end_datetime=datetime.datetime(2024, 1, 2),
        db_file=mock_db_file,
        resolutions=['D', '60', '1'] # Primary resolution is Daily
    )
    mock_strategy_instance = MockStrategy(symbols=['SYM1', 'SYM2'], portfolio=MagicMock(), order_manager=MagicMock())
    mock_strategy_instance.__class__.__name__ = "MockStrategy" # Set __name__ for printing in engine
    
    with patch('src.strategies.base_strategy.BaseStrategy') as MockBaseStrategy:
        MockBaseStrategy.return_value = mock_strategy_instance
        MockBaseStrategy.__name__ = "MockStrategy" # Set __name__ for printing in engine
        engine.run(MockBaseStrategy, ['SYM1', 'SYM2'], {})

    # Check on_data calls
    assert len(mock_strategy_instance.on_data_calls) > 0
    first_call = mock_strategy_instance.on_data_calls[0]
    
    # Verify timestamp
    assert first_call['timestamp'] == datetime.datetime(2024, 1, 1, 0, 0, 0)

    # Verify data structure for the first call
    market_data = first_call['market_data']
    assert '60' in market_data
    assert '1' in market_data
    assert 'D' in market_data

    # Check content for 60-min data (should be empty for 00:00:00 timestamp)
    assert not market_data['60']

    # Check content for 1-min data (should be empty for 00:00:00 timestamp)
    assert not market_data['1']

    # Check content for Daily data
    assert 'SYM1' in market_data['D']
    assert market_data['D']['SYM1']['close'] == 104 # From 2024-01-01 00:00:00

    # Now, test for a timestamp where 60-min and 1-min data exist
    engine = BacktestingEngine(
        start_datetime=datetime.datetime(2024, 1, 1, 9, 15, 0),
        end_datetime=datetime.datetime(2024, 1, 1, 9, 15, 0),
        db_file=mock_db_file,
        resolutions=['60', '1', 'D'] # Primary resolution is 60-min
    )
    mock_strategy_instance_2 = MockStrategy(symbols=['SYM1', 'SYM2'], portfolio=MagicMock(), order_manager=MagicMock())
    mock_strategy_instance_2.__class__.__name__ = "MockStrategy" # Set __name__ for printing in engine
    
    with patch('src.strategies.base_strategy.BaseStrategy') as MockBaseStrategy_2:
        MockBaseStrategy_2.return_value = mock_strategy_instance_2
        MockBaseStrategy_2.__name__ = "MockStrategy" # Set __name__ for printing in engine
        engine.run(MockBaseStrategy_2, ['SYM1', 'SYM2'], {})

    assert len(mock_strategy_instance_2.on_data_calls) > 0
    second_call = mock_strategy_instance_2.on_data_calls[0]

    # Verify timestamp
    assert second_call['timestamp'] == datetime.datetime(2024, 1, 1, 9, 15, 0)

    # Verify data structure for the second call
    market_data_2 = second_call['market_data']
    assert '60' in market_data_2
    assert '1' in market_data_2
    assert 'D' in market_data_2

    # Check content for 60-min data
    assert 'SYM1' in market_data_2['60']
    assert market_data_2['60']['SYM1']['close'] == 100.5 # From 2024-01-01 09:15:00

    # Check content for 1-min data
    assert 'SYM1' in market_data_2['1']
    assert market_data_2['1']['SYM1']['close'] == 100.1 # From 2024-01-01 09:15:00

    # Check content for Daily data (should be empty for this intraday timestamp)
    assert not market_data_2['D']


def test_engine_handles_missing_data_for_resolution(mock_db_file):
    engine = BacktestingEngine(
        start_datetime=datetime.datetime(2024, 1, 3), # Date with no 60-min or 1-min data
        end_datetime=datetime.datetime(2024, 1, 3),
        db_file=mock_db_file,
        resolutions=['D', '60', '1']
    )
    mock_strategy_instance = MockStrategy(symbols=['SYM1'], portfolio=MagicMock(), order_manager=MagicMock())
    mock_strategy_instance.__class__.__name__ = "MockStrategy" # Set __name__ for printing in engine
    
    with patch('src.strategies.base_strategy.BaseStrategy') as MockBaseStrategy:
        MockBaseStrategy.return_value = mock_strategy_instance
        MockBaseStrategy.__name__ = "MockStrategy" # Set __name__ for printing in engine
        engine.run(MockBaseStrategy, ['SYM1'], {})

    assert len(mock_strategy_instance.on_data_calls) > 0
    first_call = mock_strategy_instance.on_data_calls[0]
    market_data = first_call['market_data']

    assert 'D' in market_data
    assert '60' in market_data
    assert '1' in market_data

    assert market_data['D'] # Daily data should exist
    assert not market_data['60'] # 60-min data should be empty for this timestamp
    assert not market_data['1'] # 1-min data should be empty for this timestamp
