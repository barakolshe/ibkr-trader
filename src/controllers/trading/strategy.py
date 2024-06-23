from datetime import datetime, timedelta, timezone
from decimal import Decimal
from queue import Queue
import threading
from typing import Any, Literal, Optional, Union
import arrow
import backtrader as bt
from numpy import average
from pydantic import BaseModel, ConfigDict

from consts.time_consts import TIMEZONE
from utils.math_utils import D
from logger.logger import logger


class DataManager(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: Any
    symbol: Optional[str] = None
    score: Optional[Decimal] = D("0")
    close_gap: Optional[Decimal] = D("0")

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
            for index, data in enumerate(self.datas):
                self.datas_manager.append(DataManager(data=data, symbol=symbols[index]))

        def get_cash(self) -> float:
            return self.broker.getcash()  # type: ignore

        def notify_data(self, data: Any, status: int) -> None:
            if status == data.LIVE:
                self.data_ready = True

        def get_price(self, price: float) -> float:
            raise NotImplementedError()

        def notify_order(self, order: bt.Order) -> None:
            curr_datetime = arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE)
            symbol = ""
            for data_manager in self.datas_manager:
                if order in [
                    data_manager.initial_order,
                    data_manager.limit_price_order,
                    data_manager.stop_price_order,
                    data_manager.market_order,
                ]:
                    if data_manager.symbol is None:
                        raise Exception("Symbol is None")
                    symbol = data_manager.symbol
            type = ""
            if order.isbuy():
                type = "Buy"
            else:
                type = "Sell"

            if order.status in [order.Accepted]:
                return

            if order.status in [order.Canceled]:
                logger.info(f"{type} cancelled {symbol} {curr_datetime} {order.size}")
                return

            if order.status in [order.Expired]:
                logger.info(f"{type} expired {symbol} {curr_datetime} {order.size}")
                return

            if order.status in [order.Completed]:
                logger.info(
                    f"{type} completed {symbol} {curr_datetime} order_value: {order.executed.price}"
                )
                self.bar_executed = len(self)

            if self.did_leave_position and self.position.size == 0:
                self.stop_run()

        def stop_run(self) -> None:
            print("Stopping run")
            self.env.runstop()

        def buy_custom(self, parent: bt.Order = None, **kwargs: Any) -> bt.Order:
            raise NotImplementedError()

        def sell_custom(self, parent: bt.Order = None, **kwargs: Any) -> bt.Order:
            raise NotImplementedError()

        def adjust_time_index(self, index: int) -> int:
            value = index * (60 / self.tick_duration)
            if value % 1.0 != 0:
                raise Exception("Value is not an integer")
            return int(value)

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

        def next(self) -> None:
            if not self.working_signal.is_set():
                self.working_signal.set()
            curr_datetime = arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE)
            if self.did_leave_position:
                return

            # Checking if time is up for the day
            if curr_datetime >= arrow.get(self.today).replace(
                hour=15, minute=0, second=0
            ):
                for data_manager in self.datas_manager:
                    if (
                        data_manager.initial_order is None
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
                                data=data_manager.data,
                                size=data_manager.initial_order.size,
                                exectype=bt.Order.Market,
                            )
                        else:
                            data_manager.market_order = self.buy_custom(
                                data=data_manager.data,
                                size=data_manager.initial_order.size,
                                exectype=bt.Order.Market,
                            )
                self.did_leave_position = True

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
                data = data_manager.data
                volume = sum(
                    data.volume.get(size=self.adjust_time_index(84))
                ) * average(data.open.get(size=self.adjust_time_index(84)))
                if volume < 20000:
                    logger.info(f"Not trading {data_manager.symbol}")
                    data_manager.score = D("0")
                    continue
                close_gap = (
                    data.close[0] / data.open[(self.adjust_time_index(-84))]
                ) - 1
                if close_gap > 0:
                    highest = max(data.high.get(size=self.adjust_time_index(84)))
                    start_of_day = data.open[self.adjust_time_index(-89)]
                    curr_diff, start_diff = (
                        highest - data.close[0],
                        highest - start_of_day,
                    )
                    if (
                        data.close[self.adjust_time_index(-39)] - data.close[0] > 0
                        and data.close[self.adjust_time_index(-14)] - data.close[0] > 0
                    ):
                        data_manager.score = D("0")
                        logger.info(f"Not trading {data_manager.symbol}")
                        continue
                    if curr_diff * start_diff > 0 and curr_diff > 0.5 * start_diff:
                        data_manager.score = D("0")
                        logger.info(f"Not trading {data_manager.symbol}")
                    else:
                        data_manager.score = D(abs(close_gap))
                else:
                    lowest = min(data.low.get(size=self.adjust_time_index(84)))
                    start_of_day = data.open[self.adjust_time_index(-89)]
                    curr_diff, start_diff = (
                        data.close[0] - lowest,
                        start_of_day - lowest,
                    )
                    if (
                        data.close[0] - data.close[self.adjust_time_index(-39)] > 0
                        and data.close[0] - data.close[self.adjust_time_index(-14)] > 0
                    ):
                        data_manager.score = D("0")
                        logger.info(f"Not trading {data_manager.symbol}")
                        continue
                    if curr_diff * start_diff > 0 and curr_diff > 0.5 * start_diff:
                        data_manager.score = D("0")
                        logger.info(f"Not trading {data_manager.symbol}")
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
                data = data_manager.data
                size = self.get_size(data.close[0]) // len(sorted_scores)
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
            self.is_in_position = True

        def get_size(self, price: Decimal) -> int:
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

            def get_size(self, price: Decimal) -> int:
                return int(D(self.get_cash() * 0.99) // D(price))

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

            def get_size(self, price: Decimal) -> int:
                return int(D(min(self.get_cash(), 5000)) // price)

            def get_price(self, price: float) -> float:
                return float(D(price, precision=D("0.05")))

        return RealStrategy
