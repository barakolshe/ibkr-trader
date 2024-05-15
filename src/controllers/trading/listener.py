import time
import ujson
from queue import Queue
import socket
from typing import Any, Optional

import arrow
from consts.time_consts import DATETIME_FORMATTING, TIMEZONE
from ib.app import IBapi  # type: ignore
from logger.logger import logger
from consts.networking_consts import LISTENING_PORT
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


def listen_for_stocks(queue: Queue[Optional[Stock]], kill_queue: Queue[Any]) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", LISTENING_PORT))
    server.listen(5)
    server.settimeout(10)
    logger.info("Server is listening")
    while True:
        logger.info("Waiting for connections")
        if not kill_queue.empty():
            return
        try:
            conn, addr = server.accept()
            logger.info(f"Connected by {addr}")
            data = conn.recv(100000).decode("utf-8")
        except Exception:
            continue
        stock_json = ujson.loads(data)
        stock = json_to_stock(stock_json)
        conn.sendall("OK".encode("utf-8"))
        queue.put(stock)
        conn.close()
