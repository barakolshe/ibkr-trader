import ujson
from queue import Queue
from threading import Thread
import socket, time
from typing import Any, Callable

from consts.networking_consts import LISTENING_PORT
from controllers.trading.listener import listen_for_stocks
from ib.app import IBapi  # type: ignore
from models.trading import Stock


def test_listen_for_stocks(stock: Stock) -> None:
    queue: Queue[Any] = Queue()
    server = Thread(target=listen_for_stocks, args=(queue,))
    server.start()
    time.sleep(2)

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(("127.0.0.1", LISTENING_PORT))
    client_socket.sendall(ujson.dumps(stock.get_json()).encode("utf-8"))
    data = client_socket.recv(20)
    client_socket.close()
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(("127.0.0.1", LISTENING_PORT))
    client_socket.send("EXIT".encode("utf-8"))
    assert data == b"OK"
    assert queue.get() == stock


def test_trade_from_socket(
    stock: Stock, get_app: Callable[[], tuple[IBapi, Queue[Any], Thread]]
) -> None:
    app, queue, thread = get_app()
    server = Thread(target=listen_for_stocks, args=(queue,))
    thread.start()
    server.start()
    time.sleep(2)

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(("127.0.0.1", LISTENING_PORT))
    client_socket.sendall(ujson.dumps(stock.get_json()).encode("utf-8"))
    data = client_socket.recv(20)
    client_socket.close()
