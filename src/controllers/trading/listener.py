import json
import time
from queue import Queue
from typing import Any, Optional
import pika

import arrow
from consts.time_consts import DATETIME_FORMATTING, TIMEZONE
from ib.app import IBapi  # type: ignore
from logger.logger import logger
from models.article import Article
from models.trading import Stock


def json_to_stock(stock_json: Any) -> Stock:
    return Stock(
        symbol=stock_json["symbol"],
        score=stock_json["score"],
        article=Article(
            website=stock_json["article"]["website"],
            url=stock_json["article"]["url"],
            content=stock_json["article"]["content"],
            datetime=arrow.get(
                stock_json["article"]["datetime"],
                DATETIME_FORMATTING,
                tzinfo=TIMEZONE,
            ).datetime,
        ),
    )


def wait_for_time(kill_queue: Queue[Any]) -> bool:
    has_slept = False
    while True:
        logger.info("Waiting for time")
        if not kill_queue.empty():
            return True
        curr_date = arrow.now(tz=TIMEZONE)
        if curr_date.weekday() == 5 or curr_date.weekday() == 6:
            time.sleep(20)
            has_slept = True
        else:
            if curr_date.hour < 4 and curr_date.hour >= 16:
                time.sleep(20)
                has_slept = True
            else:
                return has_slept


def callback(
    ch: Any, method: Any, properties: Any, body: Any, queue: Queue[Any]
) -> None:
    stock_json = json.loads(body)
    # stock = json_to_stock(stock_json)
    queue.put(stock_json)


def listen_for_stocks(queue: Queue[Stock], kill_queue: Queue[Any]) -> None:
    connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
    channel = connection.channel()
    channel.basic_consume(
        queue="stocks",
        auto_ack=True,
        on_message_callback=lambda ch, method, properties, body: callback(
            ch, method, properties, body, queue
        ),
    )
    channel.start_consuming()
