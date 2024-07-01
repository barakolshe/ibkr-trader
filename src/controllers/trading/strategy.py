from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal, Optional
import arrow
import backtrader as bt
from numpy import average
from pydantic import BaseModel, ConfigDict

from consts.time_consts import TIMEZONE
from consts.trading_consts import (
    CHECK_PEAKS,
    CHOSEN_STOCKS_AMOUNT,
    STOP_LOSS,
    TARGET_PROFIT,
    CLOSE_GAP_MULTIPLIER_THRESHOLD,
    get_end_datetime,
    get_analysis_start_datetime,
    get_start_datetime,
    get_volume_analysis_start_datetime,
)
from controllers.trading.indicators.adx import ADX  # type: ignore
from controllers.trading.indicators.rsi import CustomRSI  # type: ignore
from utils.math_utils import D
from logger.logger import logger, log_important


class StrategyType(Enum):
    TEST = "TEST"
    PAPER = "PAPER"
    REAL = "LIVE"


def interpolate_volume(
    volume: float, min_volume: int = 10000, max_volume: int = 40000
) -> float:
    if volume <= min_volume:
        return 0
    elif volume >= max_volume:
        return 1
    else:
        return (volume - min_volume) / (max_volume - min_volume)


class OrderType(Enum):
    LONG = "long"
    SHORT = "short"


class DataManager(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data1: Any
    data3: Any
    data5: Any
    # rsi: Any
    adx: Any
    symbol: Optional[str] = None
    score: Optional[float] = 0
    close_gap: Optional[float] = 0
    average_volume: Optional[int] = None
    absolute_gap: Optional[float] = 0
    should_use_rsi: bool = False
    peak_price_gap: Optional[float] = None
    is_in_position: bool = False
    did_leave_position: bool = False

    initial_order: Optional[bt.Order] = None
    limit_price_order: Optional[bt.Order] = None
    stop_price_order: Optional[bt.Order] = None

    market_order: Optional[bt.Order] = None


def strategy_factory(
    symbols: list[str],
    _today: datetime,
    type: StrategyType,
) -> bt.Strategy:

    class BaseStrategy(bt.Strategy):  # type: ignore
        today: datetime = _today

        data_ready: bool = False
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
                        adx=ADX(self.datas[index + 1]),
                    )
                )

        def should_start_trading(self, curr_datetime: datetime) -> bool:
            raise NotImplementedError()

        def get_cash(self) -> float:
            return self.broker.getcash()  # type: ignore

        def notify_data(self, data: Any, status: int) -> None:
            if status == data.LIVE:
                self.data_ready = True

        def get_price(self, price: float) -> float:
            return float(D(price, precision=D("0.05")))

        def get_price_with_deviation(
            self, price: float, order_type: OrderType
        ) -> float:
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

        def stop_run(self) -> None:
            print(f"Stopping run {self.get_curr_datetime()}")
            self.env.runstop()

        def buy_custom(
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
            order_type: OrderType,
        ) -> tuple[bt.Order, bt.Order, bt.Order]:
            if order_type == OrderType.LONG:
                main = self.buy_custom(
                    data=data,
                    price=self.get_price_with_deviation(price, OrderType.LONG),
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
                    price=self.get_price_with_deviation(price, OrderType.SHORT),
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

        def get_close_gap_percentage(
            self, data_manager: DataManager, curr_datetime: arrow.Arrow
        ) -> float:
            close_gap: float = (
                data_manager.data1.close[0]
                / data_manager.data1.open[
                    self.get_index_by_datetime(
                        get_analysis_start_datetime(self.today),
                    )
                ]
            ) - 1
            return close_gap

        def get_close_gap_difference(
            self, data_manager: DataManager, datetime: arrow.Arrow
        ) -> float:
            close_gap: float = (
                data_manager.data1.close[0]
                - data_manager.data1.open[
                    self.get_index_by_datetime(
                        datetime,
                    )
                ]
            )
            return close_gap

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
            absolute_gap = 0
            start_index = self.get_index_by_datetime(
                get_analysis_start_datetime(self.today).shift(
                    minutes=5
                ),  # TODO maybe change this
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
            log_important(
                f"ADX for {data_manager.symbol}: {data_manager.adx[0]}", "info"
            )

            data_manager.absolute_gap = abs(data_manager.close_gap) / absolute_gap
            return True

        def get_curr_datetime(self) -> arrow.Arrow:
            return arrow.get(self.data.datetime.datetime(0)).to(TIMEZONE)

        def make_end_market_order(self, data_manager: DataManager) -> None:
            if (
                data_manager.initial_order is None
                or data_manager.limit_price_order is None
                or data_manager.stop_price_order is None
            ):
                raise Exception("Initial order is None")
            if data_manager.initial_order.isbuy():
                data_manager.market_order = self.sell_custom(
                    data=data_manager.data1,
                    size=data_manager.initial_order.size,
                    exectype=bt.Order.Limit,
                    price=self.get_price_with_deviation(
                        self.data1.close[0], OrderType.SHORT
                    ),
                )
            else:
                data_manager.market_order = self.buy_custom(
                    data=data_manager.data1,
                    size=data_manager.initial_order.size,
                    exectype=bt.Order.Limit,
                    price=self.get_price_with_deviation(
                        self.data1.close[0], OrderType.SHORT
                    ),
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
                    if data_manager.absolute_gap is None:
                        raise Exception("Absolute gap is None")
                    data_manager.score = (
                        abs(self.get_close_gap_percentage(data_manager, curr_datetime))
                        * data_manager.absolute_gap
                        * interpolate_volume(
                            data_manager.average_volume,
                            10000,
                            int(self.get_cash() // 2),
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
                        abs(self.get_close_gap_percentage(data_manager, curr_datetime))
                        * data_manager.absolute_gap
                        * interpolate_volume(
                            data_manager.average_volume,
                            10000,
                            int(self.get_cash() // 2),
                        )
                        * 100
                    )
                    log_important(
                        f"Score for {data_manager.symbol}: {data_manager.score}", "info"
                    )

        def enter_position(self) -> None:
            for data_manager in self.data_managers:
                if (
                    arrow.get(data_manager.data1.datetime.datetime(0)).to(TIMEZONE)
                    != self.get_curr_datetime()
                    or data_manager.is_in_position
                ):
                    data_manager.is_in_position = True
                    continue
                self.get_stats(data_manager)

            # Entering position with stocks with highest scores
            filtered_scores: list[DataManager] = []
            for data_manager in self.data_managers:
                if data_manager.score is not None and data_manager.score > 0:
                    filtered_scores.append(data_manager)
            sorted_scores: list[DataManager] = sorted(
                filtered_scores, key=lambda x: x.score, reverse=True  # type: ignore
            )[0:CHOSEN_STOCKS_AMOUNT]
            cash = self.get_cash()
            for data_manager in sorted_scores:
                if data_manager.is_in_position:
                    continue
                data = data_manager.data1
                if data_manager.average_volume is None:
                    raise Exception("Average volume is None")
                size = self.get_size(
                    data.close[0],
                    data_manager.average_volume,
                    cash,
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
                        order_type=OrderType.LONG,
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
                        order_type=OrderType.SHORT,
                    )

            for data_manager in self.data_managers:
                data_manager.is_in_position = True

        def check_peaks(self) -> None:
            for data_manager in self.data_managers:
                if (
                    not data_manager.initial_order
                    or data_manager.initial_order.executed.price <= 0
                    or data_manager.did_leave_position
                ):
                    continue
                if data_manager.close_gap is not None and data_manager.close_gap > 0:
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
                and self.data1.close[0] > 1
            ):
                self.enter_position()
            # Checking if time is up for the day
            if curr_datetime >= get_end_datetime(self.today):
                self.check_end_position()
                return

            if CHECK_PEAKS:
                self.check_peaks()

        def get_size(
            self, price: float, average_volume: int, cash: float, divider: int
        ) -> int:
            raise NotImplementedError()

    if type == StrategyType.TEST:

        class TestStrategy(BaseStrategy):

            def get_price_with_deviation(
                self,
                price: float,
                order_type: OrderType,
            ) -> float:
                if order_type == OrderType.LONG:
                    return float(D(price * 1.005, precision=D("0.05")))
                else:
                    return float(D(price * 0.995, precision=D("0.05")))

            def should_start_trading(self, curr_datetime: datetime) -> bool:
                return True

            def get_size(
                self, price: float, average_volume: int, cash: float, divider: int
            ) -> int:
                return min(
                    average_volume // 2,
                    int(self.get_cash() - (1000000 - 40000) // float(price) // divider),
                )

        return TestStrategy

    if type == StrategyType.REAL:

        class RealStrategy(BaseStrategy):
            def get_price_with_deviation(
                self,
                price: float,
                order_type: OrderType,
            ) -> float:
                if order_type == OrderType.LONG:
                    return float(D(price * 1.0005, precision=D("0.05")))
                else:
                    return float(D(price * 0.9995, precision=D("0.05")))

            def should_start_trading(self, curr_datetime: datetime) -> bool:
                return self.data_ready

            def get_size(
                self, price: float, average_volume: int, cash: float, divider: int
            ) -> int:
                return min(
                    average_volume // 2,
                    int(min(self.get_cash(), 5000) // float(price) // divider),
                )

        return RealStrategy
