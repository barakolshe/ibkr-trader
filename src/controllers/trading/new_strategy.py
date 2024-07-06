from queue import Queue
from threading import Thread
import time
from typing import Any, Optional
import arrow
from numpy import average
from pandas import DataFrame
import pandas as pd
from pydantic import BaseModel, ConfigDict
from consts.trading_consts import (
    CHECK_PEAKS,
    CHOSEN_STOCKS_AMOUNT,
    CLOSE_GAP_MULTIPLIER_THRESHOLD,
    STOP_LOSS,
    TARGET_PROFIT,
    get_analysis_start_datetime,
    get_end_datetime,
    get_start_datetime,
    get_volume_analysis_start_datetime,
)
from interactive_api.app import IBapi, OrderStatus, OrderType
from interactive_api.ibwrapper import IBWrapper
from models.evaluation import Evaluation
from logger.logger import logger, log_important
from datetime import timedelta, datetime
from interactive_api.app import Order
from utils.math_utils import D


def interpolate_volume(
    volume: float, min_volume: int = 10000, max_volume: int = 40000
) -> float:
    if volume <= min_volume:
        return 0
    elif volume >= max_volume:
        return 1
    else:
        return (volume - min_volume) / (max_volume - min_volume)


class DataManager(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    queue: Queue[Any]
    symbol: str

    initial_order: Optional[Order] = None
    limit_price_order: Optional[Order] = None
    stop_price_order: Optional[Order] = None
    market_order: Optional[Order] = None

    score: Optional[float] = 0
    close_gap: Optional[float] = 0
    average_volume: Optional[int] = None
    absolute_gap: Optional[float] = 0
    should_use_rsi: bool = False
    peak_price_gap: Optional[float] = None
    is_in_position: bool = False
    did_leave_position: bool = False
    position_size: Optional[int] = None

    @property
    def position_type(self) -> OrderType:
        if self.close_gap is not None and self.close_gap > 0:
            return OrderType.LONG
        return OrderType.SHORT

    data1: DataFrame

    @property
    def data3(self) -> DataFrame:
        return self.data1.resample("3min").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "wap": "mean",
            }
        )

    @property
    def data5(self) -> DataFrame:
        return self.data1.resample("5min").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "wap": "mean",
            }
        )

    is_finished: bool = False


class NewTrader:
    app: IBapi
    ibwrapper: IBWrapper
    is_testing: bool = False
    cash: float

    today: datetime
    data_ready: bool = False
    data_managers: list[DataManager] = []

    def __init__(self, today: datetime, is_testing: bool = False) -> None:
        self.app = IBapi()
        self.app.connect("127.0.0.1", 4002, 39)
        ib_app_thread = Thread(target=self.app.run, daemon=True)
        ib_app_thread.start()
        self.today = today
        self.ibwrapper = IBWrapper(self.app)
        self.is_testing = is_testing
        time.sleep(2)
        self.cash = self.get_cash()

    def main_loop(self, evaluations: list[Evaluation]) -> None:
        for evaluation in evaluations:
            empty_df = pd.DataFrame(
                columns=["open", "high", "low", "close", "volume", "wap"]
            )
            empty_df.index = pd.to_datetime(empty_df.index)
            self.data_managers.append(
                DataManager(
                    symbol=evaluation.symbol,
                    queue=self.ibwrapper.get_historical_data(evaluation),
                    data1=empty_df,
                )
            )
        self.iterate_queues()

    def get_past_data(self) -> None:
        while True:
            if all(
                [
                    curr_data_manager.is_finished
                    for curr_data_manager in self.data_managers
                ]
            ):
                for data_manager in self.data_managers:
                    data_manager.data1 = self.complete_missing_minutes(
                        data_manager.data1
                    )
                return
            while not all(
                [data_manager.is_finished for data_manager in self.data_managers]
            ):
                for data_manager in self.data_managers:
                    if data_manager.queue.empty() or data_manager.is_finished:
                        continue

                    while not data_manager.queue.empty():
                        dict_data: Optional[dict[str, Any]] = data_manager.queue.get()
                        if dict_data is None:
                            data_manager.is_finished = True
                            break
                        date = dict_data["date"]
                        dict_data.pop("date")
                        data_manager.data1.loc[date] = dict_data  # type: ignore

    def complete_missing_minutes(self, df: DataFrame) -> DataFrame:
        complete_index = pd.date_range(
            start=df.index[0],
            end=df.index[-1],
            freq="1min",
        )

        # Reindex the dataframe to the complete datetime index
        df = df.reindex(complete_index)

        # Forward fill the OHLC values with the last known 'Close' price
        df["close"] = df["close"].fillna(method="ffill")
        df["open"] = df["open"].fillna(df["close"])
        df["high"] = df["high"].fillna(df["close"])
        df["low"] = df["low"].fillna(df["close"])

        # Set missing 'Volume' to 0
        df["volume"] = df["volume"].fillna(0)

        # Calculate VWAP for the filled rows
        df["vwap"] = (
            df["high"] + df["low"] + df["close"]
        ) / 3  # Simple example for VWAP calculation

        return df

    def iterate_queues(self) -> None:

        self.get_past_data()
        if self.is_testing:
            existing_dfs = [data_manager.data1 for data_manager in self.data_managers]
            for data_manager in self.data_managers:
                empty_df = pd.DataFrame(
                    columns=["open", "high", "low", "close", "volume", "wap"]
                )
                empty_df.index = pd.to_datetime(empty_df.index)
                data_manager.data1 = empty_df
            start_datetime = arrow.get(self.today).replace(hour=9, minute=30).datetime
            end_datetime = arrow.get(self.today).replace(hour=16, minute=0).datetime
            curr_datetime = start_datetime
            while curr_datetime < end_datetime:
                for data_manager, existing_df in zip(self.data_managers, existing_dfs):
                    if curr_datetime in existing_df.index:
                        data_manager.data1.loc[curr_datetime] = existing_df.loc[
                            curr_datetime
                        ]
                curr_datetime += timedelta(minutes=1)
                self.trade()

    def trade(self) -> None:
        curr_datetime = self.data_managers[0].data1.index[-1]

        # Checking if time is up for the day
        if curr_datetime >= get_end_datetime(self.today).datetime and all(
            [data_manager.is_in_position for data_manager in self.data_managers]
        ):
            self.check_end_position()
            return

        if all(
            [data_manager.average_volume for data_manager in self.data_managers]
        ) and not any(
            [data_manager.is_in_position for data_manager in self.data_managers]
        ):
            self.enter_position()
            return
        for data_manager in self.data_managers:
            if data_manager.data1.empty:
                continue
            curr_datetime = data_manager.data1.index[-1]

            if (
                get_start_datetime(self.today).shift(minutes=-1).datetime
                <= curr_datetime
                < get_start_datetime(self.today).shift(minutes=30).datetime
                and data_manager.data1["close"].iloc[-1] > 1
                and data_manager.average_volume is None
            ):
                self.get_stats(data_manager)

            if (
                data_manager.is_in_position
                and not data_manager.did_leave_position
                and CHECK_PEAKS
            ):
                self.check_peaks()

    def should_start_trading(self, curr_datetime: datetime) -> bool:
        raise NotImplementedError()

    def get_cash(self) -> float:
        return self.ibwrapper.get_account_usd_blocking(self.app)

    def get_price(self, price: float) -> float:
        raise NotImplementedError()

    def get_price_with_deviation(self, price: float, order_type: OrderType) -> float:
        raise NotImplementedError()

    def get_close_gap_percentage(self, data_manager: DataManager) -> float:
        close_gap: float = (
            data_manager.data1["close"].iloc[-1]
            / data_manager.data1["open"].loc[
                get_analysis_start_datetime(self.today).datetime,
            ]
        ) - 1
        return close_gap

    def get_close_gap_difference(
        self, data_manager: DataManager, datetime: arrow.Arrow
    ) -> float:
        close_gap: float = (
            data_manager.data1["close"].iloc[-1]
            - data_manager.data1["open"].loc[datetime.datetime]
        )
        return close_gap

    def get_average_volume(self, data_manager: DataManager) -> int:
        average_volume = int(
            float(
                average(
                    data_manager.data1.loc[  # type: ignore
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
        absolute_gap = 0
        filtered_df = data_manager.data5.loc[
            get_analysis_start_datetime(self.today).shift(minutes=5).datetime :
        ]

        close_diffs = filtered_df["close"].diff().abs()
        absolute_gap = close_diffs.sum(skipna=True)

        if absolute_gap > abs(data_manager.close_gap) * CLOSE_GAP_MULTIPLIER_THRESHOLD:
            log_important(
                f"Not trading {data_manager.symbol} because of absolute gap", "info"
            )
            return False

        data_manager.absolute_gap = abs(data_manager.close_gap) / absolute_gap
        return True

    def make_end_market_order(self, data_manager: DataManager) -> None:
        if (
            data_manager.initial_order is None
            or data_manager.limit_price_order is None
            or data_manager.stop_price_order is None
            or data_manager.position_size is None
        ):
            raise Exception("Initial order is None")
        logger.info(
            f"Making end market order for {data_manager.symbol} {data_manager.data1['close'].iloc(-1)}"
        )
        self.app.cancelOrder(data_manager.limit_price_order.id)
        self.app.cancelOrder(data_manager.stop_price_order.id)
        contract = self.ibwrapper.get_contract(data_manager.symbol)
        if data_manager.position_type == OrderType.LONG:
            data_manager.market_order = self.app.place_order(
                contract,
                action=OrderType.SHORT,
                orderType="LMT",
                totalQuantity=abs(data_manager.position_size),
                lmtPrice=self.get_price_with_deviation(
                    data_manager.data1["close"].iloc[-1], OrderType.SHORT
                ),
            )
        else:
            data_manager.market_order = self.app.place_order(
                contract,
                action=OrderType.LONG,
                orderType="LMT",
                totalQuantity=abs(data_manager.position_size),
                lmtPrice=self.get_price_with_deviation(
                    data_manager.data1["close"].iloc[-1], OrderType.LONG
                ),
            )

    def check_end_position(self) -> None:
        for data_manager in self.data_managers:
            if (
                data_manager.did_leave_position
                or data_manager.market_order is not None
                or data_manager.initial_order is None
                or data_manager.initial_order.status not in [OrderStatus.COMPLETED]
                or data_manager.limit_price_order.status in [OrderStatus.COMPLETED]  # type: ignore
                or data_manager.stop_price_order.status in [OrderStatus.COMPLETED]  # type: ignore
            ):
                continue
            if data_manager.stop_price_order.status not in [  # type: ignore
                OrderStatus.COMPLETED
            ] and data_manager.stop_price_order.status not in [  # type: ignore
                OrderStatus.COMPLETED
            ]:
                self.make_end_market_order(data_manager)
            data_manager.did_leave_position = True
        return

    def get_stats(self, data_manager: DataManager) -> None:
        try:
            data_manager.average_volume = self.get_average_volume(data_manager)
        except Exception:
            logger.warning(
                f"Error getting average volume {data_manager.symbol}",
                exc_info=True,
            )
            data_manager.average_volume = 0
        if data_manager.average_volume is None or data_manager.average_volume < 10000:
            log_important(
                f"Not trading {data_manager.symbol} because of volume", "info"
            )
            data_manager.is_in_position = True
            return
        data_manager.close_gap = self.get_close_gap_difference(
            data_manager, get_analysis_start_datetime(self.today)
        )
        if data_manager.close_gap > 0:
            should_trade_stock = self.should_trade_stock(data_manager)
            if not should_trade_stock:
                data_manager.is_in_position = True
            else:
                if data_manager.absolute_gap is None:
                    raise Exception("Absolute gap is None")
                data_manager.score = (
                    abs(self.get_close_gap_percentage(data_manager))
                    * data_manager.absolute_gap
                    * interpolate_volume(
                        data_manager.average_volume,
                        10000,
                        int(self.cash // 2),
                    )
                    * 100
                )

                log_important(
                    f"Score for {data_manager.symbol}: {data_manager.score}", "info"
                )
        else:
            should_trade_stock = self.should_trade_stock(data_manager)
            if not should_trade_stock:
                data_manager.is_in_position = True
            else:
                if data_manager.absolute_gap is None:
                    raise Exception("Absolute gap is None")
                data_manager.score = (
                    abs(self.get_close_gap_percentage(data_manager))
                    * data_manager.absolute_gap
                    * interpolate_volume(
                        data_manager.average_volume,
                        10000,
                        int(self.cash // 2),
                    )
                    * 100
                )
                log_important(
                    f"Score for {data_manager.symbol}: {data_manager.score}", "info"
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
        for data_manager in sorted_scores:
            if data_manager.is_in_position:
                continue
            if data_manager.average_volume is None:
                raise Exception("Average volume is None")
            size = self.get_size(
                data_manager.data1["close"].iloc[-1],
                data_manager.average_volume,
                self.cash,
                len(sorted_scores),
            )
            if data_manager.close_gap is not None and data_manager.close_gap > D("0"):
                (
                    data_manager.initial_order,
                    data_manager.limit_price_order,
                    data_manager.stop_price_order,
                ) = self.app.place_bracket_order(
                    action=OrderType.LONG,
                    quantity=size,
                    price_limit=self.get_price(
                        data_manager.data1["close"].iloc[-1] * (1 + TARGET_PROFIT)
                    ),
                    take_profit_limit_price=self.get_price_with_deviation(
                        data_manager.data1["close"].iloc[-1], OrderType.LONG
                    ),
                    stop_loss_price=self.get_price(
                        data_manager.data1["close"].iloc[-1] * (1 - STOP_LOSS)
                    ),
                    stop_loss_limit_price=self.get_price(
                        data_manager.data1["close"].iloc[-1] * (1 - STOP_LOSS)
                    ),
                    contract=self.ibwrapper.get_contract(data_manager.symbol),
                    parent_valid=data_manager.data1.index[-1] + timedelta(minutes=30),
                    children_valid=arrow.get(data_manager.data1.index[-1])
                    .replace(hour=15, minute=0, second=0)
                    .datetime,
                )
            else:
                (
                    data_manager.initial_order,
                    data_manager.limit_price_order,
                    data_manager.stop_price_order,
                ) = self.app.place_bracket_order(
                    action=OrderType.SHORT,
                    quantity=size,
                    price_limit=self.get_price(
                        data_manager.data1["close"].iloc[-1] * (1 + TARGET_PROFIT)
                    ),
                    take_profit_limit_price=self.get_price_with_deviation(
                        data_manager.data1["close"].iloc[-1], OrderType.SHORT
                    ),
                    stop_loss_price=self.get_price(
                        data_manager.data1["close"].iloc[-1] * (1 - STOP_LOSS)
                    ),
                    stop_loss_limit_price=self.get_price(
                        data_manager.data1["close"].iloc[-1] * (1 - STOP_LOSS)
                    ),
                    contract=self.ibwrapper.get_contract(data_manager.symbol),
                    parent_valid=data_manager.data1.index[-1] + timedelta(minutes=30),
                    children_valid=arrow.get(data_manager.data1.index[-1])
                    .replace(hour=15, minute=0, second=0)
                    .datetime,
                )

        for data_manager in self.data_managers:
            data_manager.is_in_position = True

    def check_peaks(self) -> None:
        for data_manager in self.data_managers:
            if (
                not data_manager.initial_order
                or data_manager.initial_order.price <= 0
                or data_manager.did_leave_position
            ):
                continue
            if data_manager.close_gap is not None and data_manager.close_gap > 0:
                if (
                    data_manager.data1["close"].iloc[-1]
                    > 1.01 * data_manager.initial_order.price
                ):
                    if (
                        not data_manager.peak_price_gap
                        or data_manager.peak_price_gap
                        > (
                            data_manager.data1["close"].iloc[-1]
                            / data_manager.initial_order.price
                        )
                        - 1
                    ):
                        data_manager.peak_price_gap = (
                            data_manager.data1["close"].iloc[-1]
                            / data_manager.initial_order.price
                        ) - 1
                if (
                    data_manager.peak_price_gap is not None
                    and (
                        data_manager.data1["close"].iloc[-1]
                        / data_manager.initial_order.price
                    )
                    - 1
                    < 0.25 * data_manager.peak_price_gap
                ):
                    self.make_end_market_order(data_manager)
                    data_manager.did_leave_position = True
            else:
                if (
                    data_manager.data1["close"].iloc[-1]
                    < 0.99 * data_manager.initial_order.price
                ):
                    if (
                        not data_manager.peak_price_gap
                        or data_manager.peak_price_gap
                        > (
                            data_manager.initial_order.price
                            / data_manager.data1["close"].iloc[-1]
                        )
                        - 1
                    ):
                        data_manager.peak_price_gap = (
                            data_manager.initial_order.price
                            / data_manager.data1["close"].iloc[-1]
                        ) - 1
                if (
                    data_manager.peak_price_gap is not None
                    and (
                        data_manager.initial_order.price
                        / data_manager.data1["close"].iloc[-1]
                    )
                    - 1
                    < 0.25 * data_manager.peak_price_gap
                ):
                    logger.info(
                        f"Leaving position because of peaks {data_manager.symbol} {data_manager.data1.index[-1]}"
                    )
                    self.make_end_market_order(data_manager)
                    data_manager.did_leave_position = True

    def get_size(
        self, price: float, average_volume: int, cash: float, divider: int
    ) -> int:
        raise NotImplementedError()
