from queue import Queue
from threading import Thread
import time
from typing import Any, Callable

from ib.app import IBapi  # type: ignore
from ib.wrapper import get_account_usd, get_current_stock_price


def test_get_account_usd(
    get_app: Callable[[], tuple[IBapi, Queue[Any], Thread]]
) -> None:
    app, queue, thread = get_app()
    thread.start()

    time.sleep(2)
    usd = get_account_usd(app, queue)

    assert usd >= 0
    app.disconnect()
    thread.join()


def test_get_stock_price(
    get_app: Callable[[], tuple[IBapi, Queue[Any], Thread]]
) -> None:
    app, queue, thread = get_app()
    thread.start()

    time.sleep(2)
    price = get_current_stock_price(app, "AAPL", "NASDAQ", queue)
    assert price > 0
    app.disconnect()
    thread.join()
