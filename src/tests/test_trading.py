import time
from typing import Callable, Optional
from controllers.trading.trader import Trader
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
    app, app_queue, app_thread = get_app()
    app_thread.start()
    trade_event_queue = Queue[Optional[Stock]]()
    kill_queue = Queue[Any]()

    time.sleep(2)
    trader = Trader(app, trade_event_queue, app_queue, kill_queue)
    trader_thread = Thread(target=trader.main_loop, args=(True,))
    trader_thread.start()
    trade_event_queue.put(stock)
    while len(trader.open_positions) == 0:
        time.sleep(1)

    app.disconnect()
    app_thread.join()
    trader_thread.join()


def test_trade_short(
    get_app: Callable[[], tuple[IBapi, Queue[Any], Thread]], stock_short: Stock
) -> None:

    app, queue, thread = get_app()
    thread.start()

    time.sleep(2)
    trade(
        app,
        queue,
        stock_short,
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
