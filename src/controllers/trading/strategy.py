from datetime import datetime, timedelta
from decimal import Decimal
from queue import Queue
import time
from typing import Any, Literal, Optional, Union
import arrow
import backtrader as bt

from consts.time_consts import TIMEZONE
from utils.math_utils import D
from logger.logger import logger


def is_order_completed(order: bt.Order) -> bool:
    return order.status in [bt.Order.Completed]


def strategy_factory(
    _target_profit: Decimal,
    _stop_loss: Decimal,
    _max_time: int,
    _symbol: str,
    _event_timestamp: datetime,
    type: Literal["REAL", "TEST"],
    _target_price: Optional[Decimal] = None,
    _mock_broker_queue: Optional[Queue[tuple[str, Any]]] = None,
) -> bt.Strategy:

    class BaseStrategy(bt.Strategy):  # type: ignore
        symbol: str = _symbol
        event_timestamp: datetime = _event_timestamp

        target_profit: Decimal = _target_profit
        stop_loss: Decimal = _stop_loss
        max_time: int = _max_time
        price: Optional[Decimal] = _target_price

        data_ready: bool = False

        divisor: Optional[int] = None

        initial_order: Optional[bt.Order] = None
        limit_price_order: Optional[bt.Order] = None
        stop_price_order: Optional[bt.Order] = None
        orders: list[bt.Order] = []

        # For missing minutes
        first_of_day_after_start: Optional[datetime] = None

        def get_cash(self) -> float:
            raise NotImplementedError()

        def __init__(self) -> None:
            self.dataclose = self.data.close
            self.strategies_manager_queue.put(("ADD", self))

        def notify_data(self, data: Any, status: int) -> None:
            if status == data.LIVE:
                self.data_ready = True

        def count_seconds_delay(self, curr_date: datetime) -> int:
            if self.first_of_day_after_start is None:
                raise Exception("first_of_day_after_start is None")
            return (curr_date - self.first_of_day_after_start).seconds

        def get_price(self, price: Decimal) -> Any:
            raise NotImplementedError()

        def bracket_order_custom(
            self,
            limitprice: Decimal,
            price: Decimal,
            stopprice: Decimal,
            size: float,
            parent_valid: timedelta,
            children_valid: timedelta,
            order_type: Union[Literal["long"], Literal["short"]],
        ) -> tuple[bt.Order, bt.Order, bt.Order]:
            if order_type == "long":
                main = self.buy(
                    price=self.get_price(price),
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    valid=parent_valid,
                    outsideRth=True,
                )
                limit_price = self.sell(
                    price=self.get_price(limitprice),
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    parentId=main.orderId if hasattr(main, "orderId") else None,
                    valid=children_valid,
                    outsideRth=True,
                )
                stop_price = self.sell(
                    price=self.get_price(stopprice),
                    size=size,
                    exectype=bt.Order.StopLimit,
                    plimit=self.get_price(stopprice * D("0.95")),
                    transmit=True,
                    parentId=main.orderId if hasattr(main, "orderId") else None,
                    valid=children_valid,
                    outsideRth=True,
                )
            else:
                main = self.sell(
                    price=price,
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    valid=parent_valid,
                    outsideRth=True,
                )
                limit_price = self.buy(
                    price=self.get_price(limitprice),
                    size=size,
                    exectype=bt.Order.Limit,
                    transmit=False,
                    parentId=main.orderId if hasattr(main, "orderId") else None,
                    valid=children_valid,
                    outsideRth=True,
                )
                stop_price = self.buy(
                    price=self.get_price(stopprice),
                    size=size,
                    exectype=bt.Order.StopLimit,
                    plimit=self.get_price(stopprice * D("1.05")),
                    transmit=True,
                    parentId=main.orderId if hasattr(main, "orderId") else None,
                    valid=children_valid,
                    outsideRth=True,
                )

            return main, limit_price, stop_price

        def order_filled_follow_up_actions(self, order: bt.Order) -> None:
            raise NotImplementedError()

        def order_submitted_follow_up_actions(self) -> None:
            self.strategies_manager_queue.put(("OPEN", self))

        def notify_order(self, order: bt.Order) -> None:
            if self.initial_order is not None and self.initial_order.status in [
                order.Canceled
            ]:
                logger.info("Initial order cancelled")
                self.stop_run()
            if order.status in [order.Submitted, order.Accepted]:
                return

            if order.status in [order.Canceled]:
                logger.info("Order Cancelled")
                return

            if order.status in [order.Completed]:
                if order.isbuy():
                    logger.info(
                        f"Buy EXECUTED, {order.executed.price:.2f}, {self.symbol}, divider: {self.divisor}"
                    )
                elif order.issell():
                    logger.info(
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

        def should_start_trading(self, curr_datetime: datetime) -> bool:
            raise NotImplementedError()

        def handle_position_without_price(self, seconds_delay: int) -> None:
            if self.data.volume[-1:-60] is None:
                return

        def handle_position_with_price(self, seconds_delay: int) -> None:
            return

        def next(self) -> None:
            curr_datetime = (
                arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE).datetime
            )
            if (
                self.event_timestamp
                > arrow.get(curr_datetime)
                .shift(days=1)
                .datetime  # TODO change when weekend
                and self.initial_order is None
            ):
                self.stop_run()
                return

            # Checking if i should start trading
            if not self.should_start_trading(curr_datetime):
                return

            # Setting the first tick of the day
            if self.first_of_day_after_start is None:
                self.first_of_day_after_start = curr_datetime

            time_delay = self.count_seconds_delay(curr_datetime)
            # Buy opening position

            if self.price is not None:
                self.handle_position_with_price(time_delay)
            else:
                self.handle_position_without_price(time_delay)

        def cancel_all_orders(self) -> None:
            for order in self.orders:
                self.cancel(order)

        def get_size(self) -> int:
            raise NotImplementedError()

        def move_into_position(self) -> None:
            size = self.get_size()
            if size == 0:
                return
            if self.target_profit > 0:
                (
                    self.initial_order,
                    self.limit_price_order,
                    self.stop_price_order,
                ) = self.bracket_order_custom(
                    limitprice=D(
                        (D(self.dataclose[0]) * (1 + self.target_profit)),
                        precision=D("0.05"),
                    ),
                    price=D(self.dataclose[0] * 1.01, precision=D("0.05")),
                    stopprice=D(
                        float(D(self.dataclose[0]) * (1 + self.stop_loss)),
                        precision=D("0.05"),
                    ),
                    size=size,
                    parent_valid=timedelta(minutes=5),
                    children_valid=timedelta(minutes=self.max_time),
                    order_type="long",
                )
            else:
                (
                    self.initial_order,
                    self.limit_price_order,
                    self.stop_price_order,
                ) = self.bracket_order_custom(
                    limitprice=D(
                        D(self.dataclose[0]) * (1 + self.target_profit),
                        precision=D("0.05"),
                    ),
                    price=D(self.dataclose[0] * 0.99, precision=D("0.05")),
                    stopprice=D(
                        (D(self.dataclose[0]) * (1 + self.stop_loss)),
                        precision=D("0.05"),
                    ),
                    size=size,
                    parent_valid=timedelta(minutes=5),
                    children_valid=timedelta(minutes=self.max_time),
                    order_type="short",
                )
            self.order_submitted_follow_up_actions()
            self.orders = [
                self.initial_order,
                self.limit_price_order,
                self.stop_price_order,
            ]

        def move_out_of_position(self, curr_datetime: datetime) -> None:
            if self.position.size > 0:
                self.sell(
                    size=self.position.size,
                    price=self.get_price(self.dataclose[0] * 0.98),
                    exectype=bt.Order.Limit,
                    outsideRth=True,
                )
            else:
                self.buy(
                    size=0 - self.position.size,
                    price=self.get_price(self.dataclose[0] * 1.02),
                    exectype=bt.Order.Limit,
                    outsideRth=True,
                )

    if type == "TEST":

        class TestStrategy(BaseStrategy):

            def __init__(self) -> None:
                super().__init__()

            def order_filled_follow_up_actions(self, order: bt.Order) -> None:
                self.set_cash(self.get_cash() - (order.executed.price * order.size))

            def get_price(self, price: Decimal) -> Any:
                return float(price)

            def should_start_trading(self, curr_datetime: datetime) -> bool:
                return curr_datetime >= self.event_timestamp

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

            def get_size(self) -> int:
                return int(1000 // self.dataclose[0])

        return TestStrategy

    if type == "REAL":

        class RealStrategy(BaseStrategy):
            def __init__(self) -> None:
                self.start_time = arrow.now(tz=TIMEZONE).datetime
                super().__init__()
                logger.info(f"Started Strategy {self.symbol}, {self.start_time}")

            def order_filled_follow_up_actions(self, order: bt.Order) -> None:
                return

            def get_cash(self) -> float:
                return self.broker.getcash()  # type: ignore

            def should_start_trading(self, curr_datetime: datetime) -> bool:
                return self.data_ready

            def get_size(self) -> int:
                return int(1000 // self.dataclose[0])

            def get_price(self, price: Decimal) -> Any:
                return D(price, precision=D("0.05"))

        return RealStrategy
