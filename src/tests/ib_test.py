from queue import Queue
from threading import Thread
import time
from typing import Any

from ib.app import IBapi  # type: ignore
from ib.wrapper import get_account_usd, get_current_stock_price


def test_get_account_usd() -> None:
    queue = Queue[Any]()
    app = IBapi(queue)
    app.connect("127.0.0.1", 7497, 1)
    thread = Thread(target=app.run)
    thread.start()

    time.sleep(2)
    usd = get_account_usd(app, queue)
    assert usd >= 0
    app.disconnect()
    thread.join()


def test_get_stock_price() -> None:
    queue = Queue[Any]()
    app = IBapi(queue)
    app.connect("127.0.0.1", 7497, 1)
    thread = Thread(target=app.run)
    thread.start()

    time.sleep(2)
    price = get_current_stock_price(app, "AAPL", "NASDAQ", queue)
    assert price > 0
    app.disconnect()
    thread.join()
