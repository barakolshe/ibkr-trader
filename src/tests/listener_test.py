import json
from queue import Queue
from threading import Thread
from typing import Any
import pika

from controllers.trading.listener import listen_for_stocks
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
