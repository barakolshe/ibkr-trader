from decimal import Decimal
import math
from pandas import DataFrame

from consts.time_consts import BAR_SIZE_MINUTES, HOURS_FROM_START, SECONDS_FROM_END
from utils.time_utils import hours_to_seconds


def get_change_percentage(a: Decimal, b: Decimal) -> Decimal:
    return (a / b) - 1


def _get_extremums(df: DataFrame, original_price: Decimal) -> list[Decimal]:
    extremums: list[Decimal] = [original_price]
    for _, row in df.iterrows():
        if row["low"] < original_price and row["low"] < extremums[-1]:
            if extremums[-1] < original_price:
                extremums[-1] = row["low"]
            else:
                extremums.append(row["low"])

        if row["high"] > original_price and row["high"] > extremums[-1]:
            if extremums[-1] > original_price:
                extremums[-1] = row["high"]
            else:
                extremums.append(row["high"])

    last = df.iloc[-1]["close"]
    extremums.append(last)
    extremums = [
        get_change_percentage(extremum, original_price) for extremum in extremums
    ]
    return extremums[1:]


def get_extremums(df: DataFrame) -> list[Decimal]:
    starting_index = math.floor(
        (SECONDS_FROM_END - hours_to_seconds(HOURS_FROM_START))
        / (BAR_SIZE_MINUTES * 60)
    )
    original_price = df.iloc[starting_index]["close"]
    sliced_df = df.iloc[starting_index + 1 :]
    sliced_df.reset_index()

    extremums = _get_extremums(sliced_df, original_price)

    return extremums
