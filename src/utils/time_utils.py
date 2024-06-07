from datetime import datetime

import arrow


def minutes_to_seconds(minutes: int) -> int:
    return minutes * 60


def hours_to_seconds(hours: float) -> float:
    return hours * 60 * 60


def days_to_seconds(days: int) -> int:
    return days * 24 * 60 * 60


def days_to_minutes(days: int) -> int:
    return days * 24 * 60


def get_business_days(start_date: datetime, end_date: datetime) -> int:
    start_date_arrow = arrow.get(start_date)
    end_date_arrow = arrow.get(end_date)

    count = 0

    curr_date = start_date_arrow
    while curr_date < end_date_arrow:
        if curr_date.weekday() <= 4:
            count += 1
        curr_date = curr_date.shift(days=1)

    if count == 0:
        return 1
    return count


def is_between_dates(
    examined_date: datetime, start_date: datetime, end_date: datetime
) -> bool:
    return examined_date >= start_date and examined_date <= end_date
