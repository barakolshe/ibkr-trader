from decimal import Decimal
import os
from queue import Queue
from random import randint
from threading import Thread
import time
from typing import Any, Optional
import arrow
from numpy import average, median
from pandas import DataFrame
import pandas as pd
from pydantic import BaseModel, ConfigDict
from consts.time_consts import TIMEZONE
from consts.trading_consts import (
    CHECK_PEAKS,
    CHOSEN_STOCKS_AMOUNT,
    CLOSE_GAP_MULTIPLIER_THRESHOLD,
    MINIMUM_SHARE_PRICE,
    MINIMUM_VOLUME,
    MINIMUM_VOLUME_MULTIPLIER,
    PEAK_HIGHEST,
    PEAK_PRICE_THRESHOLD,
    PREVIOUS_DAY_CLOSE_COMPARISON,
    STOP_LOSS,
    TARGET_PROFIT,
    get_analysis_start_datetime,
    get_end_datetime,
    get_start_datetime,
    get_volume_analysis_start_datetime,
)
from ibapi.contract import Contract

from interactive_api.app import IBapi, OrderStatus, OrderType
from interactive_api.ibwrapper import IBWrapper
from models.evaluation import Evaluation
from logger.logger import logger, log_important
from datetime import timedelta, datetime
from interactive_api.app import Order
from utils.math_utils import D


def interpolate_volume(volume: float, min_volume: int, max_volume: int) -> float:
    min_volume = max(min_volume, MINIMUM_VOLUME)
    if volume <= min_volume:
        return 0
    elif volume >= max_volume:
        return 1
    else:
        return (volume - min_volume) / (max_volume - min_volume)


def get_empty_df() -> DataFrame:
    empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume", "wap"])
    empty_df.index = pd.to_datetime(empty_df.index)

    return empty_df


class DataManager(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    is_testing: bool = False

    historic_queue: Optional[Queue[Any]] = None
    live_queue: Optional[Queue[Any]] = None
    symbol: str
    min_tick: Decimal

    initial_order: Optional[Order] = None
    limit_price_order: Optional[Order] = None
    stop_price_order: Optional[Order] = None
    market_order: Optional[Order] = None

    score: Optional[float] = 0
    close_gap: Optional[float] = 0
    average_volume: Optional[float] = None
    absolute_gap: Optional[float] = 0
    peak_price_gap: Optional[float] = None
    is_in_position: bool = False
    did_leave_position: bool = False
    position_size: Optional[int] = None
    yesterday_close: Optional[float] = None

    realdata: DataFrame = get_empty_df()

    data1: DataFrame = get_empty_df()

    def resample_datas(self) -> None:
        if self.is_testing:
            self.data1 = self.realdata
        else:
            self.data1 = self.resample_data(1)

    def resample_data(self, minutes: int) -> DataFrame:
        df = self.realdata.resample(f"{minutes}min").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "wap": "mean",
            }
        )
        if not self.is_testing:
            df = complete_missing_minutes(df, f"{minutes}min")
        return df

    @property
    def data5(self) -> DataFrame:
        df = self.realdata.resample("5min").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "wap": "mean",
            }
        )
        if not self.is_testing:
            df = complete_missing_minutes(df, "5min")
        return df

    is_finished: bool = False


def complete_missing_minutes(df: DataFrame, freq: str) -> DataFrame:
    complete_index = pd.date_range(
        start=df.index[0],
        end=df.index[-1],
        freq=freq,
    )

    # Reindex the dataframe to the complete datetime index
    df = df.reindex(complete_index)

    # Forward fill the OHLC values with the last known 'Close' price
    df["close"] = df["close"].infer_objects().ffill()
    df["open"] = df["open"].infer_objects().fillna(df["close"])
    df["high"] = df["high"].infer_objects().fillna(df["close"])
    df["low"] = df["low"].infer_objects().fillna(df["close"])

    # Set missing 'Volume' to 0
    df["volume"] = df["volume"].infer_objects().fillna(0)

    # Calculate VWAP for the filled rows
    df["vwap"] = (
        df["high"] + df["low"] + df["close"]
    ) / 3  # Simple example for VWAP calculation

    return df


class BaseStrategy:
    app: IBapi
    ib_app_thread: Thread
    ibwrapper: IBWrapper
    is_testing: bool
    cash: float
    fake_cash: Optional[float] = None

    today: datetime
    data_ready: bool
    data_managers: list[DataManager]

    def __init__(
        self,
        today: datetime,
        is_testing: bool = False,
        initial_cash: Optional[float] = None,
    ) -> None:
        self.app = IBapi()
        self.app.connect("127.0.0.1", 4002, 37)
        self.ib_app_thread = Thread(target=self.app.run, daemon=True)
        self.ib_app_thread.start()
        self.today = today
        self.ibwrapper = IBWrapper(self.app)
        self.is_testing = is_testing
        self.data_managers = []
        self.data_ready = False
        time.sleep(2)
        if not initial_cash:
            self.cash = self.get_cash()
            self.fake_cash = None
        else:
            self.cash = initial_cash
            self.fake_cash = initial_cash

    def main_loop(self, evaluations: list[Evaluation]) -> None:
        for evaluation in evaluations:
            min_tick = self.ibwrapper.get_min_tick_blocking(evaluation)
            does_file_exist = os.path.exists(
                f"data/stocks/{evaluation.ticker}-{self.today.date()}.csv"
            )
            logger.info(f"Getting data for {evaluation.ticker}")
            self.data_managers.append(
                DataManager(
                    is_testing=self.is_testing,
                    symbol=evaluation.ticker,
                    historic_queue=(
                        self.ibwrapper.get_historical_data(evaluation, self.today)
                        if not does_file_exist
                        else None
                    ),
                    live_queue=(
                        self.ibwrapper.get_live_data(evaluation)
                        if not self.is_testing
                        else None
                    ),
                    min_tick=min_tick if min_tick is not None else D("0.01"),
                )
            )
        self.iterate_queues()
        if self.fake_cash is not None:
            self.cash = self.fake_cash
        self.app.disconnect()
        self.ib_app_thread.join()

    def get_past_data(self) -> None:
        for data_manager in self.data_managers:
            if data_manager.historic_queue is None:
                data_manager.realdata = pd.read_csv(
                    f"data/stocks/{data_manager.symbol}-{self.today.date()}.csv",
                    index_col=0,
                    parse_dates=True,
                )
                data_manager.is_finished = True
        relevant_data_managers = [
            data_manager
            for data_manager in self.data_managers
            if data_manager.historic_queue is not None
        ]
        while True:
            if all(
                [
                    curr_data_manager.is_finished
                    for curr_data_manager in relevant_data_managers
                ]
            ):
                for data_manager in relevant_data_managers:
                    if data_manager.realdata.empty:
                        continue
                    data_manager.realdata = complete_missing_minutes(
                        data_manager.realdata, "1min"
                    )
                return
            while not all(
                [
                    data_manager.is_finished
                    for data_manager in relevant_data_managers
                    if data_manager.historic_queue is not None
                ]
            ):
                for data_manager in relevant_data_managers:
                    if data_manager.historic_queue is None:
                        raise Exception("Historic queue is None")
                    if data_manager.historic_queue.empty() or data_manager.is_finished:
                        continue

                    while not data_manager.historic_queue.empty():
                        dict_data: Optional[dict[str, Any]] = (
                            data_manager.historic_queue.get()
                        )
                        if dict_data is None:
                            data_manager.is_finished = True
                            break
                        date = dict_data["date"]
                        dict_data.pop("date")
                        data_manager.realdata.loc[date] = dict_data  # type: ignore

    def get_live_data(self) -> None:
        for data_manager in self.data_managers:
            if data_manager.live_queue is None:
                raise Exception("Live queue is None")
            if data_manager.live_queue.empty():
                continue

            while not data_manager.live_queue.empty():
                dict_data: Optional[dict[str, Any]] = data_manager.live_queue.get()
                if dict_data is None:
                    continue
                date = dict_data["date"]
                dict_data.pop("date")
                data_manager.realdata.loc[date] = dict_data  # type: ignore

    def iterate_queues(self) -> None:

        self.get_past_data()
        for data_manager in self.data_managers:
            if data_manager.realdata.empty:
                continue
            if (
                arrow.now(tz=TIMEZONE)
                .replace(hour=0, minute=0, second=0)
                .shift(days=-1)
                .datetime
                > self.today
            ):
                if not os.path.exists(
                    f"data/stocks/{data_manager.symbol}-{self.today.date()}.csv"
                ):
                    data_manager.realdata.to_csv(
                        f"data/stocks/{data_manager.symbol}-{self.today.date()}.csv"
                    )
        if self.is_testing:
            existing_dfs = [
                data_manager.realdata for data_manager in self.data_managers
            ]
            for data_manager in self.data_managers:
                try:
                    filtered_df = data_manager.realdata[
                        data_manager.realdata.index < self.today
                    ]
                    if not filtered_df.empty:
                        data_manager.yesterday_close = filtered_df["close"].iloc[-1]
                except:
                    pass

                empty_df = pd.DataFrame(
                    columns=["open", "high", "low", "close", "volume", "wap"]
                )
                empty_df.index = pd.to_datetime(empty_df.index)
                data_manager.realdata = empty_df

            start_datetime = arrow.get(self.today).replace(hour=9, minute=30).datetime
            end_datetime = arrow.get(self.today).replace(hour=16, minute=0).datetime
            curr_datetime = start_datetime
            while curr_datetime < end_datetime:
                for data_manager, existing_df in zip(self.data_managers, existing_dfs):
                    if curr_datetime in existing_df.index:
                        data_manager.realdata.loc[curr_datetime] = existing_df.loc[  # type: ignore
                            curr_datetime
                        ]
                        data_manager.resample_datas()
                curr_datetime += timedelta(minutes=1)
                if self.get_curr_datetime() is None:
                    continue
                self.trade()
        else:
            while arrow.now(tz=TIMEZONE).hour < 16:
                self.get_live_data()
                for data_manager in self.data_managers:
                    data_manager.resample_datas()
                self.trade()

    def should_enter_position(self, curr_datetime: datetime) -> bool:
        return (
            curr_datetime > get_start_datetime(self.today).shift(minutes=1).datetime
            and not any(
                [data_manager.initial_order for data_manager in self.data_managers]
            )
            and any(
                [data_manager.average_volume for data_manager in self.data_managers]
            )
        )

    def get_curr_datetime(self) -> Optional[datetime]:
        raise NotImplementedError()

    def trade(self) -> None:
        curr_datetime = self.get_curr_datetime()
        if curr_datetime is None:
            logger.info("No data available")
            return

        if any([data_manager.is_in_position for data_manager in self.data_managers]):
            self.check_orders()

        # Checking if time is up for the day
        if curr_datetime >= get_end_datetime(self.today).datetime and all(
            [data_manager.is_in_position for data_manager in self.data_managers]
        ):
            self.check_end_position()
            return

        if self.should_enter_position(curr_datetime):
            self.enter_position()
            return

        for data_manager in self.data_managers:
            if data_manager.data1.empty:
                continue

            if (
                self.should_start_trading(data_manager)
                and data_manager.average_volume is None
            ):
                self.get_stats(data_manager)

            if (
                data_manager.is_in_position
                and not data_manager.did_leave_position
                and CHECK_PEAKS
            ):
                self.check_peaks()

    def should_start_trading(self, data_manager: DataManager) -> bool:
        raise NotImplementedError()

    def get_cash(self) -> float:
        raise NotImplementedError()

    def get_price(self, price: float, precision: Decimal) -> float:
        return float(D(price, precision=precision))

    def get_price_with_deviation(
        self, price: float, order_type: OrderType, precision: Decimal
    ) -> float:
        raise NotImplementedError()

    def get_close_gap_percentage(self, data_manager: DataManager) -> Optional[float]:
        try:
            analysis_index: int = data_manager.data1.index.get_loc(  # type: ignore
                get_analysis_start_datetime(self.today).datetime
            )

            close_gap: float = (
                average(data_manager.data1["close"].iloc[-10:])
                / average(
                    data_manager.data1["open"].iloc[analysis_index : analysis_index + 6]
                )
                - 1
            )
        except:
            logger.info("Error getting close gap difference", exc_info=True)
            return None
        return close_gap

    def get_close_gap_difference(self, data_manager: DataManager) -> Optional[float]:
        try:
            analysis_index: int = data_manager.data1.index.get_loc(  # type: ignore
                get_analysis_start_datetime(self.today).datetime
            )

            close_gap: float = average(
                data_manager.data1["close"].iloc[-10:]
            ) - average(
                data_manager.data1["open"].iloc[analysis_index : analysis_index + 6]
            )
        except:
            logger.info("Error getting close gap difference", exc_info=True)
            return None
        return close_gap

    def get_average_volume(self, data_manager: DataManager) -> float:
        average_volume = float(
            float(
                average(
                    data_manager.data1.loc[
                        get_volume_analysis_start_datetime(self.today).datetime :,  # type: ignore
                        "volume",
                    ],
                )
            )
            * average(
                data_manager.data1.loc[
                    get_volume_analysis_start_datetime(self.today).datetime :, "close"  # type: ignore
                ],
            )
        )
        log_important(
            f"Average volume for {data_manager.symbol}: {average_volume}", "info"
        )
        return average_volume

    def should_trade_stock(self, data_manager: DataManager) -> bool:
        if data_manager.close_gap is None:
            raise Exception("Close gap is None")
        absolute_gap: float = 0
        filtered_df = data_manager.data5.loc[
            get_analysis_start_datetime(self.today).datetime :  # type: ignore
        ].copy()

        close_diffs = filtered_df["close"].diff().abs()
        absolute_gap = float(close_diffs.sum(skipna=True))  # type: ignore

        if absolute_gap > abs(data_manager.close_gap) * CLOSE_GAP_MULTIPLIER_THRESHOLD:
            log_important(
                f"Not trading {data_manager.symbol} because of absolute gap", "info"
            )
            return False

        if absolute_gap == 0:
            return False
        data_manager.absolute_gap = abs(data_manager.close_gap) / absolute_gap
        return True

    def check_end_position(self) -> None:
        for data_manager in self.data_managers:
            if (
                data_manager.did_leave_position
                or data_manager.market_order is not None
                or data_manager.initial_order is None
                or data_manager.initial_order.status not in [OrderStatus.COMPLETED]
                or data_manager.limit_price_order.status in [OrderStatus.COMPLETED]  # type: ignore
                or data_manager.stop_price_order.status in [OrderStatus.COMPLETED]  # type: ignore
                or data_manager.position_size == 0
            ):
                continue
            self.make_end_market_order(data_manager)
            data_manager.did_leave_position = True
        return

    def get_stats(self, data_manager: DataManager) -> None:
        curr_close_price = data_manager.data1["close"].iloc[-1]
        if curr_close_price <= MINIMUM_SHARE_PRICE or (
            PREVIOUS_DAY_CLOSE_COMPARISON
            and data_manager.yesterday_close is not None
            and abs(curr_close_price - data_manager.yesterday_close)
            > 0.05 * data_manager.yesterday_close
        ):
            data_manager.score = 0
            return
        try:
            data_manager.average_volume = self.get_average_volume(data_manager)
        except Exception:
            logger.warning(
                f"Error getting average volume {data_manager.symbol}",
                exc_info=True,
            )
            data_manager.average_volume = 0
        if (
            data_manager.average_volume is None
            or interpolate_volume(
                data_manager.average_volume,
                int(self.cash // (CHOSEN_STOCKS_AMOUNT * MINIMUM_VOLUME_MULTIPLIER)),
                int(self.cash // CHOSEN_STOCKS_AMOUNT),
            )
            == 0
        ):
            log_important("Not trading because average volume is too low", "info")
            data_manager.score = 0
            return
        data_manager.close_gap = self.get_close_gap_difference(data_manager)
        if data_manager.close_gap is None:
            data_manager.score = 0
            data_manager.close_gap = 0
            return

        should_trade_stock = self.should_trade_stock(data_manager)
        if not should_trade_stock:
            data_manager.score = 0
        else:
            if data_manager.absolute_gap is None:
                raise Exception("Absolute gap is None")
            close_gap_percentage = self.get_close_gap_percentage(data_manager)
            if close_gap_percentage is None:
                data_manager.score = 0
                return
            data_manager.score = (
                abs(close_gap_percentage)
                * data_manager.absolute_gap
                * interpolate_volume(
                    data_manager.average_volume,
                    int(
                        self.cash // (CHOSEN_STOCKS_AMOUNT * MINIMUM_VOLUME_MULTIPLIER)
                    ),
                    int(self.cash // CHOSEN_STOCKS_AMOUNT),
                )
                * 100
            )

            log_important(
                f"Score for {data_manager.symbol}: {data_manager.score:.3f}", "info"
            )

    def enter_position(self) -> None:
        # Entering position with stocks with highest scores
        filtered_scores: list[DataManager] = []
        for data_manager in self.data_managers:
            if data_manager.score is not None and data_manager.score > 0:
                filtered_scores.append(data_manager)
        sorted_scores: list[DataManager] = sorted(
            filtered_scores, key=lambda x: x.score, reverse=True  # type: ignore
        )[0:CHOSEN_STOCKS_AMOUNT]
        sorted_scores.reverse()
        for index, data_manager in enumerate(sorted_scores):
            curr_datetime = data_manager.realdata.index[-1]
            if (
                not (
                    get_start_datetime(self.today).shift(minutes=-1).datetime
                    <= curr_datetime
                    < get_start_datetime(self.today).shift(minutes=30).datetime
                )
                or data_manager.is_in_position
            ):
                continue

            if data_manager.average_volume is None:
                raise Exception("Average volume is None")
            size = self.get_size(
                data_manager.realdata["close"].iloc[-1],
                data_manager.average_volume,
                self.cash,
                len(sorted_scores) - index,
            )
            if data_manager.close_gap is None:
                continue
            data_manager.position_size = size
            if data_manager.close_gap > D("0"):
                logger.info(
                    f"Buying {data_manager.symbol} for {data_manager.realdata['close'].iloc[-1]} {data_manager.realdata.index[-1]}, size: {size}"
                )
                self.cash -= size * data_manager.realdata["close"].iloc[-1]
                (
                    data_manager.initial_order,
                    data_manager.limit_price_order,
                    data_manager.stop_price_order,
                ) = self.place_bracket_order(
                    data_manager,
                    action=OrderType.BUY,
                    quantity=size,
                    price_limit=data_manager.realdata["close"].iloc[-1],
                    take_profit_limit_price=data_manager.realdata["close"].iloc[-1]
                    * (1 + TARGET_PROFIT),
                    stop_loss_price=data_manager.realdata["close"].iloc[-1]
                    * (1 - STOP_LOSS),
                    stop_loss_limit_price=data_manager.realdata["close"].iloc[-1]
                    * (1 - STOP_LOSS),
                    contract=self.ibwrapper.get_contract(data_manager.symbol),
                    parent_valid=data_manager.realdata.index[-1]
                    + timedelta(minutes=30),
                    children_valid=get_end_datetime(self.today)
                    .shift(minutes=-30)
                    .replace(hour=12, minute=43, second=0)
                    .datetime,
                )
            else:
                logger.info(
                    f"Selling {data_manager.symbol} for {data_manager.realdata['close'].iloc[-1]} {data_manager.realdata.index[-1]}, size: {size}"
                )
                self.cash -= size * data_manager.realdata["close"].iloc[-1]
                (
                    data_manager.initial_order,
                    data_manager.limit_price_order,
                    data_manager.stop_price_order,
                ) = self.place_bracket_order(
                    data_manager,
                    action=OrderType.SELL,
                    quantity=size,
                    price_limit=data_manager.realdata["close"].iloc[-1],
                    take_profit_limit_price=data_manager.realdata["close"].iloc[-1]
                    * (1 - TARGET_PROFIT),
                    stop_loss_price=data_manager.realdata["close"].iloc[-1]
                    * (1 + STOP_LOSS),
                    stop_loss_limit_price=data_manager.realdata["close"].iloc[-1]
                    * (1 + STOP_LOSS),
                    contract=self.ibwrapper.get_contract(data_manager.symbol),
                    parent_valid=data_manager.realdata.index[-1]
                    + timedelta(minutes=30),
                    children_valid=get_end_datetime(self.today)
                    .shift(minutes=-30)
                    .replace(hour=12, minute=43, second=0)
                    .datetime,
                )

        for data_manager in self.data_managers:
            data_manager.is_in_position = True

    def check_peaks(self) -> None:
        for data_manager in self.data_managers:
            if (
                not data_manager.initial_order
                or not data_manager.initial_order.status == OrderStatus.COMPLETED
                or data_manager.did_leave_position
            ):
                continue
            if data_manager.close_gap is not None and data_manager.close_gap > 0:
                if (
                    data_manager.realdata["close"].iloc[-1]
                    > (1 + PEAK_HIGHEST) * data_manager.initial_order.price
                ):
                    if (
                        not data_manager.peak_price_gap
                        or data_manager.peak_price_gap
                        > (
                            data_manager.realdata["close"].iloc[-1]
                            / data_manager.initial_order.price
                        )
                        - 1
                    ):
                        data_manager.peak_price_gap = (
                            data_manager.realdata["close"].iloc[-1]
                            / data_manager.initial_order.price
                        ) - 1
                if (
                    data_manager.peak_price_gap is not None
                    and (
                        data_manager.realdata["close"].iloc[-1]
                        / data_manager.initial_order.price
                    )
                    - 1
                    < PEAK_PRICE_THRESHOLD * data_manager.peak_price_gap
                ):
                    logger.info(
                        f"Leaving position because of peaks {data_manager.symbol} {data_manager.realdata.index[-1]}"
                    )
                    self.make_end_market_order(data_manager)
                    data_manager.did_leave_position = True
            else:
                if (
                    data_manager.realdata["close"].iloc[-1]
                    < (1 - PEAK_HIGHEST) * data_manager.initial_order.price
                ):
                    if (
                        not data_manager.peak_price_gap
                        or data_manager.peak_price_gap
                        > (
                            data_manager.initial_order.price
                            / data_manager.realdata["close"].iloc[-1]
                        )
                        - 1
                    ):
                        data_manager.peak_price_gap = (
                            data_manager.initial_order.price
                            / data_manager.realdata["close"].iloc[-1]
                        ) - 1
                if (
                    data_manager.peak_price_gap is not None
                    and (
                        data_manager.initial_order.price
                        / data_manager.realdata["close"].iloc[-1]
                    )
                    - 1
                    < PEAK_PRICE_THRESHOLD * data_manager.peak_price_gap
                ):
                    logger.info(
                        f"Leaving position because of peaks {data_manager.symbol} {data_manager.realdata.index[-1]}"
                    )
                    self.make_end_market_order(data_manager)
                    data_manager.did_leave_position = True

    def get_size(
        self, price: float, average_volume: float, cash: float, divider: int
    ) -> int:
        raise NotImplementedError()

    def place_bracket_order(
        self,
        data_manager: DataManager,
        action: OrderType,
        quantity: int,
        price_limit: float,
        take_profit_limit_price: float,
        stop_loss_price: float,
        stop_loss_limit_price: float,
        parent_valid: datetime,
        children_valid: datetime,
        contract: Contract,
    ) -> tuple[Order, Order, Order]:
        raise NotImplementedError()

    def check_orders(self) -> None:
        raise NotImplementedError()

    def make_end_market_order(self, data_manager: DataManager) -> None:
        raise NotImplementedError()


class TestStrategy(BaseStrategy):

    def get_curr_datetime(self) -> Optional[datetime]:
        datetimes: list[datetime] = []
        for data_manager in self.data_managers:
            try:
                datetimes.append(data_manager.realdata.index[-1])
            except:
                continue
        if len(datetimes) == 0:
            return None
        curr_datetime = max(datetimes)
        return curr_datetime

    def should_start_trading(self, data_manager: DataManager) -> bool:
        curr_datetime: datetime = data_manager.realdata.index[-1]
        return (
            get_start_datetime(self.today).shift(minutes=-1).datetime
            <= curr_datetime
            < get_start_datetime(self.today).shift(minutes=30).datetime
        )

    def get_size(
        self, price: float, average_volume: float, cash: float, divider: int
    ) -> int:
        size = min(
            int(average_volume),
            int(cash * 0.99 // price // divider),
        )
        return size

    def get_cash(self) -> float:
        if self.fake_cash is None:
            raise Exception("Fake cash is None")
        return self.fake_cash

    def place_bracket_order(
        self,
        data_manager: DataManager,
        action: OrderType,
        quantity: int,
        price_limit: float,
        take_profit_limit_price: float,
        stop_loss_price: float,
        stop_loss_limit_price: float,
        parent_valid: datetime,
        children_valid: datetime,
        contract: Contract,
    ) -> tuple[Order, Order, Order]:

        orders = (
            Order(
                id=randint(0, 1000000),
                queue=Queue[Any](),
                status=OrderStatus.COMPLETED,
                order_type=action,
                price=float(
                    average(
                        [
                            price_limit,
                            self.get_price_with_deviation(
                                price_limit, action, precision=data_manager.min_tick
                            ),
                        ]
                    )
                ),
                quantity=quantity,
            ),
            Order(
                id=randint(0, 1000000),
                queue=Queue[Any](),
                status=OrderStatus.SENT,
                order_type=(
                    OrderType.BUY if action == OrderType.SELL else OrderType.SELL
                ),
                price=self.get_price(
                    take_profit_limit_price, precision=data_manager.min_tick
                ),
                quantity=quantity,
            ),
            Order(
                id=randint(0, 1000000),
                queue=Queue[Any](),
                status=OrderStatus.SENT,
                order_type=(
                    OrderType.BUY if action == OrderType.SELL else OrderType.SELL
                ),
                price=self.get_price(
                    stop_loss_limit_price, precision=data_manager.min_tick
                ),
                quantity=quantity,
            ),
        )

        if not self.fake_cash:
            raise Exception("Fake cash is None")

        if action == OrderType.BUY:
            self.fake_cash -= (
                float(
                    average(
                        [
                            price_limit,
                            self.get_price_with_deviation(
                                price_limit, action, precision=data_manager.min_tick
                            ),
                        ]
                    )
                )
                * quantity
            )
        else:
            self.fake_cash += (
                float(
                    average(
                        [
                            price_limit,
                            self.get_price_with_deviation(
                                price_limit, action, precision=data_manager.min_tick
                            ),
                        ]
                    )
                )
                * quantity
            )

        return orders

    def check_orders(self) -> None:
        for data_manager in self.data_managers:
            if (
                data_manager.initial_order is not None
                and data_manager.limit_price_order is not None
                and data_manager.limit_price_order.status is not OrderStatus.COMPLETED
                and data_manager.stop_price_order is not None
                and data_manager.stop_price_order.status is not OrderStatus.COMPLETED
                and data_manager.market_order is None
                and data_manager.position_size is not None
                and data_manager.position_size != 0
            ):
                shares = int(
                    min(
                        data_manager.position_size,
                        data_manager.realdata["volume"].iloc[-1],
                    )
                )
                if data_manager.initial_order.order_type == OrderType.BUY:
                    if (
                        data_manager.realdata["close"].iloc[-1]
                        >= data_manager.limit_price_order.price
                    ):
                        self.fake_cash += (
                            data_manager.realdata["close"].iloc[-1] * shares
                        )

                        data_manager.position_size -= shares
                        if data_manager.position_size == 0:
                            logger.info(
                                f"PROFIT LIMIT: Selling {data_manager.symbol} {data_manager.realdata['close'].iloc[-1]} {data_manager.realdata.index[-1]} value: {(data_manager.realdata['close'].iloc[-1] - data_manager.initial_order.price) * data_manager.initial_order.quantity: .2f}"
                            )
                            data_manager.limit_price_order.status = (
                                OrderStatus.COMPLETED
                            )
                            data_manager.did_leave_position = True
                        else:
                            data_manager.limit_price_order.status = OrderStatus.PARTIAL
                    elif (
                        data_manager.realdata["close"].iloc[-1]
                        <= data_manager.stop_price_order.price
                    ):
                        self.fake_cash += (
                            data_manager.realdata["close"].iloc[-1] * shares
                        )

                        data_manager.position_size -= shares
                        if data_manager.position_size == 0:
                            logger.info(
                                f"STOP LOSS: Selling {data_manager.symbol} {data_manager.realdata['close'].iloc[-1]} {data_manager.realdata.index[-1]} value: {(data_manager.realdata['close'].iloc[-1] - data_manager.initial_order.price) * data_manager.initial_order.quantity: .2f}"
                            )
                            data_manager.limit_price_order.status = (
                                OrderStatus.COMPLETED
                            )
                            data_manager.did_leave_position = True
                        else:
                            data_manager.limit_price_order.status = OrderStatus.PARTIAL
                else:
                    if (
                        data_manager.realdata["close"].iloc[-1]
                        <= data_manager.limit_price_order.price
                    ):
                        self.fake_cash -= (
                            data_manager.realdata["close"].iloc[-1] * shares
                        )
                        data_manager.position_size -= shares
                        if data_manager.position_size == 0:
                            logger.info(
                                f"PROFIT LIMIT: Buying {data_manager.symbol} {data_manager.realdata['close'].iloc[-1]} {data_manager.realdata.index[-1]} value: {(data_manager.initial_order.price - data_manager.realdata['close'].iloc[-1]) * data_manager.initial_order.quantity: .2f}"
                            )
                            data_manager.limit_price_order.status = (
                                OrderStatus.COMPLETED
                            )
                            data_manager.did_leave_position = True
                        else:
                            data_manager.limit_price_order.status = OrderStatus.PARTIAL
                    elif (
                        data_manager.realdata["close"].iloc[-1]
                        >= data_manager.stop_price_order.price
                    ):
                        self.fake_cash -= (
                            data_manager.realdata["close"].iloc[-1] * shares
                        )
                        data_manager.position_size -= shares
                        if data_manager.position_size == 0:
                            logger.info(
                                f"STOP LOSS: Buying {data_manager.symbol} {data_manager.realdata['close'].iloc[-1]} {data_manager.realdata.index[-1]} value: {(data_manager.initial_order.price - data_manager.realdata['close'].iloc[-1]) * data_manager.initial_order.quantity: .2f}"
                            )
                            data_manager.limit_price_order.status = (
                                OrderStatus.COMPLETED
                            )
                            data_manager.did_leave_position = True
                        else:
                            data_manager.limit_price_order.status = OrderStatus.PARTIAL

    def make_end_market_order(self, data_manager: DataManager) -> None:
        if not data_manager.initial_order or not data_manager.position_size:
            raise Exception("Initial order is None")
        data_manager.market_order = Order(
            id=randint(0, 1000000),
            queue=Queue[Any](),
            status=OrderStatus.COMPLETED,
            order_type=(
                OrderType.BUY
                if data_manager.initial_order.order_type == OrderType.SELL
                else OrderType.SELL
            ),
            price=data_manager.realdata["close"].iloc[-1],
            quantity=data_manager.position_size,
        )
        if data_manager.initial_order.order_type == OrderType.BUY:
            logger.info(
                f"MARKET: Selling {data_manager.symbol} for {data_manager.realdata['close'].iloc[-1]} {data_manager.realdata.index[-1]} {data_manager.position_size} value: {(data_manager.realdata['close'].iloc[-1] - data_manager.initial_order.price) * data_manager.initial_order.quantity: .2f}"
            )
            self.fake_cash += (
                data_manager.realdata["close"].iloc[-1] * data_manager.position_size
            )
        else:
            logger.info(
                f"MARKET: Buying {data_manager.symbol} for {data_manager.realdata['close'].iloc[-1]} {data_manager.realdata.index[-1]} {data_manager.position_size} value: {(data_manager.initial_order.price - data_manager.realdata['close'].iloc[-1]) * data_manager.initial_order.quantity: .2f}"
            )
            self.fake_cash -= (
                data_manager.realdata["close"].iloc[-1] * data_manager.position_size
            )
        data_manager.position_size = 0
        data_manager.did_leave_position = True

    def get_price_with_deviation(
        self, price: float, order_type: OrderType, precision: Decimal
    ) -> float:
        if order_type == OrderType.BUY:
            return self.get_price(price * 1.003, precision=precision)
        else:
            return self.get_price(price * 0.997, precision=precision)


class PaperStrategy(BaseStrategy):

    def get_curr_datetime(self) -> Optional[datetime]:
        return arrow.now(tz=TIMEZONE).datetime

    def should_start_trading(self, data_manager: DataManager) -> bool:
        curr_datetime = data_manager.realdata.index[-1]
        return (
            get_start_datetime(self.today).shift(minutes=-1).datetime
            <= curr_datetime
            < get_start_datetime(self.today).shift(minutes=30).datetime
            and get_start_datetime(self.today).shift(minutes=-1).datetime
            <= arrow.now(tz="US/Eastern").datetime
            < get_start_datetime(self.today).shift(minutes=30).datetime
        )

    def get_size(
        self, price: float, average_volume: float, cash: float, divider: int
    ) -> int:
        size = min(
            int(average_volume),
            int(min(cash * 0.99, 50000) // price // divider),
        )
        return size

    def get_cash(self) -> float:
        cash = self.ibwrapper.get_account_usd_blocking()
        after_subtraction = cash - 960000
        if cash < 0:
            return cash
        else:
            return after_subtraction

    def place_bracket_order(
        self,
        data_manager: DataManager,
        action: OrderType,
        quantity: int,
        price_limit: float,
        take_profit_limit_price: float,
        stop_loss_price: float,
        stop_loss_limit_price: float,
        parent_valid: datetime,
        children_valid: datetime,
        contract: Contract,
    ) -> tuple[Order, Order, Order]:
        price_limit = self.get_price_with_deviation(
            price_limit, action, precision=data_manager.min_tick
        )
        take_profit_limit_price = self.get_price(
            take_profit_limit_price, precision=data_manager.min_tick
        )
        stop_loss_price = self.get_price(
            stop_loss_price, precision=data_manager.min_tick
        )
        stop_loss_limit_price = self.get_price(
            stop_loss_limit_price, precision=data_manager.min_tick
        )

        return self.app.place_bracket_order(
            action,
            quantity,
            price_limit,
            take_profit_limit_price,
            stop_loss_price,
            stop_loss_limit_price,
            parent_valid,
            children_valid,
            contract,
        )

    def check_orders(self) -> None:
        for data_manager in self.data_managers:
            if (
                data_manager.initial_order is not None
                and not data_manager.initial_order.queue.empty()
            ):
                data_manager.initial_order = data_manager.initial_order.queue.get()
                if (
                    data_manager.initial_order is not None
                    and data_manager.initial_order.status == OrderStatus.COMPLETED
                ):
                    data_manager.position_size = data_manager.initial_order.quantity
                    logger.info("Initial order filled")
            if (
                data_manager.limit_price_order is not None
                and not data_manager.limit_price_order.queue.empty()
            ):
                data_manager.limit_price_order = (
                    data_manager.limit_price_order.queue.get()
                )
                if (
                    data_manager.limit_price_order is not None
                    and data_manager.limit_price_order.status == OrderStatus.COMPLETED
                ):
                    data_manager.did_leave_position = True
                    data_manager.position_size = 0
                    logger.info("Limit price filled")
            if (
                data_manager.stop_price_order is not None
                and not data_manager.stop_price_order.queue.empty()
            ):
                data_manager.stop_price_order = (
                    data_manager.stop_price_order.queue.get()
                )
                if (
                    data_manager.stop_price_order is not None
                    and data_manager.stop_price_order.status == OrderStatus.COMPLETED
                ):
                    data_manager.did_leave_position = True
                    data_manager.position_size = 0
                    logger.info("Stop price filled")
            if (
                data_manager.market_order is not None
                and not data_manager.market_order.queue.empty()
            ):
                data_manager.market_order = data_manager.market_order.queue.get()
                if (
                    data_manager.market_order is not None
                    and data_manager.market_order.status == OrderStatus.COMPLETED
                ):
                    data_manager.did_leave_position = True
                    data_manager.position_size = 0
                    logger.info("Market order filled")

    def make_end_market_order(self, data_manager: DataManager) -> None:
        if (
            data_manager.initial_order is None
            or data_manager.limit_price_order is None
            or data_manager.stop_price_order is None
            or data_manager.position_size is None
        ):
            raise Exception("Initial order is None")
        logger.info(
            f"Making end market order for {data_manager.symbol} {data_manager.realdata['close'].iloc[-1]}"
        )
        contract = self.ibwrapper.get_contract(data_manager.symbol)
        if data_manager.initial_order.order_type == OrderType.BUY:
            data_manager.market_order = self.app.place_order(
                contract,
                action=OrderType.SELL,
                orderType="LMT",
                totalQuantity=abs(data_manager.position_size),
                lmtPrice=self.get_price_with_deviation(
                    data_manager.realdata["close"].iloc[-1],
                    OrderType.SELL,
                    data_manager.min_tick,
                ),
            )
        else:
            data_manager.market_order = self.app.place_order(
                contract,
                action=OrderType.BUY,
                orderType="LMT",
                totalQuantity=abs(data_manager.position_size),
                lmtPrice=self.get_price_with_deviation(
                    data_manager.realdata["close"].iloc[-1],
                    OrderType.BUY,
                    data_manager.min_tick,
                ),
            )

    def get_price_with_deviation(
        self, price: float, order_type: OrderType, precision: Decimal
    ) -> float:
        if order_type == OrderType.BUY:
            return self.get_price(max(price * 1.003, price + 0.03), precision=precision)
        else:
            return self.get_price(min(price * 0.997, price - 0.03), precision=precision)
