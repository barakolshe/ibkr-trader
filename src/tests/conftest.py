import arrow
import pytest

from consts.time_consts import TIMEZONE
from models.article import Article
from models.trading import Stock
from utils.math_utils import D


@pytest.fixture
def stock() -> Stock:
    return Stock(
        symbol="AAPL",
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
        article=Article(
            website="CNN",
            url="https://cnn.com",
            content="AAPL is a good stock",
            datetime=arrow.now(tz=TIMEZONE).replace(microsecond=0).datetime,
        ),
    )
