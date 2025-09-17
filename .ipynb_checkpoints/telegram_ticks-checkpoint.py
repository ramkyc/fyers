import zstandard as zstd
import pandas as pd
from datetime import timezone, datetime as dt

def create_df_from_zip(file_name):
    return pd.read_pickle(file_name, compression='zstd')

def ticks_for_token(token, df):
    return df[token]

def ticks_for_token_and_time(token, start_time, end_time, df):
    ticks = ticks_for_token(token, df)
    return [tick[1] for tick in ticks_for_token(token, df) if start_time <= tick[0] <= end_time]

if __name__ == "__main__":
    # Parse args
    file_name = "/Users/ramakrishna/Downloads/Telegram Desktop Downloads/2024-10-18_tick_data.zip"
    token = 11267842  # Get it from Actions / Positions file
    start_time = dt.fromisoformat('2024-10-07T15:02:36') # Time is UTC format
    end_time = dt.fromisoformat('2024-10-07T15:02:38') # Time is UTC format

    # Get ticks between time stamps
    df = create_df_from_zip(file_name)
    ticks = ticks_for_token_and_time(token, start_time, end_time, df)
    print(ticks)
