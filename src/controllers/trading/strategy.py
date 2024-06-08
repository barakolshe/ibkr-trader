from datetime import datetime, timedelta
from decimal import Decimal
from queue import Queue
import random
import threading
import time
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
    type: Literal["REAL", "TEST", "TEST_REAL_TIME"],
    _strategies_manager_queue: Queue[tuple[str, Any]],
    _mock_broker_queue: Optional[Queue[tuple[str, Any]]] = None,
    _test_next_tick_queue: Optional[Queue[tuple[Queue[Any], datetime]]] = None,
    _test_curr_time: Optional[datetime] = None,
) -> bt.Strategy:

    class BaseStrategy(bt.Strategy):  # type: ignore
        target_profit: Decimal = _target_profit
        stop_loss: Decimal = _stop_loss
        max_time: timedelta = _max_time
        start_price: Optional[Decimal] = None
        symbol: str = _symbol
        event_timestamp: datetime = _event_timestamp
        data_ready: bool = False

        strategies_manager_queue: Queue[tuple[str, Any]] = _strategies_manager_queue
        divisor: int

        initial_order: Optional[bt.Order] = None
        limit_price_order: Optional[bt.Order] = None
        stop_price_order: Optional[bt.Order] = None
        orders: list[bt.Order] = []

        # For missing minutes
        first_of_day_after_start: Optional[datetime] = None
        time_delay: int = 0

        def get_cash(self) -> float:
            raise NotImplementedError()

        def set_cash(self, cash: float) -> None:
            raise NotImplementedError()

        def log(self, txt: str, date: Optional[datetime] = None) -> None:
            """Logging function for this strategy"""
            date = date or self.data.datetime.datetime(0)
            logger.info(f"{arrow.get(date).to(TIMEZONE).datetime} {txt}")

        def __init__(self) -> None:
            self.start_time = (
                arrow.get(self.data.datetime.datetime(1)).to(TIMEZONE).datetime
            )
            self.log(
                f"Started Strategy {self.symbol}",
                self.start_time,
            )
            self.dataclose = self.data.close
            self.strategies_manager_queue.put(("ADD", self))

        def get_divisor(self) -> int:
            response_queue = Queue[int]()
            self.strategies_manager_queue.put(("GET", response_queue))
            self.divisor = response_queue.get()
            return self.divisor

        def notify_data(self, data: Any, status: int) -> None:
            if status == data.LIVE:
                self.data_ready = True

        def count_minutes_delay(self, curr_date: datetime) -> int:
            if self.first_of_day_after_start is None:
                raise Exception("first_of_day_after_start is None")
            return (curr_date - self.first_of_day_after_start).seconds // 60

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

        def order_filled_follow_up_actions(self, order: bt.Order) -> None:
            raise NotImplementedError()

        def order_submitted_follow_up_actions(self) -> None:
            self.strategies_manager_queue.put(("OPEN", self))

        def notify_order(self, order: bt.Order) -> None:
            if order.status in [order.Submitted, order.Accepted]:
                return

            if order.status in [order.Canceled]:
                self.log("Order Cancelled")
                return

            if order.status in [order.Completed]:
                if order.isbuy():
                    self.log(
                        f"Buy EXECUTED, {order.executed.price:.2f}, {self.symbol}, divider: {self.divisor}"
                    )
                elif order.issell():
                    self.log(
                        f"SELL EXECUTED, {order.executed.price:.2f}, {self.symbol}"
                    )
                self.order_filled_follow_up_actions(order)
                self.bar_executed = len(self)
                # Leaving if the position was closed
                if self.position.size == 0:
                    self.strategies_manager_queue.put(("CLOSE", self))
                    self.stop_run()
                    return

        def stop_run(self) -> None:
            self.env.runstop()

        def should_wait_for_queue_signal(self) -> bool:
            raise NotImplementedError()

        def wait_for_queue_signal(
            self, curr_datetime: datetime
        ) -> Optional[Queue[Any]]:
            raise NotImplementedError()

        def should_start_trading(self, curr_datetime: datetime) -> bool:
            raise NotImplementedError()

        def handle_next_finish(self, response_queue: Optional[Queue[Any]]) -> None:
            raise NotImplementedError()

        def sleep(self) -> None:
            raise NotImplementedError()

        def set_first_tick_of_day(self, curr_datetime: datetime) -> datetime:
            if (
                curr_datetime >= self.event_timestamp
                and self.first_of_day_after_start is None
            ):
                self.first_of_day_after_start = curr_datetime

        def next(self) -> None:
            curr_datetime = (
                arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE).datetime
            )
            self.set_first_tick_of_day(curr_datetime)
            if self.first_of_day_after_start is None:
                return
            # The response queue part is for testing
            response_queue: Optional[Queue[Any]] = None
            if self.should_wait_for_queue_signal():
                response_queue = self.wait_for_queue_signal(curr_datetime)
                if response_queue is None:
                    return

            if not self.should_start_trading(curr_datetime):
                time_delay = self.count_minutes_delay(curr_datetime)
                self.time_delay = time_delay
            elif self.time_delay <= 5:
                if not self.start_price:
                    self.start_price = self.dataclose[0]
                if self.start_price < 0.5:
                    self.stop_run()
                    return
                self._next(curr_datetime)
            else:
                self.stop_run()
                return

            self.handle_next_finish(response_queue)

        def _next(self, curr_datetime: datetime) -> None:
            if (
                not self.position
                and not self.initial_order
                and is_between_dates(
                    curr_datetime,
                    self.first_of_day_after_start,
                    self.first_of_day_after_start + self.max_time,
                )
            ):
                self.sleep()  # Making sure the thread queues are in sync or something like that
                divisor = self.get_divisor()
                cash = self.get_cash()
                size = ((cash * 0.95) // self.dataclose[0]) // divisor
                if size == 0:
                    return
                if self.target_profit > 0:
                    (
                        self.initial_order,
                        self.limit_price_order,
                        self.stop_price_order,
                    ) = self.bracket_order_custom(
                        limitprice=float(
                            D(self.dataclose[0]) * (1 + self.target_profit)
                        ),
                        price=self.dataclose[0] * 1.01,
                        stopprice=float(D(self.dataclose[0]) * (1 + self.stop_loss)),
                        size=size,
                        parent_valid=curr_datetime + timedelta(minutes=5),
                        children_valid=curr_datetime + self.max_time,
                        type="long",
                    )
                else:
                    (
                        self.initial_order,
                        self.limit_price_order,
                        self.stop_price_order,
                    ) = self.bracket_order_custom(
                        limitprice=float(
                            D(self.dataclose[0]) * (1 + self.target_profit)
                        ),
                        price=self.dataclose[0] * 0.99,
                        stopprice=float(D(self.dataclose[0]) * (1 + self.stop_loss)),
                        size=size,
                        parent_valid=curr_datetime + timedelta(minutes=5),
                        children_valid=curr_datetime + self.max_time,
                        type="short",
                    )
                self.order_submitted_follow_up_actions()
                self.orders = [
                    self.initial_order,
                    self.limit_price_order,
                    self.stop_price_order,
                ]
            elif (
                self.position.size != 0
                and not is_order_completed(self.limit_price_order)
                and not is_order_completed(self.stop_price_order)
                and curr_datetime >= self.first_of_day_after_start + self.max_time
            ):
                if self.position.size > 0:
                    self.sell(size=self.position.size, exectype=bt.Order.Market)
                else:
                    self.buy(size=0 - self.position.size, exectype=bt.Order.Market)

    if type == "TEST_REAL_TIME":

        class TestStrategy(BaseStrategy):
            test_next_tick_queue: Optional[Queue[tuple[Queue[Any], datetime]]] = (
                _test_next_tick_queue
            )
            test_curr_time: Optional[datetime] = _test_curr_time

            def sleep(self) -> None:
                time.sleep(random.uniform(0, 4))

            def order_filled_follow_up_actions(self, order: bt.Order) -> None:
                self.sleep()
                self.set_cash(self.get_cash() - (order.executed.price * order.size))

            def handle_next_finish(self, response_queue: Optional[Queue[Any]]) -> None:
                if response_queue is not None:
                    response_queue.put(None)

            def should_wait_for_queue_signal(self) -> bool:
                return True

            def wait_for_queue_signal(
                self, curr_datetime: datetime
            ) -> Optional[Queue[Any]]:
                if self.test_curr_time is None:
                    raise Exception("Using test wrong")
                if self.test_next_tick_queue is None:
                    raise Exception("Using test wrong")
                if self.test_curr_time > curr_datetime:
                    return None
                try:
                    while True:
                        response_queue, server_curr_datetime = (
                            self.test_next_tick_queue.get(timeout=5)
                        )

                        if (
                            server_curr_datetime != curr_datetime
                            and self.position.size == 0
                        ):
                            response_queue.put(None)
                            continue
                        return response_queue
                except:
                    raise Exception("Bad stuff happened")

            def should_start_trading(self, curr_datetime: datetime) -> bool:
                return (
                    self.test_curr_time is not None
                    and self.test_curr_time <= curr_datetime
                )

            def get_cash(self) -> float:
                response_queue = Queue[float]()
                if _mock_broker_queue is None:
                    raise Exception("Using test wrong")
                _mock_broker_queue.put(("GET", response_queue))
                return response_queue.get()

            def set_cash(self, cash: float) -> None:
                if _mock_broker_queue is None:
                    raise Exception("Using test wrong")
                _mock_broker_queue.put(("SET", cash))

        return TestStrategy

    class GenericRealStrategy(BaseStrategy):
        def order_filled_follow_up_actions(self, order: bt.Order) -> None:
            return

        def sleep(self) -> None:
            return

        def handle_next_finish(self, response_queue: Optional[Queue[Any]]) -> None:
            return

        def should_wait_for_queue_signal(self) -> bool:
            return False

        def wait_for_queue_signal(
            self, curr_datetime: datetime
        ) -> Optional[Queue[Any]]:
            return None

        def get_cash(self) -> float:
            return self.broker.get_cash()  # type: ignore

        def set_cash(self, cash: float) -> None:
            return

    if type == "REAL":

        class RealStrategy(GenericRealStrategy):
            def should_start_trading(self, curr_datetime: datetime) -> bool:
                return self.data_ready

        return RealStrategy

    if type == "TEST":

        class TestRealStrategy(GenericRealStrategy):
            def should_start_trading(self, curr_datetime: datetime) -> bool:
                return True

        return TestRealStrategy
