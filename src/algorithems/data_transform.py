from datetime import datetime
from decimal import Decimal
from pandas import DataFrame

from models.math import Extremum
from utils.math_utils import D


def get_change_percentage(a: Decimal, b: Decimal) -> Decimal:
    return (a / b) - 1


def _get_extremums(df: DataFrame, start_point: Extremum) -> list[Extremum]:
    if df.empty:
        return []
    extremums: list[Extremum] = [start_point]
    for _, row in df.iterrows():
        curr_datetime: datetime = row.name.to_pydatetime()  # type: ignore
        if row["low"] < start_point.value and row["low"] < extremums[-1].value:
            if extremums[-1].value < start_point.value:
                extremums[-1] = Extremum(value=row["low"], datetime=curr_datetime)
            else:
                extremums.append(Extremum(value=row["low"], datetime=curr_datetime))

        if row["high"] > start_point.value and row["high"] > extremums[-1].value:
            if extremums[-1].value > start_point.value:
                extremums[-1] = Extremum(value=row["high"], datetime=curr_datetime)
            else:
                extremums.append(Extremum(value=row["high"], datetime=curr_datetime))

    last = Extremum(value=df.iloc[-1]["close"], datetime=df.iloc[-1].name.to_pydatetime())  # type: ignore
    extremums.append(last)
    extremums = [
        Extremum(
            value=get_change_percentage(extremum.value, start_point.value),
            datetime=extremum.datetime,
        )
        for extremum in extremums[1:]
    ]

    return extremums


def get_extremums(df: DataFrame) -> list[Extremum]:
    starting_index = 0
    original_price = D(df.iloc[starting_index]["close"])
    original_datetime = df.iloc[starting_index].name.to_pydatetime()  # type: ignore
    sliced_df = df.iloc[starting_index + 1 :]
    sliced_df.reset_index()

    extremums = _get_extremums(
        sliced_df, Extremum(value=original_price, datetime=original_datetime)
    )

    return extremums
