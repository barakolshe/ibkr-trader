import json
import ujson
from queue import Queue
from threading import Thread
import socket, time
from typing import Any, Callable
import pika

from consts.networking_consts import LISTENING_PORT
from controllers.trading.listener import listen_for_stocks
from ib.app import IBapi  # type: ignore
from models.trading import Stock


def test_listen_for_stocks(stock_short: Stock) -> None:
    queue: Queue[Any] = Queue()
    kill_queue: Queue[Any] = Queue()

    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = connection.channel()
    channel.queue_declare(queue="stocks")

    thread = Thread(target=listen_for_stocks, args=(queue, kill_queue), daemon=True)
    thread.start()

    value = {"a": 1}
    channel.basic_publish(exchange="", routing_key="stocks", body=json.dumps(value))
    assert value == queue.get()
