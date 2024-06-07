from datetime import datetime, timedelta
from decimal import Decimal
import os
from queue import Queue
import threading
from typing import Any, Literal, Optional, Union
import arrow
import backtrader as bt

from consts.time_consts import TIMEZONE
from controllers.trading.mock_broker import MockBroker
from utils.math_utils import D
from utils.time_utils import is_between_dates
from logger.logger import logger


def is_order_completed(order: bt.Order) -> bool:
    return order.status in [bt.Order.Completed]


def strategy_factory(
    _target_profit: Decimal,
    _stop_loss: Decimal,
    _max_time: timedelta,
    _symbol: str,
    _event_timestamp: datetime,
    _change_divisor_event: threading.Event,
    _divisor_queue: Queue[int],
    _divisor: int,
    _in_position_event: threading.Event,
    _mock_broker: Optional[MockBroker] = None,
    _test_next_tick_queue: Optional[Queue[Queue[Any]]] = None,
    _test_curr_time: Optional[datetime] = None,
) -> bt.Strategy:

    class BaseStrategy(bt.Strategy):  # type: ignore
        target_profit: Decimal = _target_profit
        stop_loss: Decimal = _stop_loss
        max_time: timedelta = _max_time
        start_time: datetime
        symbol: str = _symbol
        event_timestamp: datetime = _event_timestamp
        data_ready: bool = False

        change_divisor_event: threading.Event = _change_divisor_event
        divisor_queue: Queue[int] = _divisor_queue
        divisor: int = _divisor
        in_position_event: threading.Event = _in_position_event

        initial_order: Optional[bt.Order] = None
        limit_price_order: Optional[bt.Order] = None
        stop_price_order: Optional[bt.Order] = None
        orders: list[bt.Order] = []

        # For missing minutes
        first_of_day_after_start: Optional[datetime] = None
        time_delay: int = 0
        test_next_tick_queue: Optional[Queue[Queue[Any]]] = _test_next_tick_queue
        test_curr_time: Optional[datetime] = _test_curr_time

        def get_cash(self) -> float:
            raise NotImplementedError()

        def set_cash(self, cash: float) -> None:
            raise NotImplementedError()

        def log(self, txt: str, date: Optional[datetime] = None) -> None:
            """Logging function for this strategy"""
            date = date or self.data.datetime.datetime(0)
            print(f"{arrow.get(date).to(TIMEZONE).datetime} {txt}")

        def __init__(self) -> None:
            self.start_time = (
                arrow.get(self.data.datetime.datetime(1)).to(TIMEZONE).datetime
            )
            self.dataclose = self.data.close
            self.start_price = self.dataclose[1]

        def notify_data(self, data: Any, status: int) -> None:
            if status == data.LIVE:
                self.data_ready = True

        def count_minutes_delay(self, curr_date: datetime) -> int:
            if (
                arrow.get(curr_date).date() == arrow.get(self.event_timestamp).date()
                and curr_date > self.event_timestamp
            ):
                if self.first_of_day_after_start is None:
                    self.first_of_day_after_start = curr_date
                else:
                    if os.environ.get("TEST") == "Test":
                        if self.test_curr_time is None:
                            raise Exception("Not using test right")
                        return (
                            self.test_curr_time - self.first_of_day_after_start
                        ).seconds // 60
                    else:
                        return (curr_date - self.first_of_day_after_start).seconds // 60

            return 0

        def bracket_order_custom(
            self,
            limitprice: float,
            price: float,
            stopprice: float,
            size: float,
            parent_valid: datetime,
            children_valid: datetime,
            type: Union[Literal["long"], Literal["short"]],
        ) -> tuple[bt.Order, bt.Order, bt.Order]:
            if type == "long":
                main = self.buy(
                    price=price,
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    valid=parent_valid,
                )
                limit_price = self.sell(
                    price=limitprice,
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    parent=main,
                    valid=children_valid,
                )
                stop_price = self.sell(
                    price=stopprice,
                    size=size,
                    exectype=bt.Order.Stop,
                    transmit=True,
                    parent=main,
                    valid=children_valid,
                )
            else:
                main = self.sell(
                    price=price,
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    valid=parent_valid,
                )
                limit_price = self.buy(
                    price=limitprice,
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    parent=main,
                    valid=children_valid,
                )
                stop_price = self.buy(
                    price=stopprice,
                    size=size,
                    exectype=bt.Order.Stop,
                    transmit=True,
                    parent=main,
                    valid=children_valid,
                )

            return main, limit_price, stop_price

        def notify_order(self, order: bt.Order) -> None:
            if order.status in [order.Submitted, order.Accepted]:
                return

            if order.status in [order.Canceled]:
                self.log("Order Cancelled")
                return

            if order.status in [order.Completed]:
                if order.isbuy():
                    self.log(f"Buy EXECUTED, {order.executed.price:.2f}, {self.symbol}")
                    self.set_cash(self.get_cash() - (order.executed.price * order.size))
                elif order.issell():
                    self.log(
                        f"SELL EXECUTED, {order.executed.price:.2f}, {self.symbol}"
                    )
                    self.set_cash(
                        self.get_cash() + (order.executed.price * abs(order.size))
                    )
                self.in_position_event.set()
                if self.position == 0:
                    self.env.runstop()

                self.bar_executed = len(self)

        def next(self) -> None:
            curr_datetime = (
                arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE).datetime
            )
            response_queue: Optional[Queue[Any]] = None
            if os.environ.get("TEST") == "True":
                if self.test_next_tick_queue is None:
                    raise Exception("Using test wrong")
                response_queue = self.test_next_tick_queue.get()
            if (
                not self.data_ready
                and not os.environ.get("TEST")
                or (
                    os.environ.get("TEST")
                    and self.test_curr_time
                    and self.test_curr_time > curr_datetime
                )
            ):
                time_delay = self.count_minutes_delay(curr_datetime)
                self.time_delay = time_delay
            elif self.time_delay <= 5:
                self._next(curr_datetime)
            if response_queue:
                response_queue.put(True)

        def _next(self, curr_datetime: datetime) -> None:
            if self.change_divisor_event.is_set() and not self.position:
                for order in self.orders:
                    self.cancel(order)
                self.divisor = self.divisor_queue.get()
                self.change_divisor_event.clear()

            if (
                not self.position
                and not self.initial_order
                and is_between_dates(
                    curr_datetime,
                    self.start_time,
                    self.start_time + self.max_time,
                )
            ):
                size = ((self.get_cash() * 0.9) // self.start_price) // self.divisor
                if self.target_profit > 0:
                    (
                        self.initial_order,
                        self.limit_price_order,
                        self.stop_price_order,
                    ) = self.bracket_order_custom(
                        limitprice=float(
                            D(self.start_price) * (1 + self.target_profit)
                        ),
                        price=self.start_price * 1.01,
                        stopprice=float(D(self.start_price) * (1 + self.stop_loss)),
                        size=size,
                        parent_valid=self.start_time + timedelta(minutes=5),
                        children_valid=self.start_time + self.max_time,
                        type="long",
                    )
                else:
                    (
                        self.initial_order,
                        self.limit_price_order,
                        self.stop_price_order,
                    ) = self.bracket_order_custom(
                        limitprice=float(
                            D(self.start_price) * (1 + self.target_profit)
                        ),
                        price=self.start_price * 0.99,
                        stopprice=float(D(self.start_price) * (1 + self.stop_loss)),
                        size=size,
                        parent_valid=self.start_time + timedelta(minutes=5),
                        children_valid=self.start_time + self.max_time,
                        type="short",
                    )
                self.orders = [
                    self.initial_order,
                    self.limit_price_order,
                    self.stop_price_order,
                ]
            elif (
                self.position
                and not is_order_completed(self.limit_price_order)
                and not is_order_completed(self.stop_price_order)
                and curr_datetime >= self.start_time + self.max_time
            ):
                if self.position.size > 0:
                    self.sell(size=self.position.size, exectype=bt.Order.Market)
                else:
                    self.buy(size=0 - self.position.size, exectype=bt.Order.Market)

    if _mock_broker is not None:

        class TestStrategy(BaseStrategy):
            def get_cash(self) -> float:
                return _mock_broker.get_cash()  # type: ignore

            def set_cash(self, cash: float) -> None:
                _mock_broker.set_cash(cash)  # type: ignore

        return TestStrategy

    if _mock_broker is None:

        class RealStrategy(BaseStrategy):
            def get_cash(self) -> float:
                return self.broker.get_cash()  # type: ignore

            def set_cash(self, cash: float) -> None:
                pass

        return RealStrategy
