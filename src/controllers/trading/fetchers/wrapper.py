from queue import Queue
from re import S
import time
from typing import Any, Optional
import arrow
from pandas import DataFrame
import os
import pandas as pd
import requests  # type: ignore
from datetime import datetime

from consts.time_consts import (
    ALPACA_TIME_FORMAT,
    TIMEZONE,
)
from models.evaluation import Evaluation
from logger.logger import logger


def cut_relevant_df(
    df: DataFrame, start_date: datetime, end_date: datetime, time_limit: int
) -> Optional[DataFrame]:
    start_of_day = arrow.get(start_date).replace(hour=0, minute=0, second=0).datetime

    today_ticks = df[(df.index >= start_of_day)]
    next_day_ticks = df[(df.index >= arrow.get(start_of_day).shift(days=1).datetime)]

    if today_ticks.empty:
        return None
    first_of_day = df[(df.index >= start_of_day)].index[0]
    last_of_day = today_ticks.index[-1]

    if first_of_day > start_date:
        start_date = first_of_day
        if start_date is None:
            return None
        end_date = arrow.get(start_date).shift(minutes=time_limit).datetime

    elif last_of_day < end_date:
        if last_of_day <= start_date:
            if not next_day_ticks.empty:
                first_next_day = next_day_ticks.index[0]
                start_date = first_next_day
                end_date = arrow.get(first_next_day).shift(minutes=time_limit).datetime
        else:
            start_date = arrow.get(
                today_ticks[(today_ticks.index <= start_date)].index[-1]
            ).datetime
            shift = time_limit - (end_date - start_date).seconds // 60
            if not next_day_ticks.empty:
                first_next_day = next_day_ticks.index[0]
                end_date = arrow.get(first_next_day).shift(minutes=shift).datetime

    else:
        if start_date not in df.index:
            current_price = today_ticks[(today_ticks.index <= start_date)].iloc[-1]
            new_df = DataFrame(
                [current_price],
                index=pd.DatetimeIndex(
                    [arrow.get(start_date).to(TIMEZONE).datetime], tz=TIMEZONE
                ),
            )
            df = pd.concat([new_df, df])
            df.index = pd.to_datetime(df.index, utc=True).map(
                lambda x: x.tz_convert(TIMEZONE)
            )

    df = df[(df.index >= start_date) & (df.index <= end_date)]

    first_of_df = arrow.get(df.index[0])

    for index, row in df.iterrows():
        if arrow.get(index) < first_of_df.shift(minutes=10) and row.volume >= 2000:  # type: ignore
            return df

    return None


def get_historical_data_from_file(
    evaluation: Evaluation,
    csv_file_path: str,
    start_date: datetime,
    end_date: datetime,
    time_limit: int,
) -> Optional[DataFrame]:
    df = evaluation.load_df_from_csv(csv_file_path)
    if df is None:
        raise ValueError("Error loading historical data from file")
    return cut_relevant_df(df, start_date, end_date, time_limit)


def get_historical_data(
    evaluation: Evaluation,
    time_limit: int,
) -> Optional[DataFrame]:
    start_date = arrow.get(evaluation.timestamp, TIMEZONE)
    end_date = start_date.shift(minutes=time_limit)
    if evaluation.does_csv_file_exist():
        if evaluation.is_stock_known_invalid() or evaluation.symbol == "":
            return None
        matching_file = evaluation.get_matching_csv(
            start_date.datetime, end_date.datetime
        )
        if matching_file:
            return get_historical_data_from_file(
                evaluation,
                matching_file,
                start_date.datetime,
                end_date.datetime,
                time_limit,
            )
    df = get_stock_response(evaluation, start_date, end_date)
    if df is None:
        return None

    return cut_relevant_df(df, start_date.datetime, end_date.datetime, time_limit)


def complete_missing_values(df: DataFrame) -> DataFrame:
    # Ensure the index is datetime and sorted
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Create a date range from the first to the last timestamp at minute frequency
    full_range = pd.date_range(
        start=df.index[0].floor("T"), end=df.index[-1].ceil("T"), freq="T"
    )

    # Reindex the dataframe to this full range, filling missing rows with NaNs
    df_full = df.reindex(full_range)

    # Optionally forward-fill or backward-fill the missing values
    df_full.ffill(
        inplace=True
    )  # You can also use .bfill() or .fillna(method='ffill') based on the requirement

    return df_full


def get_stock_response(
    evaluation: Evaluation, start_date: arrow.Arrow, end_date: arrow.Arrow
) -> Optional[DataFrame]:
    for _ in range(2):
        start_date = start_date.shift(days=-1)
        end_date = min(end_date.shift(days=1), arrow.now(tz=TIMEZONE).shift(hours=-2))
        try:
            data = None
            time.sleep(5)
            response = requests.get(
                "https://data.alpaca.markets/v2/stocks/bars",
                params={
                    "symbols": evaluation.symbol,
                    "start": start_date.format(ALPACA_TIME_FORMAT),
                    "end": end_date.format(ALPACA_TIME_FORMAT),
                    "timeframe": "1Min",
                },
                headers={
                    "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                    "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"],
                },
            )
            if response.status_code != 200:
                logger.error(
                    f"Error getting stock response {response.text if response.text else ''}."
                )
                raise Exception("Error getting stock response")
            data = response.json()
            # Load the data into a DataFrame
            df = DataFrame(data["bars"][evaluation.symbol])

            # Convert the 't' column to datetime
            df["t"] = df["t"].map(lambda d: arrow.get(d).to(TIMEZONE).datetime)

            # Set the 't' column as the index
            df.set_index("t", inplace=True)
            df.rename(
                columns={
                    "c": "close",
                    "h": "high",
                    "l": "low",
                    "n": "number",
                    "o": "open",
                    "v": "volume",
                    "vw": "vwap",
                },
                inplace=True,
            )
            evaluation.save_to_csv(df, start_date.datetime, end_date.datetime)
            return df
        except Exception as e:
            logger.error(
                f"Error getting stock response {data if data else ''}.", exc_info=True
            )
            pass
    evaluation.save_invalid_stock()
    return None
