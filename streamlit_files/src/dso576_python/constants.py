"""Shared constants: the stock universe and the selectable periods.

Every module that needs the ticker list or the periods imports them from here,
so they are defined once.
"""

# The eight companies, in the order used for tables and controls
COMPANIES = {
    'AAPL': 'Apple', 'ADBE': 'Adobe', 'AMZN': 'Amazon', 'GOOGL': 'Alphabet',
    'META': 'Meta', 'MSFT': 'Microsoft', 'NVDA': 'Nvidia', 'TSLA': 'Tesla',
}

# Calendar years present in the pinned data (2024 is December only, 2026 is January-March)
YEARS = (2024, 2025, 2026)

# The period selector: the full range (the default) plus each year
FULL_RANGE = 'full'
PERIODS = (FULL_RANGE,) + YEARS
