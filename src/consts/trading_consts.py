from datetime import datetime
import arrow

STOP_LOSS = 0.015
TARGET_PROFIT = 0.05


def get_volume_analysis_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=10, minute=0, second=0)


def get_analysis_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=9, minute=35, second=0)


def get_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=11, minute=0, second=0)


def get_end_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=15, minute=0, second=0)


CLOSE_GAP_MULTIPLIER_THRESHOLD = 6

EXTREMUM_DIFF_THRESHOLD = 0.5

# enter_trade_datetime = datetime()
