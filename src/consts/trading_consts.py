from datetime import datetime
import arrow


def get_volume_analysis_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=10, minute=0, second=0)


def get_analysis_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=9, minute=35, second=0)


def get_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=13, minute=40, second=0)  # TODO: Revert this


def get_end_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=13, minute=50, second=0)  # TODO: Revert this


STOP_LOSS = 0.02
TARGET_PROFIT = 0.04

CLOSE_GAP_MULTIPLIER_THRESHOLD = 10

CHOSEN_STOCKS_AMOUNT = 2

CHECK_PEAKS = True

PEAK_PRICE_THRESHOLD = 0.25

MINIMUM_SHARE_PRICE = 1.5
