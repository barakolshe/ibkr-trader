from datetime import datetime, timedelta
from decimal import Decimal
from queue import Queue
import threading
from typing import Any, Literal, Optional, Union
import arrow
import backtrader as bt
from numpy import average
from pydantic import BaseModel, ConfigDict

# from IBJts.source.pythonclient.ibapi import order
from consts.time_consts import TIMEZONE
from consts.trading_consts import (
    CHECK_PEAKS,
    EXTREMUM_DIFF_THRESHOLD,
    SHOULD_USE_RSI,
    STOP_LOSS,
    TARGET_PROFIT,
    CLOSE_GAP_MULTIPLIER_THRESHOLD,
    get_end_datetime,
    get_analysis_start_datetime,
    get_start_datetime,
    get_volume_analysis_start_datetime,
)
from controllers.trading.rsi import CustomRSI  # type: ignore
from utils.math_utils import D
from logger.logger import logger, log_important


class DataManager(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data1: Any
    data3: Any
    data5: Any
    rsi: Any
    symbol: Optional[str] = None
    score: Optional[Decimal] = D("0")
    close_gap: Optional[Decimal] = D("0")
    average_volume: Optional[int] = None
    should_use_rsi: bool = False
    peak_price_gap: Optional[Decimal] = None
    is_in_position: bool = False
    did_leave_position: bool = False

    initial_order: Optional[bt.Order] = None
    limit_price_order: Optional[bt.Order] = None
    stop_price_order: Optional[bt.Order] = None

    market_order: Optional[bt.Order] = None


def strategy_factory(
    symbols: list[str],
    _today: datetime,
    _working_signal: threading.Event,
    type: Literal["REAL", "TEST"],
    _mock_broker_queue: Optional[Queue[tuple[str, Any]]] = None,
) -> bt.Strategy:

    class BaseStrategy(bt.Strategy):  # type: ignore
        today: datetime = _today

        data_ready: bool = False
        did_signal_working: bool = False
        working_signal: threading.Event = _working_signal
        data_managers: list[DataManager] = []

        def __init__(self) -> None:
            super().__init__()
            for index in range(0, len(self.datas), 3):
                self.data_managers.append(
                    DataManager(
                        data1=self.datas[index],
                        data3=self.datas[index + 1],
                        data5=self.datas[index + 2],
                        symbol=symbols[index // 3],
                        rsi=CustomRSI(self.datas[index + 1], rsi_period=14),
                    )
                )

        def get_cash(self) -> float:
            return self.broker.getcash()  # type: ignore

        def notify_data(self, data: Any, status: int) -> None:
            if status == data.LIVE:
                self.data_ready = True

        def get_price(self, price: float) -> float:
            raise NotImplementedError()

        def notify_order(self, order: bt.Order) -> None:
            curr_datetime = arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE)
            target_data_manager: Optional[DataManager] = None
            for data_manager in self.data_managers:
                if order in [
                    data_manager.initial_order,
                    data_manager.limit_price_order,
                    data_manager.stop_price_order,
                    data_manager.market_order,
                ]:
                    target_data_manager = data_manager
            type = ""
            if order.isbuy():
                type = "Buy"
            else:
                type = "Sell"

            if target_data_manager is None:
                return

            if order.status in [order.Accepted]:
                return

            if order.status in [order.Canceled]:
                logger.info(
                    f"{type} cancelled {target_data_manager.symbol} {curr_datetime.time()}"
                )
                return

            if order.status in [order.Expired]:
                logger.info(
                    f"{type} expired {target_data_manager.symbol} {curr_datetime.time()}"
                )
                return

            if order.status in [order.Completed]:
                if order == target_data_manager.initial_order:
                    log_important(
                        f"{type} completed {target_data_manager.symbol} {curr_datetime.time()} share_price: {order.executed.price}, commission: {order.executed.comm}",
                        "info",
                    )
                else:
                    if target_data_manager.initial_order is not None:
                        value = (
                            (order.executed.price * order.executed.size)
                            + (
                                target_data_manager.initial_order.executed.price
                                * target_data_manager.initial_order.executed.size
                            )
                        ) * -1
                        log_important(
                            f"{type} completed {target_data_manager.symbol} {curr_datetime.time()} share_price: {order.executed.price:.3f}, value: {value:.3f}, commission: {order.executed.comm}",
                            "info",
                        )
                self.bar_executed = len(self)

                # for data_manager in self.datas_manager:
                #     if self.getposition(data=data_manager.data1).size != 0:
                #         return
                # self.stop_run()

        def stop_run(self) -> None:
            print(f"Stopping run {self.get_curr_datetime()}")
            self.env.runstop()

        def buy_custom(self, parent: bt.Order = None, **kwargs: Any) -> bt.Order:
            raise NotImplementedError()

        def sell_custom(self, parent: bt.Order = None, **kwargs: Any) -> bt.Order:
            raise NotImplementedError()

        def get_index_by_datetime(
            self, datetime: arrow.Arrow, tick_size: int = 1
        ) -> int:
            curr_datetime = self.get_curr_datetime()
            return 0 - int((curr_datetime - datetime).seconds // (60 * tick_size))

        def get_index_by_timedelta(
            self, timedelta: timedelta, tick_size: int = 1
        ) -> int:
            return 0 - int(timedelta.seconds // (60 * tick_size))

        def bracket_order_custom(
            self,
            data: Any,
            limitprice: float,
            price: float,
            stopprice: float,
            size: float,
            parent_valid: timedelta | datetime,
            children_valid: timedelta | datetime,
            order_type: Union[Literal["long"], Literal["short"]],
        ) -> tuple[bt.Order, bt.Order, bt.Order]:
            if order_type == "long":
                main = self.buy_custom(
                    data=data,
                    price=self.get_price(price) * 1.005,
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    valid=parent_valid,
                    outsideRth=True,
                )
                limit_price = self.sell_custom(
                    data=data,
                    price=self.get_price(limitprice),
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    parent=main,
                    valid=children_valid,
                    outsideRth=True,
                )
                stop_price = self.sell_custom(
                    data=data,
                    price=self.get_price(stopprice),
                    size=size,
                    exectype=bt.Order.StopLimit,
                    plimit=self.get_price(stopprice * 0.95),
                    transmit=True,
                    parent=main,
                    valid=children_valid,
                )
            else:
                main = self.sell_custom(
                    data=data,
                    price=price * 0.995,
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    valid=parent_valid,
                )
                limit_price = self.buy_custom(
                    data=data,
                    price=self.get_price(limitprice),
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    parent=main,
                    valid=children_valid,
                )
                stop_price = self.buy_custom(
                    data=data,
                    price=self.get_price(stopprice),
                    size=size,
                    exectype=bt.Order.StopLimit,
                    plimit=self.get_price(stopprice * 1.05),
                    transmit=True,
                    parent=main,
                    valid=children_valid,
                )

            return main, limit_price, stop_price

        def get_close_gap_percent(
            self, data_manager: DataManager, curr_datetime: arrow.Arrow
        ) -> Decimal:
            close_gap = (
                data_manager.data1.close[0]
                / data_manager.data1.open[
                    self.get_index_by_datetime(
                        get_analysis_start_datetime(self.today),
                    )
                ]
            ) - 1
            return D(close_gap)

        def get_close_gap_difference(
            self, data_manager: DataManager, datetime: arrow.Arrow
        ) -> Decimal:
            close_gap = (
                data_manager.data1.close[0]
                - data_manager.data1.open[
                    self.get_index_by_datetime(
                        datetime,
                    )
                ]
            )
            return D(close_gap)

        def get_average_volume(self, data_manager: DataManager) -> int:
            average_volume = int(
                average(
                    data_manager.data1.volume.get(
                        size=abs(
                            self.get_index_by_datetime(
                                get_volume_analysis_start_datetime(self.today),
                            )
                        )
                    )
                )
                * average(
                    data_manager.data1.open.get(
                        size=abs(
                            self.get_index_by_datetime(
                                get_volume_analysis_start_datetime(self.today),
                            )
                        )
                    )
                )
            )
            log_important(
                f"Average volume for {data_manager.symbol}: {average_volume}", "info"
            )
            return average_volume

        def should_trade_stock(self, data_manager: DataManager) -> bool:
            if data_manager.close_gap is None:
                raise Exception("Close gap is None")
            start_of_day = data_manager.data1.open[
                self.get_index_by_datetime(
                    get_analysis_start_datetime(self.today).shift(minutes=-5),
                )
            ]
            if data_manager.close_gap > 0:
                highest = max(
                    data_manager.data1.high.get(
                        size=abs(
                            self.get_index_by_datetime(
                                get_analysis_start_datetime(self.today)
                            )
                        )
                    )
                )

                start_diff = highest - start_of_day
                curr_diff = highest - data_manager.data1.close[0]
            else:
                lowest = min(
                    data_manager.data1.low.get(
                        size=abs(
                            self.get_index_by_datetime(
                                get_analysis_start_datetime(self.today),
                            )
                        )
                    )
                )

                curr_diff = data_manager.data1.close[0] - lowest
                start_diff = start_of_day - lowest

            if bool(
                curr_diff * start_diff > 0
                and curr_diff > EXTREMUM_DIFF_THRESHOLD * start_diff
            ):
                log_important(
                    f"Not trading {data_manager.symbol} because of extremum gap", "info"
                )
                return False

            absolute_gap = 0
            start_index = self.get_index_by_datetime(
                get_analysis_start_datetime(self.today).shift(minutes=5),
                tick_size=5,
            )

            for i in range(start_index, 1):
                absolute_gap += abs(
                    data_manager.data5.close[i] - data_manager.data5.close[i - 1]
                )
            if (
                absolute_gap
                > abs(data_manager.close_gap) * CLOSE_GAP_MULTIPLIER_THRESHOLD
            ):
                log_important(
                    f"Not trading {data_manager.symbol} because of absolute gap", "info"
                )
                return False

            return True

        def get_curr_datetime(self) -> arrow.Arrow:
            return arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE)

        def make_end_market_order(self, data_manager: DataManager) -> None:
            if data_manager.initial_order.isbuy():
                data_manager.market_order = self.sell_custom(
                    data=data_manager.data1,
                    size=data_manager.initial_order.size,
                    exectype=bt.Order.Market,
                )
            else:
                data_manager.market_order = self.buy_custom(
                    data=data_manager.data1,
                    size=data_manager.initial_order.size,
                    exectype=bt.Order.Market,
                )
            data_manager.limit_price_order.cancel()
            data_manager.stop_price_order.cancel()

        def check_end_position(self) -> None:
            for data_manager in self.data_managers:
                if (
                    data_manager.did_leave_position
                    or data_manager.market_order is not None
                    or data_manager.initial_order is None
                    or data_manager.initial_order.status not in [bt.Order.Completed]
                    or data_manager.limit_price_order.status in [bt.Order.Completed]  # type: ignore
                    or data_manager.stop_price_order.status in [bt.Order.Completed]  # type: ignore
                ):
                    continue
                if data_manager.stop_price_order.status not in [  # type: ignore
                    bt.Order.Completed
                ] and data_manager.stop_price_order.status not in [  # type: ignore
                    bt.Order.Completed
                ]:
                    self.make_end_market_order(data_manager)
                data_manager.did_leave_position = True
            return

        def check_rsi(self) -> None:
            for data_manager in self.data_managers:
                if (
                    data_manager.initial_order is None
                    or data_manager.initial_order.status not in [bt.Order.Completed]
                    or not data_manager.should_use_rsi
                ):
                    continue
                if (
                    data_manager.market_order is None
                    and data_manager.limit_price_order is not None
                    and data_manager.limit_price_order.status
                    not in [bt.Order.Completed]
                    and data_manager.stop_price_order is not None
                    and data_manager.stop_price_order.status not in [bt.Order.Completed]
                ):
                    if (
                        data_manager.rsi[0] >= 72
                        and data_manager.initial_order.isbuy()
                        and data_manager.initial_order.executed.price
                        < data_manager.data1.close[0]
                    ):
                        logger.info("Leaving because of RSI")
                        data_manager.limit_price_order.cancel()
                        data_manager.stop_price_order.cancel()
                        logger.info(f"RSI: {data_manager.rsi[0]}")
                        data_manager.market_order = self.sell_custom(
                            data=data_manager.data1,
                            size=data_manager.initial_order.size,
                            exectype=bt.Order.Market,
                        )
                    elif (
                        data_manager.rsi[0] <= 28
                        and data_manager.initial_order.issell()
                        and data_manager.initial_order.executed.price
                        > data_manager.data1.close[0]
                    ):
                        logger.info("Leaving because of RSI")
                        data_manager.limit_price_order.cancel()
                        data_manager.stop_price_order.cancel()
                        logger.info(f"RSI: {data_manager.rsi[0]}")
                        data_manager.market_order = self.buy_custom(
                            data=data_manager.data1,
                            size=data_manager.initial_order.size,
                            exectype=bt.Order.Market,
                        )

        def get_stats(self, data_manager: DataManager) -> None:
            curr_datetime = self.get_curr_datetime()
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
                or data_manager.average_volume < 10000
            ):
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
                    data_manager.score = D(
                        abs(self.get_close_gap_percent(data_manager, curr_datetime))
                    )
            else:
                should_trade_stock = self.should_trade_stock(data_manager)
                if not should_trade_stock:
                    data_manager.is_in_position = True
                else:
                    data_manager.score = D(
                        abs(self.get_close_gap_percent(data_manager, curr_datetime))
                    )

        def enter_position(self) -> None:
            for data_manager in self.data_managers:
                if (
                    data_manager.data1.datetime.datetime(0) != self.datetime.datetime(0)
                    or data_manager.is_in_position
                ):
                    data_manager.is_in_position = True
                    continue
                self.get_stats(data_manager)

            # Entering position with stocks with highest scores
            filtered_scores: list[DataManager] = []
            for data_manager in self.data_managers:
                if data_manager.score is not None and data_manager.score > D("0"):
                    filtered_scores.append(data_manager)
            sorted_scores: list[DataManager] = sorted(
                filtered_scores, key=lambda x: x.score, reverse=True  # type: ignore
            )[0:3]
            for data_manager in sorted_scores:
                if data_manager.is_in_position:
                    continue
                data = data_manager.data1
                if data_manager.average_volume is None:
                    raise Exception("Average volume is None")
                size = self.get_size(
                    data.close[0],
                    data_manager.average_volume,
                    len(sorted_scores),
                )
                if data_manager.close_gap is not None and data_manager.close_gap > D(
                    "0"
                ):
                    (
                        data_manager.initial_order,
                        data_manager.limit_price_order,
                        data_manager.stop_price_order,
                    ) = self.bracket_order_custom(
                        data=data,
                        size=size,
                        limitprice=data.close[0] * (1 + TARGET_PROFIT),
                        price=data.close[0],
                        stopprice=data.close[0] * (1 - STOP_LOSS),
                        parent_valid=timedelta(minutes=30),
                        children_valid=timedelta(hours=4),
                        order_type="long",
                    )
                else:
                    (
                        data_manager.initial_order,
                        data_manager.limit_price_order,
                        data_manager.stop_price_order,
                    ) = self.bracket_order_custom(
                        data=data,
                        size=size,
                        limitprice=data.close[0] * (1 - TARGET_PROFIT),
                        price=data.close[0],
                        stopprice=data.close[0] * (1 + STOP_LOSS),
                        parent_valid=timedelta(minutes=30),
                        children_valid=timedelta(hours=4),
                        order_type="short",
                    )
                curr_rsi = data_manager.rsi[0]
                # logger.info(f"INITIAL RSI: {curr_rsi}")
                data_manager.should_use_rsi = curr_rsi >= 40 and curr_rsi <= 60
                data_manager.is_in_position = True

        def check_peaks(self) -> None:
            for data_manager in self.data_managers:
                if (
                    not data_manager.initial_order
                    or data_manager.initial_order.executed.price <= 0
                    or data_manager.did_leave_position
                ):
                    continue
                if data_manager.close_gap > 0:
                    if (
                        data_manager.data1.close[0]
                        > 1.01 * data_manager.initial_order.executed.price
                    ):
                        if (
                            not data_manager.peak_price_gap
                            or data_manager.peak_price_gap
                            > (
                                data_manager.data1.close[0]
                                / data_manager.initial_order.executed.price
                            )
                            - 1
                        ):
                            data_manager.peak_price_gap = (
                                data_manager.data1.close[0]
                                / data_manager.initial_order.executed.price
                            ) - 1
                    if (
                        data_manager.peak_price_gap is not None
                        and (
                            data_manager.data1.close[0]
                            / data_manager.initial_order.executed.price
                        )
                        - 1
                        < 0.25 * data_manager.peak_price_gap
                    ):
                        self.make_end_market_order(data_manager)
                        data_manager.did_leave_position = True
                else:
                    if (
                        data_manager.data1.close[0]
                        < 0.99 * data_manager.initial_order.executed.price
                    ):
                        if (
                            not data_manager.peak_price_gap
                            or data_manager.peak_price_gap
                            > (
                                data_manager.initial_order.executed.price
                                / data_manager.data1.close[0]
                            )
                            - 1
                        ):
                            data_manager.peak_price_gap = (
                                data_manager.initial_order.executed.price
                                / data_manager.data1.close[0]
                            ) - 1
                    if (
                        data_manager.peak_price_gap is not None
                        and (
                            data_manager.initial_order.executed.price
                            / data_manager.data1.close[0]
                        )
                        - 1
                        < 0.25 * data_manager.peak_price_gap
                    ):
                        self.make_end_market_order(data_manager)
                        data_manager.did_leave_position = True

        def next(self) -> None:
            curr_datetime = self.get_curr_datetime()

            if (
                get_start_datetime(self.today).shift(minutes=-1)
                <= curr_datetime
                < get_start_datetime(self.today).shift(minutes=30)
            ):
                self.enter_position()
            # Checking if time is up for the day
            if curr_datetime >= get_end_datetime(self.today):
                self.check_end_position()
                return

            if CHECK_PEAKS:
                self.check_peaks()

            # Checking if RSI is signaling to leave
            if SHOULD_USE_RSI:
                self.check_rsi()

        def get_size(self, price: Decimal, average_volume: int, divider: int) -> int:
            raise NotImplementedError()

    if type == "TEST":

        class TestStrategy(BaseStrategy):

            def buy_custom(
                self, parent: Optional[bt.Order] = None, **kwargs: Any
            ) -> bt.Order:
                return self.buy(
                    parent=parent,
                    **kwargs,
                )

            def sell_custom(
                self, parent: Optional[bt.Order] = None, **kwargs: Any
            ) -> bt.Order:
                return self.sell(
                    parent=parent,
                    **kwargs,
                )

            def get_price(self, price: float) -> float:
                return price

            def set_cash(self, cash: float) -> None:
                if _mock_broker_queue is None:
                    raise Exception("Using test wrong")
                _mock_broker_queue.put(("SET", cash))

            def get_size(
                self, price: Decimal, average_volume: int, divider: int
            ) -> int:
                size = min(
                    average_volume // 2,
                    int(D(self.get_cash() * 0.99) // D(price) // divider),
                )
                return size

        return TestStrategy

    if type == "REAL":

        class RealStrategy(BaseStrategy):
            def buy_csutom(
                self, parent: Optional[bt.Order] = None, **kwargs: Any
            ) -> bt.Order:
                return self.buy(
                    parentId=(
                        parent.orderId
                        if parent is not None and hasattr(parent, "orderId")
                        else None
                    ),
                    **kwargs,
                )

            def sell_custom(
                self, parent: Optional[bt.Order] = None, **kwargs: Any
            ) -> bt.Order:
                return self.sell(
                    parentId=(
                        parent.orderId
                        if parent is not None and hasattr(parent, "orderId")
                        else None
                    ),
                    **kwargs,
                )

            def should_start_trading(self, curr_datetime: datetime) -> bool:
                return self.data_ready

            def get_size(
                self, price: Decimal, average_volume: int, divider: int
            ) -> int:
                return min(
                    average_volume // 2,
                    int(D(min(self.get_cash(), 5000)) // price // divider),
                )

            def get_price(self, price: float) -> float:
                return float(D(price, precision=D("0.05")))

        return RealStrategy
