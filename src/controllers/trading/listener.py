import ujson
from queue import Queue
import socket
from typing import Any, Optional

import arrow
from consts.time_consts import DATETIME_FORMATTING, TIMEZONE
from ib.app import IBapi  # type: ignore
from logger.logger import logger
from consts.networking_consts import LISTENING_PORT
from controllers.evaluation.groups import get_group_for_score
from controllers.trading.main_trader import trade
from models.article import Article
from models.trading import Stock
from persistency.data_handler import load_groups_from_file

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(("127.0.0.1", LISTENING_PORT))


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


def listen_for_stocks(queue: Queue[Optional[Stock]]) -> None:
    server.listen(5)
    logger.info("Server is listening")
    while True:
        conn, addr = server.accept()
        logger.info(f"Connected by {addr}")
        data = conn.recv(2048).decode("utf-8")
        if data == "EXIT":
            conn.close()
            queue.put(None)
            break
        stock_json = ujson.loads(data)
        stock = json_to_stock(stock_json)
        conn.sendall("OK".encode("utf-8"))
        queue.put(stock)
        conn.close()


def queue_listener(app: IBapi, queue: Queue[Optional[Stock]]) -> None:
    groups = load_groups_from_file()
    while True:
        stock = queue.get()
        if stock is None:
            return
        datetime = stock.article.datetime
        if datetime < arrow.now().shift(minutes=-2).datetime:
            logger.info("Stock is too old, skipping")
            continue
        matching_group = get_group_for_score(
            groups,
            stock.score,
        )
        trade(app, queue, stock, matching_group)
