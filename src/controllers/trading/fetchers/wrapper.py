from queue import Queue
from re import S
import time
from typing import Any, Optional
import arrow
from pandas import DataFrame
import os
import pandas as pd
import requests  # type: ignore
import requests_cache
from datetime import datetime


from consts.time_consts import (
    ALPACA_TIME_FORMAT,
    TIMEZONE,
)
from models.evaluation import Evaluation
from logger.logger import logger

session = requests_cache.CachedSession("demo_cache")


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
    time_frame: int,
) -> Optional[DataFrame]:
    start_date = arrow.get(evaluation.timestamp, TIMEZONE)
    end_date = arrow.get(evaluation.timestamp, TIMEZONE).shift(days=1)
    # if evaluation.does_csv_file_exist():
    #     if evaluation.is_stock_known_invalid() or evaluation.symbol == "":
    #         return None
    #     matching_file = evaluation.get_matching_csv(
    #         start_date.datetime, end_date.datetime
    #     )
    #     if matching_file:
    #         return get_historical_data_from_file(
    #             evaluation,
    #             matching_file,
    #             start_date.datetime,
    #             end_date.datetime,
    #             time_limit,
    #         )
    df = get_stock_response(evaluation, start_date, end_date, time_frame)
    if df is None:
        return None
    df = complete_missing_values(df, time_frame)

    return df


def complete_missing_values(df: DataFrame, minute_gap: int = 1) -> DataFrame:
    # Ensure the index is datetime and sorted
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Generate a complete datetime index for all minutes of the day
    start_time = df.index.min().replace(second=0, microsecond=0)
    end_time = df.index.max().replace(second=0, microsecond=0)
    complete_index = pd.date_range(
        start=start_time, end=end_time, freq=f"{minute_gap}min"
    )

    # Reindex the original DataFrame to the complete index
    df_reindexed = df.reindex(complete_index)

    # Forward fill the 'close' column to get the previous row's close price
    # Please fix this
    df_reindexed["close"] = df_reindexed["close"].ffill()

    # Set 'open', 'high', 'low', and 'close' to the forward filled 'close' value
    df_reindexed["open"] = df_reindexed["close"]
    df_reindexed["high"] = df_reindexed["close"]
    df_reindexed["low"] = df_reindexed["close"]

    # Fill missing 'volume' with 0
    df_reindexed["volume"] = df_reindexed["volume"].fillna(0)

    # Define trading hours
    market_open = pd.Timestamp("09:30:00", tz="US/Eastern").time()
    market_close = pd.Timestamp("16:00:00", tz="US/Eastern").time()

    # Assuming the DataFrame index is localized to 'US/Eastern' time zone for filtering
    # df_reindexed.index = df_reindexed.index.tz_localize("UTC").tz_convert("US/Eastern")

    # Filter DataFrame to include only rows within trading hours
    df_trading_hours = df_reindexed.between_time(market_open, market_close)

    return df_trading_hours


def get_stock_response(
    evaluation: Evaluation,
    start_date: arrow.Arrow,
    end_date: arrow.Arrow,
    time_frame: int,
) -> Optional[DataFrame]:
    start_date = arrow.get(
        start_date.datetime.replace(hour=9, minute=30, second=0, tzinfo=None)
    )
    end_date = arrow.get(
        end_date.datetime.replace(hour=16, minute=0, second=0, tzinfo=None)
    )
    try:
        data = None
        response = session.get(
            "https://data.alpaca.markets/v2/stocks/bars",
            params={
                "symbols": evaluation.symbol,
                "start": start_date.format(ALPACA_TIME_FORMAT),
                "end": end_date.format(ALPACA_TIME_FORMAT),
                "timeframe": f"{time_frame}Min",
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
            return None
        data = response.json()
        # Load the data into a DataFrame
        df = DataFrame(data["bars"][evaluation.symbol])
        # df.index = df.index - pd.DateOffset(hours=4)

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
        return df
    except Exception as e:
        logger.error(
            f"Error getting stock response {data if data else ''}.", exc_info=True
        )
        return None
