from datetime import datetime
import json
from queue import Queue
from threading import Thread
import socket, time
from typing import Any

from consts.networking_consts import LISTENING_PORT
from controllers.trading.listener import listen_for_stocks

stock: dict[str, Any] = {
    "symbol": "AAPL",
    "score": 9.5,
    "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
}


def test_listen_for_stocks() -> None:
    queue: Queue[Any] = Queue()
    server = Thread(target=listen_for_stocks, args=(queue,))
    server.start()
    time.sleep(2)

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(("127.0.0.1", LISTENING_PORT))
    client_socket.sendall(json.dumps(stock).encode("utf-8"))
    data = client_socket.recv(20)
    client_socket.close()
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(("127.0.0.1", LISTENING_PORT))
    client_socket.send("EXIT".encode("utf-8"))
    assert data == b"OK"
    assert queue.get() == stock
    client_socket.close()
    server.join()
