from queue import Queue
from typing import Any


class PositionsManager:
    open_strategies: list[Any] = []
    open_positions: list[Any] = []
    strategies_queue: Queue[tuple[str, Any]]

    def __init__(self, strategies_queue: Queue[tuple[str, Any]]) -> None:
        self.strategies_queue = strategies_queue

    def main_loop(self) -> None:
        while True:
            type, value = self.strategies_queue.get()

            if type == "ADD":
                self.add_strategy(value)
            elif type == "OPEN":
                self.started_position(value)
            elif type == "CLOSE":
                self.finished_strategy(value)
            elif type == "GET_STRATEGIES":
                value.put(self.get_strategies())
            elif type == "GET":
                value.put(self.get_divisor())
            else:
                raise Exception("Invalid type")

    def add_strategy(self, strategy: Any) -> None:
        self.open_strategies.append(strategy)

    def started_position(self, strategy: Any) -> None:
        self.open_positions.append(strategy)

    def finished_strategy(self, strategy: Any) -> None:
        index = [strategy.symbol for strategy in self.open_strategies].index(
            strategy.symbol
        )
        del self.open_strategies[index]
        index = [strategy.symbol for strategy in self.open_positions].index(
            strategy.symbol
        )
        del self.open_positions[index]

    def get_divisor(self) -> int:
        return len(self.open_strategies) - len(self.open_positions)

    def get_strategies(self) -> list[Any]:
        return self.open_strategies
