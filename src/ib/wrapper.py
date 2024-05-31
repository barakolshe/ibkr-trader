from decimal import Decimal
from queue import Queue
from re import S
import time
from typing import Any, Optional
import arrow
from ibapi.contract import Contract
from pandas import DataFrame
import os
import pandas as pd
import requests  # type: ignore
from datetime import datetime

from consts.time_consts import (
    ALPACA_TIME_FORMAT,
    MINUTES_FROM_START,
    SAFETY_DAY_GAP,
    TIMEZONE,
)
from consts.trading_consts import MAX_CASH_VALUE
from ib.app import IBapi  # type: ignore
from models.evaluation import Evaluation
from utils.math_utils import D
from logger.logger import logger


def cut_relevant_df(
    df: DataFrame, start_date: datetime, end_date: datetime
) -> Optional[DataFrame]:
    start_of_day = arrow.get(start_date).replace(hour=0, minute=0, second=0).datetime
    relevant_datetime: Optional[datetime] = None

    today_ticks = df[(df.index >= start_of_day)]
    next_day_ticks = df[(df.index >= arrow.get(start_of_day).shift(days=1).datetime)]

    if today_ticks.empty:
        return None
    first_of_day = df[(df.index >= start_of_day)].index[0]
    last_of_day = today_ticks.index[-1]

    if first_of_day > start_date:
        relevant_datetime = first_of_day
        if relevant_datetime is None:
            return None
        end_date = (
            arrow.get(relevant_datetime).shift(minutes=MINUTES_FROM_START).datetime
        )

    elif last_of_day < end_date:
        relevant_datetime = arrow.get(
            today_ticks[(today_ticks.index <= start_date)].index[-1]
        ).datetime
        shift = MINUTES_FROM_START - (end_date - relevant_datetime).seconds // 60
        if not next_day_ticks.empty:
            first_next_day = next_day_ticks.index[0]
            end_date = arrow.get(first_next_day).shift(minutes=shift).datetime

    else:
        relevant_datetime = start_date
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

    df = df[
        (df.index >= relevant_datetime) & (df.index <= end_date)  # type: ignore
    ]  # type: ignore

    return df


def get_historical_data_from_file(
    evaluation: Evaluation,
    start_date: datetime,
    end_date: datetime,
) -> Optional[DataFrame]:
    df = evaluation.load_df_from_csv()
    if df is None:
        raise ValueError("Error loading historical data from file")
    return cut_relevant_df(df, start_date, end_date)


def get_historical_data(
    app: IBapi,
    evaluation: Evaluation,
    response_queue: Queue[Any],
    id: Optional[int] = None,
) -> Optional[DataFrame]:
    start_date = arrow.get(evaluation.timestamp, TIMEZONE).shift(minutes=2)
    end_date = start_date.shift(minutes=MINUTES_FROM_START)
    if evaluation.does_csv_file_exist():
        if evaluation.is_stock_known_invalid():
            return None
        # if evaluation.should_load_from_file(start_date.datetime, end_date.datetime):
        #     return get_historical_data_from_file(
        #         evaluation, start_date.datetime, end_date.datetime
        #     )
    df = get_stock_response(evaluation, start_date, end_date)
    if df is None:
        return None

    return cut_relevant_df(df, start_date.datetime, end_date.datetime)


def get_stock_response(
    evaluation: Evaluation, start_date: arrow.Arrow, end_date: arrow.Arrow
) -> Optional[DataFrame]:
    for _ in range(2):
        start_date = start_date.shift(days=-1)
        end_date = end_date.shift(days=1)
        try:
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
            logger.error("Error getting stock response: %s", exc_info=True)
            pass
        finally:
            time.sleep(5)
    evaluation.save_invalid_stock()
    return None


def get_account_usd(app: IBapi, response_queue: Queue[Any]) -> Decimal:
    app.reqAccountSummary(app.nextValidOrderId, "All", "$LEDGER")
    usd: Decimal = D("-1")
    response: Any = ""
    while response is not None:
        try:
            response = response_queue.get(timeout=15)
        except:
            break
        if response is None:
            break
        if response[0] == "CashBalance":
            usd = D(response[1])

    if usd == -1:
        raise ValueError("Error getting account USD")
    return usd.min(MAX_CASH_VALUE)


def get_current_stock_price(
    app: IBapi, symbol: str, exchange: str, response_queue: Queue[Any]
) -> Optional[Decimal]:
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = "USD"
    app.reqMktData(app.nextValidOrderId, contract, "", True, False, [])
    try:
        value: Decimal = D(response_queue.get(timeout=10))
    except:
        return None
    return value


def get_contract(symbol: str, exchange: str) -> Contract:
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = "USD"
    return contract
