# update_daily_bar_timestamps.py
# This script updates all daily bars in the historical_data table to have the timestamp set to market close (15:30:00 IST = 10:00:00 UTC).

import sqlite3
import datetime

DB_PATH = 'data/historical_market_data.sqlite'  # Adjust path if needed
MARKET_CLOSE_IST = datetime.time(15, 30, 0)  # 3:30 PM IST

def update_daily_timestamps(db_path):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    # Select all daily bars
    cur.execute("SELECT rowid, timestamp FROM historical_data WHERE resolution = 'D'")
    rows = cur.fetchall()
    updates = []
    for rowid, ts in rows:
        # Parse the date part only
        date_part = datetime.datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').date()
        new_dt = datetime.datetime.combine(date_part, MARKET_CLOSE_IST)
        updates.append((new_dt.strftime('%Y-%m-%d %H:%M:%S'), rowid))
    # Update all rows
    cur.executemany("UPDATE historical_data SET timestamp = ? WHERE rowid = ?", updates)
    con.commit()
    print(f"Updated {len(updates)} daily bar timestamps to market close.")
    con.close()

if __name__ == "__main__":
    update_daily_timestamps(DB_PATH)
