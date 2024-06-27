from datetime import datetime
import arrow

STOP_LOSS = 0.015
TARGET_PROFIT = 0.05


def get_start_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=10, minute=20, second=0)


def get_end_datetime(date: datetime | arrow.Arrow) -> arrow.Arrow:
    return arrow.get(date).replace(hour=15, minute=0, second=0)


# enter_trade_datetime = datetime()
