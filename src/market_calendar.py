import datetime

# TODO: This hardcoded list is a form of technical debt.
# A future enhancement should replace this with a dynamic function,
# e.g., `_fetch_holidays_from_nse()`, that scrapes the official
# NSE website or uses a reliable financial calendar API to get the
# holiday list for the current year. This would make the system
# self-updating and more robust.
# Hardcoded NSE market holidays for 2025
# Source: Various financial news websites, confirmed against multiple sources.
NSE_HOLIDAYS_2025 = [
    datetime.date(2025, 2, 26),  # Maha Shivratri
    datetime.date(2025, 3, 14),  # Holi
    datetime.date(2025, 3, 31),  # Eid-Ul-Fitr (Ramadan Eid)
    datetime.date(2025, 4, 10),  # Shri Mahavir Jayanti
    datetime.date(2025, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti
    datetime.date(2025, 4, 18),  # Good Friday
    datetime.date(2025, 5, 1),   # Maharashtra Day / Labour Day
    datetime.date(2025, 8, 15),  # Independence Day
    datetime.date(2025, 8, 27),  # Ganesh Chaturthi
    datetime.date(2025, 10, 2),  # Mahatma Gandhi Jayanti / Dussehra
    datetime.date(2025, 10, 21), # Diwali (Laxmi Pujan) - Muhurat Trading
    datetime.date(2025, 10, 22), # Diwali (Bali Pratipada)
    datetime.date(2025, 11, 5),  # Prakash Gurpurb Sri Guru Nanak Dev
    datetime.date(2025, 12, 25), # Christmas
]

# Standard NSE market timings
NSE_MARKET_OPEN_TIME = datetime.time(9, 15, 0) # 9:15 AM
NSE_MARKET_CLOSE_TIME = datetime.time(15, 30, 0) # 3:30 PM

def get_trading_holidays(year: int) -> list[datetime.date]:
    """
    Returns a list of trading holidays for a given year.
    Currently hardcoded for 2025.
    """
    # This function can be enhanced later to fetch holidays dynamically.
    return NSE_HOLIDAYS_2025 if year == 2025 else []

def is_market_working_day(date: datetime.date) -> bool:
    """
    Checks if the given date is an NSE market working day.

    Args:
        date (datetime.date): The date to check.

    Returns:
        bool: True if it's a market working day, False otherwise.
    """
    # Check for weekends
    if date.weekday() >= 5:  # Saturday (5) or Sunday (6)
        return False

    # Check for holidays
    if date in NSE_HOLIDAYS_2025:
        return False

    return True

def get_market_open_time(date: datetime.date) -> datetime.datetime:
    """
    Returns the market open time for a given date.
    Considers standard timings and special trading sessions (not yet implemented).
    """
    # For now, always return standard open time. Special sessions can be added later.
    return datetime.datetime.combine(date, NSE_MARKET_OPEN_TIME)

def get_market_close_time(date: datetime.date) -> datetime.datetime:
    """
    Returns the market close time for a given date.
    Considers standard timings and special trading sessions (not yet implemented).
    """
    # For now, always return standard close time. Special sessions can be added later.
    return datetime.datetime.combine(date, NSE_MARKET_CLOSE_TIME)

if __name__ == "__main__":
    # Example usage
    today = datetime.date.today()
    print(f"Today ({today}) is a market working day: {is_market_working_day(today)}")
    print(f"Market opens today at: {get_market_open_time(today)}")
    print(f"Market closes today at: {get_market_close_time(today)}")

    # Test a weekend
    saturday = datetime.date(2025, 1, 4) # A Saturday in 2025
    print(f"Saturday ({saturday}) is a market working day: {is_market_working_day(saturday)}")

    # Test a holiday
    holi = datetime.date(2025, 3, 14) # Holi in 2025
    print(f"Holi ({holi}) is a market working day: {is_market_working_day(holi)}")

    # Test a normal weekday
    normal_day = datetime.date(2025, 1, 6) # A Monday in 2025
    print(f"Normal Day ({normal_day}) is a market working day: {is_market_working_day(normal_day)}")
