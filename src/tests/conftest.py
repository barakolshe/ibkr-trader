from queue import Queue
from threading import Thread
from typing import Any, Callable
import arrow
import pytest
import decimal

from consts.time_consts import DATETIME_FORMATTING, TIMEZONE
from ib.app import IBapi  # type: ignore
from models.article import Article
from models.trading import Stock
from utils.math_utils import D


@pytest.fixture
def get_app() -> Callable[[], tuple[IBapi, Queue[Any], Thread]]:
    def inside_get_app() -> tuple[IBapi, Queue[Any], Thread]:
        queue = Queue[Any]()
        app = IBapi(queue)
        app.connect("127.0.0.1", 7497, 1)
        thread = Thread(target=app.run)
        return app, queue, thread

    return inside_get_app


@pytest.fixture
def stock() -> Stock:
    return Stock(
        symbol="AAPL",
        score=D("0.5"),
        article=Article(
            website="CNN",
            url="https://cnn.com",
            content="AAPL is a good stock",
            datetime=arrow.now(tz=TIMEZONE).replace(microsecond=0).datetime,
        ),
    )


@pytest.fixture
def stock_short() -> Stock:
    return Stock(
        symbol="AAPL",
        score=D("-0.5"),
        article=Article(
            website="CNN",
            url="https://cnn.com",
            content="AAPL is a good stock",
            datetime=arrow.now(tz=TIMEZONE).replace(microsecond=0).datetime,
        ),
    )
