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
from controllers.trading.rsi import CustomRSI  # type: ignore
from utils.math_utils import D
from logger.logger import logger


class DataManager(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data1: Any
    data2: Any
    rsi: Any
    symbol: Optional[str] = None
    score: Optional[Decimal] = D("0")
    close_gap: Optional[Decimal] = D("0")
    average_volume: Optional[int] = None
    should_use_rsi: bool = False

    initial_order: Optional[bt.Order] = None
    limit_price_order: Optional[bt.Order] = None
    stop_price_order: Optional[bt.Order] = None

    market_order: Optional[bt.Order] = None


def strategy_factory(
    symbols: list[str],
    _today: datetime,
    _tick_duration: int,  # in seconds
    _working_signal: threading.Event,
    type: Literal["REAL", "TEST"],
    _mock_broker_queue: Optional[Queue[tuple[str, Any]]] = None,
) -> bt.Strategy:

    class BaseStrategy(bt.Strategy):  # type: ignore
        today: datetime = _today
        tick_duration: int = _tick_duration

        data_ready: bool = False
        is_in_position: bool = False
        did_leave_position: bool = False
        did_signal_working: bool = False
        working_signal: threading.Event = _working_signal
        datas_manager: list[DataManager] = []

        def __init__(self) -> None:
            super().__init__()
            for index in range(0, len(self.datas), 2):
                self.datas_manager.append(
                    DataManager(
                        data1=self.datas[index],
                        data2=self.datas[index + 1],
                        symbol=symbols[index // 2],
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
            for data_manager in self.datas_manager:
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
                    logger.info(
                        f"{type} completed {target_data_manager.symbol} {curr_datetime.time()} share_price: {order.executed.price}, commission: {order.executed.comm}"
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
                        logger.info(
                            f"{type} completed {target_data_manager.symbol} {curr_datetime.time()} share_price: {order.executed.price:.3f}, value: {value:.3f}, commission: {order.executed.comm}"
                        )
                self.bar_executed = len(self)

            if self.did_leave_position and self.position.size == 0:
                self.stop_run()

        def stop_run(self) -> None:
            print(f"Stopping run {self.get_curr_datetime()}")
            self.env.runstop()

        def buy_custom(self, parent: bt.Order = None, **kwargs: Any) -> bt.Order:
            raise NotImplementedError()

        def sell_custom(self, parent: bt.Order = None, **kwargs: Any) -> bt.Order:
            raise NotImplementedError()

        def get_index_by_datetime(self, datetime: arrow.Arrow) -> int:
            curr_datetime = self.get_curr_datetime()
            return 0 - int((curr_datetime - datetime).seconds / self.tick_duration)

        def get_index_by_timedelta(self, timedelta: timedelta) -> int:
            return 0 - int(timedelta.seconds / self.tick_duration)

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

        def get_close_gap(self, data: Any, curr_datetime: arrow.Arrow) -> Decimal:
            close_gap = (
                data.close[0]
                / data.open[
                    self.get_index_by_datetime(
                        arrow.get(curr_datetime).replace(hour=9, minute=34, second=0),
                    )
                ]
            ) - 1
            return D(close_gap)

        def get_average_volume(self, data: Any) -> int:
            curr_datetime = self.get_curr_datetime()
            return int(
                average(
                    data.volume.get(
                        size=abs(
                            self.get_index_by_datetime(
                                arrow.get(curr_datetime).replace(
                                    hour=9, minute=35, second=0
                                ),
                            )
                        )
                    )
                )
                * average(
                    data.open.get(
                        size=abs(
                            self.get_index_by_datetime(
                                arrow.get(curr_datetime).replace(
                                    hour=9, minute=35, second=0
                                ),
                            )
                        )
                    )
                )
            )

        def should_trade_stock(self, data: Any, is_buy: bool) -> bool:
            curr_datetime = self.get_curr_datetime()
            if is_buy:
                highest = max(
                    data.high.get(
                        size=abs(
                            self.get_index_by_datetime(
                                arrow.get(curr_datetime).replace(
                                    hour=9, minute=35, second=0
                                ),
                            )
                        )
                    )
                )
                start_of_day = data.open[
                    self.get_index_by_datetime(
                        arrow.get(curr_datetime).replace(hour=9, minute=30, second=0),
                    )
                ]
                curr_diff, start_diff = (
                    highest - data.close[0],
                    highest - start_of_day,
                )
            else:
                lowest = min(
                    data.low.get(
                        size=abs(
                            self.get_index_by_datetime(
                                arrow.get(curr_datetime).replace(
                                    hour=9, minute=35, second=0
                                ),
                            )
                        )
                    )
                )
                start_of_day = data.open[
                    self.get_index_by_datetime(
                        arrow.get(curr_datetime).replace(hour=9, minute=30, second=0),
                    )
                ]
                curr_diff, start_diff = (
                    data.close[0] - lowest,
                    start_of_day - lowest,
                )

            if bool(curr_diff * start_diff > 0 and curr_diff > 0.5 * start_diff):
                return False

            highest_open = max(
                data.open.get(
                    size=abs(
                        self.get_index_by_datetime(
                            arrow.get(curr_datetime).replace(
                                hour=10, minute=0, second=0
                            )
                        )
                    )
                )
            )

            lowest_open = min(
                data.open.get(
                    size=abs(
                        self.get_index_by_datetime(
                            arrow.get(curr_datetime).replace(
                                hour=10, minute=0, second=0
                            )
                        )
                    )
                )
            )
            if is_buy:
                if highest_open > data.close[0] and (
                    highest_open - data.close[0]
                ) * 0.5 > (data.close[0] - lowest_open):
                    return False

                if (
                    data.close[self.get_index_by_timedelta(timedelta(minutes=39))]
                    - data.close[0]
                    > 0
                    and data.close[self.get_index_by_timedelta(timedelta(minutes=14))]
                    - data.close[0]
                    > 0
                ):
                    return False
            else:
                if lowest_open < data.close[0] and (
                    data.close[0] - lowest_open
                ) * 0.5 > (highest_open - data.close[0]):
                    return False

                if (
                    data.close[0]
                    - data.close[self.get_index_by_timedelta(timedelta(minutes=39))]
                    > 0
                    and data.close[0]
                    - data.close[self.get_index_by_timedelta(timedelta(minutes=14))]
                    > 0
                ):
                    return False

            return True

        def get_curr_datetime(self) -> arrow.Arrow:
            return arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE)

        def next(self) -> None:
            if not self.working_signal.is_set():
                self.working_signal.set()
            curr_datetime = self.get_curr_datetime()
            if self.did_leave_position:
                return

            # Checking if time is up for the day
            if curr_datetime >= arrow.get(self.today).replace(
                hour=15, minute=0, second=0
            ):
                for data_manager in self.datas_manager:
                    if (
                        data_manager.market_order is not None
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
                self.did_leave_position = True
                return

            # Checking if RSI is signaling to leave
            if self.is_in_position:
                for data_manager in self.datas_manager:
                    if (
                        data_manager.initial_order is not None
                        and data_manager.initial_order.status in [bt.Order.Completed]
                        and data_manager.should_use_rsi
                    ):
                        if (
                            data_manager.market_order is None
                            and data_manager.limit_price_order is not None
                            and data_manager.limit_price_order.status
                            not in [bt.Order.Completed]
                            and data_manager.stop_price_order is not None
                            and data_manager.stop_price_order.status
                            not in [bt.Order.Completed]
                        ):
                            if (
                                data_manager.rsi[0] >= 70
                                and data_manager.initial_order.isbuy()
                                and data_manager.initial_order.executed.price
                                < data_manager.data1.close[0]
                            ):
                                logger.info("Leaving because of RSI")
                                data_manager.limit_price_order.cancel()
                                data_manager.stop_price_order.cancel()
                                data_manager.market_order = self.sell_custom(
                                    data=data_manager.data1,
                                    size=data_manager.initial_order.size,
                                    exectype=bt.Order.Market,
                                )
                            elif (
                                data_manager.rsi[0] <= 30
                                and data_manager.initial_order.issell()
                                and data_manager.initial_order.executed.price
                                > data_manager.data1.close[0]
                            ):
                                logger.info("Leaving because of RSI")
                                data_manager.limit_price_order.cancel()
                                data_manager.stop_price_order.cancel()
                                data_manager.market_order = self.buy_custom(
                                    data=data_manager.data1,
                                    size=data_manager.initial_order.size,
                                    exectype=bt.Order.Market,
                                )
            if (
                not (
                    arrow.get(self.today).replace(hour=10, minute=59, second=0)
                    <= curr_datetime
                    < arrow.get(self.today).replace(hour=11, minute=30)
                )
                or self.is_in_position
            ):
                return
            # Iterating datas and checking stats
            for data_manager in self.datas_manager:
                data = data_manager.data1
                data_manager.average_volume = self.get_average_volume(data)
                if (
                    data_manager.average_volume is None
                    or data_manager.average_volume < 10000
                ):
                    logger.info(f"Not trading {data_manager.symbol}")
                    data_manager.score = D("0")
                    continue
                close_gap = self.get_close_gap(data, curr_datetime)
                if close_gap > 0:
                    should_trade_stock = self.should_trade_stock(data, is_buy=True)
                    if not should_trade_stock:
                        data_manager.score = D("0")
                        logger.info(f"Not trading {data_manager.symbol}")
                    else:
                        data_manager.score = D(abs(close_gap))
                else:
                    should_trade_stock = self.should_trade_stock(data, is_buy=False)
                    if not should_trade_stock:
                        data_manager.score = D("0")
                        logger.info(f"Not trading {data_manager.symbol}")
                        continue
                    else:
                        data_manager.score = D(abs(close_gap))
                data_manager.close_gap = D(close_gap)

            # Entering position with stocks with highest scores
            filtered_scores: list[DataManager] = []
            for data_manager in self.datas_manager:
                if data_manager.score is not None and data_manager.score > D("0"):
                    filtered_scores.append(data_manager)
            sorted_scores: list[DataManager] = sorted(
                filtered_scores, key=lambda x: x.score, reverse=True  # type: ignore
            )[0:3]
            for data_manager in sorted_scores:
                data = data_manager.data1
                if data_manager.average_volume is None:
                    raise Exception("Average volume is None")
                size = self.get_size(
                    data.close[0], data_manager.average_volume, len(sorted_scores)
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
                        limitprice=data.close[0] * 1.05,
                        price=data.close[0],
                        stopprice=data.close[0] * 0.98,
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
                        limitprice=data.close[0] * 0.95,
                        price=data.close[0],
                        stopprice=data.close[0] * 1.02,
                        parent_valid=timedelta(minutes=30),
                        children_valid=timedelta(hours=4),
                        order_type="short",
                    )
            curr_rsi = data_manager.rsi[0]
            data_manager.should_use_rsi = curr_rsi >= 40 and curr_rsi <= 60
            self.is_in_position = True

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
                logger.info(f"Size: {size}")
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
