import itertools
from queue import Queue
from typing import Any


def positional_product(list1: list[Any], list2: list[Any]) -> list[tuple[Any, Any]]:
    product1 = itertools.product(list1, list2)
    product2 = itertools.product(list2, list1)

    return list(product1) + list(product2)


def empty_queue(queue: Queue[Any]) -> None:
    while not queue.empty():
        queue.get()
