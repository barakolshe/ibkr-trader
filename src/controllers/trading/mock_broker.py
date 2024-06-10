from queue import Queue
from typing import Any
from logger.logger import logger


class MockBroker:
    cash: float
    queue: Queue[tuple[str, Any]]

    def __init__(self, queue: Queue[tuple[str, Any]], cash: float) -> None:
        self.cash = cash
        self.queue = queue

    def main_loop(self) -> None:
        while True:
            type, value = self.queue.get()
            if type == "GET":
                value.put(self.cash)
            elif type == "SET":
                logger.info(f"Setting cash to {value:.2f}")
                self.cash = value
            else:
                raise Exception("Invalid message")
