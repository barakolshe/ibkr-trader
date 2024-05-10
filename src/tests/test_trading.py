import time
from typing import Callable
from controllers.trading.main_trader import trade
from queue import Queue
from threading import Thread
from typing import Any, Callable

from ib.app import IBapi  # type: ignore
from models.trading import GroupRatio, Stock
from models.trading import Stock
from utils.math_utils import D


def test_trade_long(
    get_app: Callable[[], tuple[IBapi, Queue[Any], Thread]], stock: Stock
) -> None:
    app, queue, thread = get_app()
    thread.start()

    time.sleep(2)
    trade(
        app,
        queue,
        stock,
        GroupRatio(
            score_range=(D("0.5"), D("1")),
            target_profit=D("0.01"),
            stop_loss=D("-0.01"),
            average=D("0.01"),
            urls=[],
        ),
    )

    app.disconnect()
    thread.join()


def test_trade_short(
    get_app: Callable[[], tuple[IBapi, Queue[Any], Thread]], stock: Stock
) -> None:

    app, queue, thread = get_app()
    thread.start()

    time.sleep(2)
    trade(
        app,
        queue,
        stock,
        GroupRatio(
            score_range=(D("0.5"), D("1")),
            target_profit=D("-0.01"),
            stop_loss=D("0.01"),
            average=D("0.01"),
            urls=[],
        ),
    )

    app.disconnect()
    thread.join()
