# src/utils/compare_db_schemas.py

import sqlite3
import os
import sys
import pandas as pd
import argparse

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

def get_db_schema(db_path):
    """
    Connects to a SQLite database and returns its schema as a dictionary.

    Args:
        db_path (str): The full path to the SQLite database file.

    Returns:
        dict: A dictionary where keys are table names and values are pandas
              DataFrames describing the schema of each table.
              Returns None if the database file does not exist.
    """
    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found at: {db_path}")
        return None

    schema = {}
    try:
        with sqlite3.connect(db_path) as con:
            cursor = con.cursor()
            # Get all table names from the database
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            for table_name in tables:
                # For each table, get its structure
                pragma_sql = f"PRAGMA table_info('{table_name}');"
                df = pd.read_sql_query(pragma_sql, con)
                schema[table_name] = df

    except Exception as e:
        print(f"ERROR: Could not read schema from {db_path}. Reason: {e}")
        return None

    return schema

def overwrite_tables_from_root(tables_to_overwrite: list):
    """
    Overwrites specified tables in the data directory DB with data
    from the DB in the project root.
    """
    dest_db = config.HISTORICAL_MARKET_DB_FILE
    source_db = os.path.join(config.project_root, 'historical_market_data.sqlite')

    if not os.path.exists(source_db):
        print(f"ERROR: Source database not found at: {source_db}")
        return
    if not os.path.exists(dest_db):
        print(f"ERROR: Destination database not found at: {dest_db}")
        return

    for table_name in tables_to_overwrite:
        print(f"\n--- Preparing to Overwrite Table: '{table_name}' ---")
        print(f"Source:      {source_db}")
        print(f"Destination: {dest_db}")

        try:
            # Get row counts for user confirmation
            with sqlite3.connect(f'file:{source_db}?mode=ro', uri=True) as con:
                source_count = pd.read_sql_query(f"SELECT COUNT(*) FROM {table_name}", con).iloc[0, 0]
            with sqlite3.connect(f'file:{dest_db}?mode=ro', uri=True) as con:
                # Handle case where table might not exist in destination
                try:
                    dest_count = pd.read_sql_query(f"SELECT COUNT(*) FROM {table_name}", con).iloc[0, 0]
                except pd.io.sql.DatabaseError:
                    dest_count = 0

            print(f"Source table has {source_count:,} rows.")
            print(f"Destination table has {dest_count:,} rows.")

            confirm = input(f"Are you sure you want to replace the destination table with {source_count:,} rows from the source? (y/n): ").lower()
            if confirm != 'y':
                print("Operation cancelled for this table.")
                continue

            print("\nStarting data migration...")

            # 1. Read all data from the source table
            print("  - Step 1: Reading data from source...")
            with sqlite3.connect(f'file:{source_db}?mode=ro', uri=True) as source_con:
                df = pd.read_sql_query(f"SELECT * FROM {table_name}", source_con)
            print(f"  - Read {len(df):,} rows successfully.")

            # 2. Overwrite the destination table
            print("  - Step 2: Writing data to destination...")
            with sqlite3.connect(dest_db) as dest_con:
                # Using 'replace' will drop the table first and then create a new one and insert data.
                df.to_sql(table_name, dest_con, if_exists='replace', index=False)

                # Special handling: Re-create unique index for specific tables if needed
                if table_name == 'historical_data':
                    cursor = dest_con.cursor()
                    cursor.execute("""
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_historical_data_unique 
                        ON historical_data(timestamp, symbol, resolution);
                    """)
                    print("  - Wrote data and recreated unique index for 'historical_data'.")
                else:
                    print("  - Wrote data successfully.")

            print(f"\n✅ SUCCESS: Data overwrite for table '{table_name}' complete.")

        except Exception as e:
            print(f"\n❌ ERROR: An error occurred during the overwrite process for '{table_name}': {e}")

def get_row_counts(db_path, tables):
    """Gets the row count for a list of tables in a database."""
    counts = {}
    if not os.path.exists(db_path) or not tables:
        return counts
    try:
        # Connect in read-only mode
        with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as con:
            cursor = con.cursor()
            for table in tables:
                try:
                    # Use pandas for simplicity and safety
                    count = pd.read_sql_query(f"SELECT COUNT(*) FROM {table}", con).iloc[0, 0]
                    counts[table] = count
                except Exception:
                    counts[table] = "Error" # Handle cases where table might be corrupt
    except Exception as e:
        print(f"Warning: Could not get row counts from {db_path}. Reason: {e}")
    return counts


def compare_schemas():
    """
    Compares the schemas and file sizes of the two historical_market_data.sqlite files.
    """
    # Path to the database in the /data directory (the correct one)
    db_path_data_dir = config.HISTORICAL_MARKET_DB_FILE

    # Path to the database in the project root directory (the stray one)
    db_path_root_dir = os.path.join(config.project_root, 'historical_market_data.sqlite')

    print("--- Database Schema & Size Comparison ---")

    # Get and print file sizes
    size1_mb = os.path.getsize(db_path_data_dir) / (1024 * 1024) if os.path.exists(db_path_data_dir) else 0
    print(f"DB 1 (Data Dir): {db_path_data_dir} | Size: {size1_mb:.2f} MB")

    size2_mb = os.path.getsize(db_path_root_dir) / (1024 * 1024) if os.path.exists(db_path_root_dir) else 0
    print(f"DB 2 (Root Dir): {db_path_root_dir} | Size: {size2_mb:.2f} MB\n")

    print("--- Schema Analysis ---")

    schema1 = get_db_schema(db_path_data_dir)
    schema2 = get_db_schema(db_path_root_dir)

    if schema1 is None or schema2 is None:
        print("\nComparison aborted due to errors reading a database file.")
        return

    tables1 = set(schema1.keys())
    tables2 = set(schema2.keys())

    # --- Report differences ---
    common_tables = sorted(list(tables1.intersection(tables2)))
    tables_only_in_1 = tables1 - tables2
    tables_only_in_2 = tables2 - tables1

    # Get row counts for common tables
    counts1 = get_row_counts(db_path_data_dir, common_tables)
    counts2 = get_row_counts(db_path_root_dir, common_tables)

    # Check for perfect structural identity first
    if tables1 == tables2 and all(schema1[tbl].equals(schema2[tbl]) for tbl in tables1):
        print("✅ SUCCESS: The database schemas are IDENTICAL.")
        print("Both files have the same tables and column structures.")
    else:
        print("❌ NOTICE: The database schemas are DIFFERENT.\n")

    # --- Detailed Table-by-Table Report ---
    print("--- Table Details ---")
    report_data = []
    for table in common_tables:
        count1 = counts1.get(table, 'N/A')
        count2 = counts2.get(table, 'N/A')
        report_data.append({'Table Name': table, 'Rows (DB 1)': f"{count1:,}", 'Rows (DB 2)': f"{count2:,}"})
    
    if report_data:
        report_df = pd.DataFrame(report_data)
        print(report_df.to_string(index=False))
        print("")

    if tables_only_in_1:
        print(f"Tables found ONLY in DB 1 (Data Dir): {', '.join(tables_only_in_1)}")
    if tables_only_in_2:
        print(f"Tables found ONLY in DB 2 (Root Dir): {', '.join(tables_only_in_2)}")

    print("\n--- Structure Comparison for Common Tables ---")
    for table in common_tables:
        df1 = schema1[table]
        df2 = schema2[table]
        if not df1.equals(df2):
            print(f"  - Table '{table}': Schemas are IDENTICAL.")
        else:
            print(f"  - Table '{table}': Schemas are DIFFERENT.")
            # To show the exact difference, we can merge the two schema dataframes
            merged_df = pd.merge(df1, df2, on='name', suffixes=('_db1', '_db2'), how='outer')
            print("    Details:")
            print(merged_df[['name', 'type_db1', 'type_db2']].to_string(index=False, na_rep='-MISSING-'))
            print("-" * 20)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare or manage duplicate database files.")
    parser.add_argument(
        '--overwrite-from-root',
        nargs='+',
        metavar='TABLE_NAME',
        help="Overwrite one or more tables (e.g., historical_data symbol_master) in the data/ directory DB with data from the project root DB."
    )
    args = parser.parse_args()

    if args.overwrite_from_root:
        overwrite_tables_from_root(args.overwrite_from_root)
    else:
        compare_schemas()