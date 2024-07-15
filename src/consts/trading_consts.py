from datetime import datetime
import arrow


def get_volume_analysis_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=9, minute=45, second=0)


def get_analysis_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=9, minute=35, second=0)


def get_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=11, minute=0, second=0)


def get_end_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=15, minute=0, second=0)


# Important

STOP_LOSS = 0.02
TARGET_PROFIT = 0.04
CHOSEN_STOCKS_AMOUNT = 2
MINIMUM_SHARE_PRICE = 1.5

# Close gap

CLOSE_GAP_MULTIPLIER_THRESHOLD = 10

# Peaks

PEAK_HIGHEST = 0.02

PEAK_PRICE_THRESHOLD = 0.25

CHECK_PEAKS = False

# Volume

MINIMUM_VOLUME_MULTIPLIER = 2

MINIMUM_VOLUME = 10000
