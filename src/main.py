from queue import Queue
from typing import Any
import time
from threading import Thread
import decimal

from consts.algorithem_consts import PRECISION
from controllers.evaluation.evaluate import get_evaluations, iterate_evaluations
from ib.app import IBapi  # type: ignore


def main() -> None:
    evaluations = get_evaluations()
    queue = Queue[Any]()
    app = IBapi(queue)
    app.connect("127.0.0.1", 7497, 1)
    thread = Thread(target=app.run)
    thread.start()

    time.sleep(2)
    iterate_evaluations(app, evaluations, queue)
    app.disconnect()
    thread.join()


if __name__ == "__main__":
    main()
